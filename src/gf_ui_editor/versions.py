"""Versões do projeto (checkpoints): um .zip pequeno com o que difere do oficial.

"Salvar versão" guarda em `<projeto>/.versions/` um .zip com:
- `ui/…`: só os arquivos do projeto que diferem da UI oficial (CRC do GameDataFileList.txt),
  a mesma regra do F5 e do Exportar .zip (vault/launcher.md); o STZ-UI inteiro cabe em ~6,5 MB;
- `version.json`: nome, rótulo, data, a lista completa de arquivos do projeto, camadas, modos
  da raiz e os textos editados.

"Restaurar" deixa o projeto como estava: grava os arquivos do .zip, devolve ao oficial os que
eram oficiais naquela versão (procurando a cópia oficial no próprio histórico do projeto, na
pasta UI do jogo ou no cache .official-ui) e tira os que não existiam. Tudo que é trocado
ou removido vai antes para o .history. Antes de restaurar, a versão atual é salva sozinha.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import tempfile
import zipfile

from . import __version__, gamedata, storage, text_data
from .project import Project, safe_name

VERSIONS_DIR = ".versions"
FORMAT = 1
MANIFEST = "version.json"


@dataclass(frozen=True)
class Version:
    path: Path
    label: str
    created: datetime
    files: int  # arquivos guardados no .zip (os que diferem do oficial)
    size: int  # tamanho do .zip


@dataclass
class RestoreResult:
    written: int = 0  # arquivos gravados a partir da versão
    reverted: int = 0  # voltaram ao oficial
    removed: int = 0  # não existiam na versão
    unresolved: list[str] = field(default_factory=list)  # oficial não encontrado: ficaram como estavam


def versions_dir(project: Project) -> Path:
    return project.root / VERSIONS_DIR


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
    if project.light:
        official = gamedata.official_ui_files(project.game_dir) if project.game_dir is not None else {}
        archived = set(shipped)
        official_files = {}
        for relative in files:
            if relative in archived:
                continue
            key = relative.as_posix()
            source = project.resolve(relative)
            blob = project.base_files.get(key)
            if blob is None or source != project.base_path(blob):
                blob = project.cache_official(source, key, official)
            if blob is None:
                raise ValueError(f"A UI oficial mudou durante o salvamento: {key}")
            official_files[key] = blob
    if official_files is not None:
        manifest.update(light=project.light, official_files=official_files, base_files=project.base_files)
    temporary = target.with_name(f".{target.name}.tmp")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=1))
        for relative in shipped:
            archive.write(project.resolve(relative), f"ui/{relative.as_posix()}")
    os.replace(temporary, target)
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
        result.append(Version(path, str(manifest.get("label") or ""), created, len(manifest.get("shipped", [])), path.stat().st_size))
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
    save_version(project, "antes de restaurar")
    result = RestoreResult()
    official = gamedata.official_ui_files(project.game_dir) if project.game_dir is not None else {}
    wanted = {str(name) for name in manifest.get("files", [])}
    shipped = {str(name) for name in manifest.get("shipped", [])}
    current = {relative.as_posix(): relative for relative in project.files(refresh=True)}
    restore_light = bool(manifest.get("light", project.light))
    pinned = dict(manifest.get("official_files") or {})
    restored_base = dict(manifest.get("base_files", project.base_files)) if restore_light else {}
    if restore_light:
        restored_base = {**pinned, **restored_base}
    for name in wanted:
        project.resolve(name)  # Validate paths before extracting or writing anything.
    with tempfile.TemporaryDirectory() as folder, zipfile.ZipFile(version) as archive:
        for name in sorted(wanted):
            target = project.resolve(name)
            if name in shipped:
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
                if not restore_light:
                    project.materialize(project.ui_dir / name)
                continue
            project.write_from(name, source)
            if name in shipped:
                result.written += 1
            else:
                result.reverted += 1
    for name, relative in current.items():
        if name not in wanted:
            path = project.ui_dir / relative
            if project.light:
                project.delete_file(path)
            else:
                shutil.copy2(path, project.history_path_for(path))
                path.unlink()
            result.removed += 1
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
