"""Texture names and file operations shared by the editors."""

from __future__ import annotations

from pathlib import Path
import shutil
from typing import TYPE_CHECKING

from .file_list import is_texture

if TYPE_CHECKING:
    from .project import Project


def ui_texture_names(folder: Path, project: Project | None = None) -> list[str]:
    if project is not None and project.light:
        names = {
            path.name.lower(): path.name for path in project.base_files_in(folder)
            if is_texture(path)
        }
        if folder.is_dir():
            names.update({path.name.lower(): path.name for path in folder.iterdir() if is_texture(path) and path.is_file()})
        return sorted(names.values(), key=str.lower)
    return sorted(
        (path.name for path in folder.iterdir() if is_texture(path) and path.is_file()),
        key=str.lower,
    )


def backup_texture_for_edit(project: Project | None, target: Path) -> None:
    """Save the original and a history entry before replacing an existing texture."""
    if project is not None and project.contains(target):
        project.materialize(target)
        project.remember_original(target)
        shutil.copy2(target, project.history_path_for(target))


def copy_texture_for_edit(project: Project | None, source: Path, name: str | Path) -> Path:
    """Copy into a project's UI with history, or directly to a destination path if project is None."""
    target = project.ui_dir / name if project is not None else Path(name)
    if project is not None:
        project.write_from(name, source)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return target


# ---- trocar a textura de um controle (o mesmo menu "Trocar .dds…" das duas interfaces) ----
def find_texture(folder: Path, name: str, project: Project | None = None) -> Path | None:
    """Arquivo da textura na pasta da UI, sem diferenciar maiúsculas (como o jogo)."""
    if not name:
        return None
    direct = folder / name.replace("\\", "/")
    if direct.is_file():
        return direct
    if (project is None or not project.light) and not direct.parent.is_dir():
        return None
    wanted = direct.name.lower()
    return next((direct.parent / item for item in ui_texture_names(direct.parent, project) if item.lower() == wanted), None)


def copy_suggestion(current: str) -> str:
    """Nome sugerido para a cópia editável: Botao.dds -> Botao_custom.dds."""
    path = Path(current)
    return f"{path.stem}_custom{path.suffix or '.dds'}"


def with_texture_suffix(name: str) -> str:
    name = name.strip()
    return name if name.lower().endswith((".dds", ".tga")) else name + ".dds"


def copy_for_edit(folder: Path, current: str, name: str, project: Project | None = None) -> Path:
    """Cria uma cópia de `current` com outro nome na pasta da UI. Erro se já existe."""
    source = find_texture(folder, current, project)
    if source is None:
        raise FileNotFoundError(current)
    target = folder / with_texture_suffix(name)
    if find_texture(folder, target.name, project) is not None:
        raise FileExistsError(target.name)
    if project is not None:
        return copy_texture_for_edit(project, project.read_path(source), project.relative_key(target))
    return copy_texture_for_edit(None, source, target)


def bring_target(folder: Path, source: Path, project: Project | None = None) -> tuple[Path, bool]:
    """Destino de um .dds trazido de fora e se ele substitui outro (o mesmo arquivo não conta)."""
    existing = find_texture(folder, source.name, project)
    target = existing or folder / source.name
    same = existing is not None and source.resolve() == target.resolve()
    return target, existing is not None and not same


def bring_texture(project: Project | None, folder: Path, source: Path) -> Path:
    """Copia um .dds de outra pasta para a UI; o que for substituído vai para o histórico."""
    target, _replacing = bring_target(folder, source, project)
    if source.resolve() == target.resolve():
        return target
    if project is not None:
        return copy_texture_for_edit(project, source, project.relative_key(target))
    return copy_texture_for_edit(None, source, target)
