"""Lista de arquivos do projeto (ou da pasta solta), sem Qt.

Monta o que a lista de Arquivos XML/Texturas mostra (arquivos, alterados, camadas), a
ordem das seções e as buscas de textura usadas ao renomear ou apagar. A interface Qt
(e a web, no futuro) só desenha o resultado.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import difflib
import json
import os
from pathlib import Path
import re
import shutil
from typing import TYPE_CHECKING

from .game_updates import official_text_for
from .project import is_backup_file, projects_publishing_to

if TYPE_CHECKING:
    from .project import Project

TEXTURE_SUFFIXES = (".dds", ".tga")
FILE_SECTIONS = ("layers", "changed", "all")  # ordem padrão das seções na lista de arquivos


def is_texture(path: Path) -> bool:
    return path.suffix.lower() in TEXTURE_SUFFIXES


@dataclass
class FileListing:
    """Arquivos relativos à pasta da UI. `modified` usa o caminho posix como chave."""

    xml: list[Path] = field(default_factory=list)
    textures: list[Path] = field(default_factory=list)
    modified: set[str] = field(default_factory=set)
    shared_publish: list[str] = field(default_factory=list)  # outros projetos com a mesma pasta de UICustom


def project_listing(project: "Project") -> FileListing:
    modified = project.modified_files()
    xml = [path for path in project.files() if path.suffix.lower() == ".xml"]
    # Só as da pasta principal da UI: as de subpastas (mapas, ícones) são milhares.
    textures = [path for path in project.files() if is_texture(path) and len(path.parts) == 1]
    shared = (
        projects_publishing_to(project.custom_name, exclude=project.root) if project.game_dir is not None else []
    )
    return FileListing(xml, textures, modified, shared)


def loose_listing(directory: Path | None) -> FileListing:
    """XMLs soltos de uma pasta (sem projeto): sem texturas nem alterados."""
    if directory is None:
        return FileListing()
    xml = sorted(
        (path.relative_to(directory) for path in directory.glob("*.xml") if not is_backup_file(path.name)),
        key=lambda item: item.as_posix().lower(),
    )
    return FileListing(xml)


def file_groups(files: list[Path], modified: set[str], layers: set[str]) -> dict[str, list[Path]]:
    """Arquivos de cada seção, na ordem padrão (camadas, alterados, todos)."""
    return {
        # Camadas marcadas no topo: fica fácil ver o que está ligado e desmarcar.
        "layers": [path for path in files if path.as_posix() in layers],
        "changed": [path for path in files if path.as_posix() in modified],
        "all": files,
    }


# ---- ordem e altura das seções ----------------------------------------------------------
def parse_section_order(value: str) -> list[str]:
    """Ordem salva ("all,layers,changed"); a padrão se faltar ou sobrar alguma seção."""
    order = [kind for kind in value.split(",") if kind in FILE_SECTIONS]
    return order if sorted(order) == sorted(FILE_SECTIONS) else list(FILE_SECTIONS)


def is_valid_section_order(order: list[str]) -> bool:
    return sorted(order) == sorted(FILE_SECTIONS)


def merge_hidden(order: list[str], visible_order: list[str], hidden: list[str]) -> list[str]:
    """Põe as seções escondidas (vazias) de volta, onde estavam em relação às outras em `order`."""
    merged = list(visible_order)
    for item in hidden:
        previous = order.index(item)
        # Põe logo depois da seção que vinha antes dela na ordem antiga.
        anchor = next((other for other in reversed(order[:previous]) if other in merged), None)
        merged.insert(merged.index(anchor) + 1 if anchor is not None else 0, item)
    return merged


def _with_hidden(order: list[str], visible_order: list[str], visible: list[str]) -> list[str]:
    hidden = [item for item in order if item not in visible]
    return merge_hidden(order, visible_order, hidden) if hidden else visible_order


def order_after_drop(order: list[str], visible: list[str], kind: str, index: int) -> list[str] | None:
    """Nova ordem ao soltar `kind` na posição `index` entre as visíveis; None se nada muda."""
    target = [item for item in visible if item != kind]
    before = visible[index] if index < len(visible) else None
    if before == kind:
        return None
    position = target.index(before) if before is not None else len(target)
    target.insert(position, kind)
    return _with_hidden(order, target, visible)


def order_after_move(order: list[str], visible: list[str], kind: str, step: int) -> list[str] | None:
    """Nova ordem ao subir (-1) ou descer (+1) `kind` entre as visíveis; None se não dá."""
    if kind not in visible:
        return None
    moved = list(visible)
    index = moved.index(kind)
    swap = index + step
    if not 0 <= swap < len(moved):
        return None
    moved[index], moved[swap] = moved[swap], moved[index]
    return _with_hidden(order, moved, visible)


def parse_section_heights(value: str) -> dict[str, int]:
    """Alturas salvas das seções (JSON {"layers": 120, ...}); {} se inválido."""
    try:
        data = json.loads(value)
    except ValueError:
        return {}
    return {str(key): int(item) for key, item in data.items() if isinstance(item, (int, float))} if isinstance(data, dict) else {}


# ---- texturas e histórico ----------------------------------------------------------------
def xml_using_texture(project: "Project", name: str) -> list[Path]:
    """XMLs do projeto com BGmap apontando para a textura `name`."""
    pattern = re.compile(rb'BGmap\s*=\s*"' + re.escape(name.encode("latin-1", "ignore")) + rb'"', re.IGNORECASE)
    found = []
    for relative in project.files():
        if relative.suffix.lower() != ".xml":
            continue
        path = project.ui_dir / relative
        try:
            if pattern.search(path.read_bytes()):
                found.append(path)
        except OSError:
            continue
    return found


def retarget_texture(project: "Project", paths: list[Path], old: str, new: str) -> None:
    """Troca BGmap="old" por BGmap="new" mexendo só nesse atributo, com backup de cada XML."""
    pattern = re.compile(r'(BGmap\s*=\s*")' + re.escape(old) + r'(")', re.IGNORECASE)
    for path in paths:
        try:
            raw = path.read_bytes()
            text = raw.decode("big5")
        except (OSError, UnicodeDecodeError):
            continue
        changed = pattern.sub(lambda match: match.group(1) + new + match.group(2), text)
        if changed == text:
            continue
        project.remember_original(path)
        shutil.copy2(path, project.history_path_for(path))
        path.write_bytes(changed.encode("big5"))
    project.invalidate_changes()


def history_entries(project: "Project | None", path: Path) -> tuple[list[Path], Path | None]:
    """Backups (mais recente primeiro) e o original, se houver."""
    if project is not None and project.contains(path):
        original = project.original_path_for(path)
        return project.history(path), original if original.exists() else None
    backups = sorted(
        path.parent.glob(f"{path.stem}.before-gf-ui-editor-*{path.suffix}"), key=lambda item: item.name, reverse=True
    )
    return backups, None


def backup_stamp(backup: Path) -> datetime | None:
    """Data e hora gravadas no nome do backup (…-AAAAMMDD-HHMMSS…), se houver."""
    match = re.search(r"(\d{8})-(\d{6})", backup.name)
    if not match:
        return None
    return datetime.strptime(match[1] + match[2], "%Y%m%d%H%M%S")


# ---- importar, renomear, apagar, restaurar -----------------------------------------------
INVALID_NAME_CHARS = '\\/:*?"<>|'


def has_invalid_chars(name: str) -> bool:
    return any(char in name for char in INVALID_NAME_CHARS)


def rename_target(path: Path, name: str) -> tuple[Path, bool]:
    """Destino ao renomear `path` para `name` (sem extensão, mantém a atual) e se ele
    substitui outro arquivo (mudar só maiúsculas/minúsculas não substitui)."""
    if not Path(name).suffix:
        name += path.suffix
    target = path.with_name(name)
    replacing = target.exists() and os.path.normcase(str(target)) != os.path.normcase(str(path))
    return target, replacing


@dataclass
class DeleteWarning:
    official: bool = False  # o XML existe na UI oficial
    texture_users: int = 0  # XMLs do projeto que ainda usam a textura


def delete_warning(project: "Project", path: Path) -> DeleteWarning:
    """O que avisar antes de apagar um arquivo do projeto."""
    game_dir = project.game_dir
    if path.suffix.lower() == ".xml" and game_dir is not None:
        relative = project.relative_key(path)
        return DeleteWarning(official=official_text_for(game_dir, relative) is not None)
    if is_texture(path):
        return DeleteWarning(texture_users=len(xml_using_texture(project, path.name)))
    return DeleteWarning()


def import_plan(project: "Project", sources: list[Path]) -> tuple[dict[Path, Path], list[Path]]:
    """Destino de cada arquivo importado e os que já existem no projeto (serão substituídos)."""
    targets = {source: project.import_target(source) for source in sources}
    replaced = [target for target in targets.values() if target.exists()]
    return targets, replaced


def restore_diff(path: Path, source: Path, current_label: str, restored_label: str) -> str:
    """Diff unificado entre o arquivo atual e a versão a restaurar; vazio se iguais.

    Erros de leitura (OSError) sobem para quem chamou.
    """
    current = path.read_bytes().decode("big5", errors="replace").splitlines()
    restored = source.read_bytes().decode("big5", errors="replace").splitlines()
    return "\n".join(
        difflib.unified_diff(current, restored, fromfile=current_label, tofile=restored_label, lineterm="")
    )


def restore_file(project: "Project | None", path: Path, source: Path, now: datetime | None = None) -> None:
    """Volta `path` para `source`. No projeto o estado atual vai para o histórico; num XML
    solto fica um backup `.before-gf-ui-editor-…` ao lado."""
    if project is not None and project.contains(path):
        project.restore(path, source)
        return
    backup = path.with_name(
        f"{path.stem}.before-gf-ui-editor-{(now or datetime.now()):%Y%m%d-%H%M%S}{path.suffix}"
    )
    shutil.copy2(path, backup)
    shutil.copy2(source, path)


# ---- dados para a interface web ------------------------------------------------------------
def sections_payload(
    listing: FileListing, mode: str, layers: set[str], order_value: str, heights_value: str
) -> dict:
    """Lista de Arquivos XML ou Texturas em dados: cada arquivo uma vez, as seções por índice.

    Com ícones são ~18 mil arquivos; repetir os caminhos em "Alterados" e "Todos" dobraria o
    que passa pela ponte. As seções vêm na ordem salva; a interface esconde as vazias
    (menos "Todos"). Sem texturas, o modo cai para XML, como na clássica.
    """
    if mode == "textures" and not listing.textures:
        mode = "xml"
    files = listing.textures if mode == "textures" else listing.xml
    index = {path.as_posix(): position for position, path in enumerate(files)}
    groups = file_groups(files, listing.modified, layers if mode == "xml" else set())
    return {
        "mode": mode,
        "files": list(index),
        "modified": [index[key] for key in index if key in listing.modified],
        "layers": [index[key] for key in index if key in layers] if mode == "xml" else [],
        "sections": [
            {"kind": kind, "items": [index[path.as_posix()] for path in groups[kind]]}
            for kind in parse_section_order(order_value)
        ],
        "heights": parse_section_heights(heights_value),
        "has_textures": bool(listing.textures),
        "shared_publish": list(listing.shared_publish),
    }
