"""Versões do projeto (checkpoints): um .zip pequeno com o que difere do oficial.

"Salvar versão" guarda em `<projeto>/.versions/` um .zip com:
- `ui/…`: os arquivos que diferem da UI oficial (como no F5 e no Exportar .zip), além
  dos oficiais que precisam ser arquivados porque a base compartilhada não os tem.
- `resolutions.json` e `resolutions/…`: os ajustes por resolução e arquivos variantes
  (deduplicados por conteúdo e, em projetos leves, pela base oficial por CRC).
- `version.json`: nome, rótulo, data, a lista completa de arquivos do projeto, camadas, modos
  da raiz, metadados de resoluções e os textos editados.

"Restaurar" deixa o projeto como estava: grava os arquivos do .zip, devolve ao oficial os que
eram oficiais naquela versão (procurando a cópia oficial no próprio histórico do projeto, na
pasta UI do jogo ou no cache .official-ui) e tira os que não existiam. Tudo que é trocado
ou removido vai antes para o .history. Antes de restaurar, a versão atual é salva sozinha.

Compatibilidade: versões antigas (salvas sem o bloco `"resolutions"` em `version.json`) não
tinham informação sobre ajustes de resolução; ao restaurá-las, `resolutions.json` e
`resolutions/` atuais são mantidos intactos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import zipfile

from . import __version__, gamedata, multi_resolution, storage, text_data
from .project import HISTORY_LIMIT, Project, _same_content, is_backup_file, safe_name

VERSIONS_DIR = ".versions"
FORMAT = 1
MANIFEST = "version.json"
TEMP_SUFFIX = ".gf-ui-editor.tmp"


@dataclass(frozen=True)
class Version:
    path: Path
    label: str
    created: datetime
    files: int  # arquivos guardados no .zip (os que diferem do oficial + resoluções)
    size: int  # tamanho do .zip
    resolutions: int = 0  # ajustes e variantes de resolução guardados nesta versão


@dataclass
class RestoreResult:
    written: int = 0  # arquivos gravados a partir da versão
    reverted: int = 0  # voltaram ao oficial
    removed: int = 0  # não existiam na versão
    unresolved: list[str] = field(default_factory=list)  # oficial não encontrado: ficaram como estavam


def versions_dir(project: Project) -> Path:
    return project.root / VERSIONS_DIR


def _content_digest(path: Path) -> tuple[int, str]:
    data = path.read_bytes()
    return len(data), hashlib.sha1(data).hexdigest()


def _resolution_files(project: Project) -> list[Path]:
    """Variantes em `resolutions/`, relativas a essa pasta, sem ocultos nem temporários."""
    folder = project.root / multi_resolution.VARIANTS_DIR
    if not folder.is_dir():
        return []
    files: list[str] = []
    root = str(folder)
    for current, folders, names in os.walk(root):
        relative_dir = os.path.relpath(current, root)
        top_level = relative_dir == "."
        folders[:] = [name for name in folders if not name.startswith(".")]
        for name in names:
            if name.startswith(".") or is_backup_file(name):
                continue
            files.append(name if top_level else f"{relative_dir.replace(os.sep, '/')}/{name}")
    return [Path(item) for item in sorted(files, key=str.lower)]


def _resolution_target(project: Project, relative: str) -> Path:
    """Valida e resolve um caminho relativo dentro de `<projeto>/resolutions/`."""
    rel = Path(relative)
    if rel.anchor or ".." in rel.parts or not rel.parts:
        raise ValueError(f"Caminho inválido em resoluções: {relative}")
    base = (project.root / multi_resolution.VARIANTS_DIR).resolve()
    target = (base / rel).resolve()
    if base not in target.parents:
        raise ValueError(f"Caminho inválido em resoluções: {relative}")
    return project.root / multi_resolution.VARIANTS_DIR / rel


def _validate_archive_alias(arcname: str) -> str:
    """Valida um alias interno no .zip (apenas `ui/...` ou `resolutions/...`, sem travessia)."""
    rel = Path(arcname)
    if (
        not arcname
        or rel.anchor
        or ".." in rel.parts
        or len(rel.parts) < 2
        or rel.parts[0] not in ("ui", multi_resolution.VARIANTS_DIR)
    ):
        raise ValueError(f"Referência inválida na versão: {arcname}")
    return arcname


def _atomic_copy(source: Path, target: Path) -> bool:
    """Copia `source` para `target` por arquivo temporário + replace, sem deixar meia escrita."""
    if target.is_file() and _same_content(source, target):
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=TEMP_SUFFIX, dir=target.parent)
    os.close(fd)
    try:
        shutil.copy2(source, temporary)
        os.replace(temporary, target)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    return True


def _backup_project_file(project: Project, file_path: Path) -> Path:
    """Guarda uma cópia em `.history/` para arquivos fora de `ui/` (ex.: `resolutions.json`)."""
    relative = file_path.resolve().relative_to(project.root.resolve())
    folder = project.history_dir / relative
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = folder / f"{stamp}{file_path.suffix}"
    number = 2
    while candidate.exists():
        candidate = folder / f"{stamp}-{number}{file_path.suffix}"
        number += 1
    _atomic_copy(file_path, candidate)
    backups = sorted(
        (item for item in folder.iterdir() if item.is_file()),
        key=lambda item: item.name,
        reverse=True,
    )
    for old in backups[HISTORY_LIMIT:]:
        old.unlink(missing_ok=True)
    return candidate


def _prune_empty_dirs(folder: Path, *, remove_root: bool = False) -> None:
    if not folder.is_dir():
        return
    for current, dirs, files in os.walk(folder, topdown=False):
        if not dirs and not files and (remove_root or current != str(folder)):
            try:
                os.rmdir(current)
            except OSError:
                pass


def save_version(
    project: Project, label: str = "", *, official_files: dict[str, str] | None = None,
) -> Path:
    """Guarda a versão atual do projeto e devolve o caminho do .zip."""
    shipped, _skipped = project.shipped_files()
    files = project.files(refresh=True)
    created = datetime.now()
    label = label.strip()
    folder = versions_dir(project)
    folder.mkdir(parents=True, exist_ok=True)
    stem = created.strftime("%Y%m%d-%H%M%S")
    if label:
        stem += "_" + safe_name(label)[:40]
    target = folder / f"{stem}.zip"
    number = 2
    while target.exists():
        target = folder / f"{stem}-{number}.zip"
        number += 1
    edits = text_data.load_edits(project.root)
    manifest = {
        "format": FORMAT,
        "app_version": __version__,
        "name": project.name,
        "label": label,
        "created": created.isoformat(timespec="seconds"),
        "files": [relative.as_posix() for relative in files],
        "shipped": [relative.as_posix() for relative in shipped],
        "root_modes": project.root_modes,
        "reference_layers": project.reference_layers,
        "text_edits": {
            name: {record_id: {"fields": edit.fields, "original": edit.original} for record_id, edit in records.items()}
            for name, records in edits.items()
        },
    }
    archived = set(shipped)
    official: dict[str, tuple[int, str]] = {}
    if project.light:
        official = gamedata.official_ui_files(project.game_dir) if project.game_dir is not None else {}
        pins = official_files or project.base_files
        official_files = {}
        for relative in files:
            if relative in archived:
                continue
            key = relative.as_posix()
            source = project.resolve(relative)
            blob = pins.get(key)
            if blob is None or (source != project.base_path(blob) and not _same_content(source, project.base_path(blob))):
                blob = project.cache_official(source, key, official)
            if blob is None:
                archived.add(relative)
            else:
                official_files[key] = blob
    elif official_files is not None:
        archived.update(relative for relative in files if relative.as_posix() not in official_files)
    if official_files is not None:
        manifest.update(light=project.light, official_files=official_files, base_files=project.base_files)
    if len(archived) != len(shipped):
        manifest["archived"] = [relative.as_posix() for relative in files if relative in archived]

    res_config_path = project.root / multi_resolution.STORE_NAME
    has_res_config = res_config_path.is_file()
    res_files = _resolution_files(project)
    res_official_files: dict[str, str] = {}
    res_aliases: dict[str, str] = {}
    res_archived: list[tuple[Path, str]] = []
    if res_files:
        base_by_lower = {name.lower(): blob for name, blob in project.base_files.items()}
        # Só calcula hash dos arquivos de ui/ que têm o mesmo tamanho de alguma variante.
        variant_sizes = {
            (project.root / multi_resolution.VARIANTS_DIR / relative).stat().st_size
            for relative in res_files
        }
        archived_digests: dict[tuple[int, str], str] = {}
        for relative in files:
            if relative not in archived:
                continue
            source = project.resolve(relative)
            try:
                if source.stat().st_size in variant_sizes:
                    archived_digests.setdefault(_content_digest(source), f"ui/{relative.as_posix()}")
            except OSError:
                continue
        for relative in res_files:
            key = relative.as_posix()
            source = project.root / multi_resolution.VARIANTS_DIR / relative
            if project.light:
                ui_key = Path(*relative.parts[1:]).as_posix() if len(relative.parts) > 1 else key
                blob = base_by_lower.get(ui_key.lower())
                if blob is None or not _same_content(source, project.base_path(blob)):
                    blob = project.cache_official(source, ui_key, official)
                if blob is not None:
                    res_official_files[key] = blob
                    continue
            digest = _content_digest(source)
            existing = archived_digests.get(digest)
            if existing is not None:
                res_aliases[key] = existing
                continue
            arcname = f"{multi_resolution.VARIANTS_DIR}/{key}"
            archived_digests[digest] = arcname
            res_archived.append((source, arcname))
    res_manifest: dict[str, object] = {
        "config": has_res_config,
        "files": [relative.as_posix() for relative in res_files],
    }
    if res_official_files:
        res_manifest["official_files"] = res_official_files
    if res_aliases:
        res_manifest["aliases"] = res_aliases
    manifest["resolutions"] = res_manifest

    temporary = target.with_name(f".{target.name}{TEMP_SUFFIX}")
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=1))
            for relative in files:
                if relative in archived:
                    archive.write(project.resolve(relative), f"ui/{relative.as_posix()}")
            if has_res_config:
                archive.write(res_config_path, multi_resolution.STORE_NAME)
            for source, arcname in res_archived:
                archive.write(source, arcname)
        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return target


def _read_manifest(path: Path) -> dict | None:
    try:
        with zipfile.ZipFile(path) as archive:
            data = json.loads(archive.read(MANIFEST).decode("utf-8"))
    except (OSError, KeyError, ValueError, zipfile.BadZipFile):
        return None
    return data if isinstance(data, dict) and data.get("format") == FORMAT else None


def list_versions(project: Project) -> list[Version]:
    """Versões guardadas, da mais recente para a mais antiga."""
    folder = versions_dir(project)
    if not folder.is_dir():
        return []
    result = []
    for path in folder.glob("*.zip"):
        manifest = _read_manifest(path)
        if manifest is None:
            continue
        try:
            created = datetime.fromisoformat(str(manifest.get("created")))
        except ValueError:
            created = datetime.fromtimestamp(path.stat().st_mtime)
        res_meta = manifest.get("resolutions")
        if isinstance(res_meta, dict):
            res_count = int(bool(res_meta.get("config"))) + len(res_meta.get("files", []))
        else:
            res_count = 0
        ui_count = len(manifest.get("shipped", []))
        result.append(
            Version(path, str(manifest.get("label") or ""), created, ui_count + res_count, path.stat().st_size, res_count)
        )
    return sorted(result, key=lambda version: version.created, reverse=True)


def delete_version(version: Path) -> None:
    version.unlink()


def _official_copy(project: Project, relative: str, entry: tuple[int, str]) -> Path | None:
    """Uma cópia do arquivo oficial: original guardado no histórico, pasta UI do jogo ou cache."""
    from .game_updates import cached_version  # game_updates importa project; evita ciclo na carga

    candidates = [project.resolve(relative), project.original_path_for(project.ui_dir / relative)]
    if (blob := project.base_files.get(relative)) is not None:
        candidates.append(project.base_path(blob))
    if project.game_dir is not None:
        candidates.append(project.game_dir / "UI" / relative)
    cached = cached_version(entry[1])
    if cached is not None:
        candidates.append(cached)
    for candidate in candidates:
        try:
            if candidate.is_file() and candidate.stat().st_size == entry[0] and gamedata.file_crc(candidate) == entry[1]:
                return candidate
        except OSError:
            continue
    return None


def restore_version(project: Project, version: Path) -> RestoreResult:
    """Deixa o projeto como na versão. Antes, salva a versão atual ("antes de restaurar")."""
    manifest = _read_manifest(version)
    if manifest is None:
        raise ValueError(f"Versão inválida: {version}")
    wanted = {str(name) for name in manifest.get("files", [])}
    archived = {str(name) for name in manifest.get("archived", manifest.get("shipped", []))}
    for name in wanted:
        project.resolve(name)  # Validate paths before extracting or writing anything.
    res_meta = manifest.get("resolutions")
    has_res_meta = isinstance(res_meta, dict)
    want_res_config = bool(res_meta.get("config")) if has_res_meta else False
    want_res_files = [str(name) for name in res_meta.get("files", [])] if has_res_meta else []
    res_pinned = dict(res_meta.get("official_files") or {}) if has_res_meta else {}
    res_aliases = dict(res_meta.get("aliases") or {}) if has_res_meta else {}
    for name in want_res_files:
        _resolution_target(project, name)
    for blob in res_pinned.values():
        project.base_path(str(blob))
    for arcname in res_aliases.values():
        _validate_archive_alias(str(arcname))

    save_version(project, "antes de restaurar")
    result = RestoreResult()
    official = gamedata.official_ui_files(project.game_dir) if project.game_dir is not None else {}
    current = {relative.as_posix(): relative for relative in project.files(refresh=True)}
    current_res = {relative.as_posix(): relative for relative in _resolution_files(project)} if has_res_meta else {}
    restore_light = bool(manifest.get("light", project.light))
    pinned = dict(manifest.get("official_files") or {})
    restored_base = dict(manifest.get("base_files", project.base_files)) if restore_light else {}
    restored_keys = {name.lower() for name in restored_base}
    with tempfile.TemporaryDirectory() as folder, zipfile.ZipFile(version) as archive:
        for name in sorted(wanted):
            target = project.resolve(name)
            if name in archived:
                extracted = Path(archive.extract(f"ui/{name}", folder))
                source = extracted
            elif name in pinned:
                source = project.base_path(pinned[name])
            else:
                entry = official.get(name.lower())
                if entry is None:
                    result.unresolved.append(name)
                    continue
                source = _official_copy(project, name, entry)
                if source is None:
                    result.unresolved.append(name)
                    continue
            if not source.is_file():
                result.unresolved.append(name)
                continue
            if target.is_file() and target.read_bytes() == source.read_bytes():
                if name.lower() not in restored_keys:
                    project.materialize(project.ui_dir / name)
                continue
            project.write_from(name, source)
            if name in archived:
                result.written += 1
            else:
                result.reverted += 1
        if has_res_meta:
            res_config_source: Path | None = None
            if want_res_config:
                res_config_source = Path(archive.extract(multi_resolution.STORE_NAME, folder))
            res_writes: list[tuple[str, Path, bool]] = []
            for name in sorted(want_res_files):
                if name in res_pinned:
                    source = project.base_path(str(res_pinned[name]))
                    from_official = True
                else:
                    arcname = str(res_aliases.get(name, f"{multi_resolution.VARIANTS_DIR}/{name}"))
                    source = Path(archive.extract(arcname, folder))
                    from_official = False
                if not source.is_file():
                    result.unresolved.append(f"{multi_resolution.VARIANTS_DIR}/{name}")
                    continue
                res_writes.append((name, source, from_official))
            res_config_target = project.root / multi_resolution.STORE_NAME
            if want_res_config and res_config_source is not None:
                if not (res_config_target.is_file() and _same_content(res_config_source, res_config_target)):
                    if res_config_target.is_file():
                        _backup_project_file(project, res_config_target)
                    _atomic_copy(res_config_source, res_config_target)
                    result.written += 1
            elif not want_res_config and res_config_target.is_file():
                _backup_project_file(project, res_config_target)
                res_config_target.unlink()
                result.removed += 1
            for name, source, from_official in res_writes:
                target = _resolution_target(project, name)
                if target.is_file() and _same_content(source, target):
                    continue
                if target.is_file():
                    _backup_project_file(project, target)
                _atomic_copy(source, target)
                if from_official:
                    result.reverted += 1
                else:
                    result.written += 1
    for name, relative in current.items():
        if name not in wanted:
            path = project.ui_dir / relative
            if project.light:
                project.delete_file(path)
            else:
                shutil.copy2(path, project.history_path_for(path))
                path.unlink()
            result.removed += 1
    if has_res_meta:
        wanted_res_lower = {name.lower() for name in want_res_files}
        for name, relative in current_res.items():
            if name.lower() not in wanted_res_lower:
                path = project.root / multi_resolution.VARIANTS_DIR / relative
                if path.is_file():
                    _backup_project_file(project, path)
                    path.unlink()
                    result.removed += 1
        _prune_empty_dirs(project.root / multi_resolution.VARIANTS_DIR, remove_root=True)
    if not result.unresolved:
        project.light = restore_light
        project.base_files = restored_base
        project.deleted = {name.lower() for name in restored_base if name not in wanted}
    project.root_modes = dict(manifest.get("root_modes") or {})
    project.reference_layers = list(manifest.get("reference_layers") or [])
    project.save_manifest()
    if project.light and not result.unresolved:
        project.compact_base()
    text_data.save_edits(project.root, {
        name: {record_id: text_data.TextEdit(list(edit.get("fields", [])), list(edit.get("original", []))) for record_id, edit in records.items()}
        for name, records in (manifest.get("text_edits") or {}).items()
    })
    project.files(refresh=True)
    return result


def project_from_version(project: Project, version: Path, new_name: str) -> Path:
    """Novo projeto a partir de uma versão: duplica o projeto e restaura a versão na cópia."""
    from .project import duplicate_project

    target = duplicate_project(project.root, new_name)
    copy = Project.load(target)
    restore_version(copy, version)
    # A cópia não precisa da versão "antes de restaurar" (era o estado do original).
    for saved in list_versions(copy):
        if saved.label == "antes de restaurar":
            saved.path.unlink()
    storage.close_all()
    return target


def version_title(version: Version) -> str:
    """Rótulo para mostrar: o nome dado ou a data."""
    when = version.created.strftime("%d/%m/%Y %H:%M")
    return f"{version.label} · {when}" if version.label else when


__all__ = [
    "RestoreResult", "Version", "delete_version", "list_versions", "project_from_version",
    "restore_version", "save_version", "version_title", "versions_dir",
]
