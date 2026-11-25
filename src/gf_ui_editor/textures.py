"""Texture names and file operations shared by the editors."""

from __future__ import annotations

from pathlib import Path
import shutil
from typing import TYPE_CHECKING

from .file_list import is_texture

if TYPE_CHECKING:
    from .project import Project


def ui_texture_names(folder: Path) -> list[str]:
    return sorted(
        (path.name for path in folder.iterdir() if is_texture(path) and path.is_file()),
        key=str.lower,
    )


def backup_texture_for_edit(project: Project | None, target: Path) -> None:
    """Save the original and a history entry before replacing an existing texture."""
    if project is not None and project.contains(target):
        project.remember_original(target)
        shutil.copy2(target, project.history_path_for(target))


def copy_texture_for_edit(project: Project | None, source: Path, name: str | Path) -> Path:
    """Copy into a project's UI with history, or directly to a destination path if project is None."""
    target = project.ui_dir / name if project is not None else Path(name)
    if project is not None and target.exists():
        backup_texture_for_edit(project, target)
    shutil.copy2(source, target)
    return target
