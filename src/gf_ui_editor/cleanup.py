"""Limpar projeto: libera espaço sem deixar o projeto incompleto.

O projeto continua com todos os arquivos que o editor usa para desenhar (inclusive o `map`):
o editor lê as texturas da pasta `ui/` do projeto, e o F5 deixa a pasta UI do jogo igual a ela.
O que pode sair:
- backups do `.history` (os antigos ou todos); os originais (`original.*`) ficam, porque são
  a cópia oficial usada para desfazer e para restaurar versões;
- pastas de ícones do jogo (itemicon, skillicon…) trazidas com "incluir ícones" na criação,
  só os arquivos iguais ao oficial; ícones editados ficam;
- na cópia do jogo (`UICustom/<nome>`, só a pasta própria do projeto), os arquivos que não
  precisam estar lá: os iguais ao oficial e os que o projeto não tem mais (o mesmo que o F5 faz);
- arquivos temporários esquecidos (`*.gf-ui-editor.tmp`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import time

from . import gamedata
from .project import GAME_ASSET_FOLDERS, ORIGINAL_NAME, Project, owned_custom_folder

OLD_DAYS = 30
TEMP_SUFFIX = ".gf-ui-editor.tmp"


@dataclass
class CleanupPlan:
    history_old: list[Path] = field(default_factory=list)  # backups com mais de OLD_DAYS dias
    history_all: list[Path] = field(default_factory=list)  # todos os backups (sem os originais)
    icons: list[Path] = field(default_factory=list)  # ícones do jogo iguais ao oficial
    icons_left: int = 0  # ícones editados que ficam
    custom: list[Path] = field(default_factory=list)  # sobras em UICustom/<nome>
    custom_dir: Path | None = None
    temporary: list[Path] = field(default_factory=list)


@dataclass
class CleanupResult:
    removed: int = 0
    freed: int = 0


def size_of(paths: list[Path]) -> int:
    total = 0
    for path in paths:
        try:
            total += path.stat().st_size
        except OSError:
            pass
    return total


def folder_size(folder: Path) -> int:
    total = 0
    for current, _dirs, names in os.walk(folder):
        for name in names:
            try:
                total += os.stat(os.path.join(current, name)).st_size
            except OSError:
                pass
    return total


def _walk(folder: Path):
    for current, _dirs, names in os.walk(folder):
        for name in names:
            yield Path(current, name)


def scan(project: Project, days: int = OLD_DAYS, progress=None) -> CleanupPlan:
    plan = CleanupPlan()
    limit = time.time() - days * 86400
    if project.history_dir.is_dir():
        for path in _walk(project.history_dir):
            if path.stem.startswith(ORIGINAL_NAME):
                continue
            plan.history_all.append(path)
            try:
                if path.stat().st_mtime < limit:
                    plan.history_old.append(path)
            except OSError:
                pass
    official = gamedata.official_ui_files(project.game_dir) if project.game_dir is not None else {}
    if project.include_assets and official and project.ui_dir.is_dir():
        for folder in project.ui_dir.iterdir():
            if not folder.is_dir() or folder.name.lower() not in GAME_ASSET_FOLDERS:
                continue
            for path in _walk(folder):
                relative = path.relative_to(project.ui_dir).as_posix()
                if gamedata.is_official(path, relative, official):
                    plan.icons.append(path)
                else:
                    plan.icons_left += 1
    if not project.publish_folder:
        custom_dir = owned_custom_folder(project)
        if custom_dir is not None:
            shipped, _skipped = project.shipped_files(progress)
            wanted = {relative.as_posix().lower() for relative in shipped}
            plan.custom_dir = custom_dir
            plan.custom = [
                path for path in _walk(custom_dir) if path.relative_to(custom_dir).as_posix().lower() not in wanted
            ]
    plan.temporary = [path for path in _walk(project.root) if path.name.endswith(TEMP_SUFFIX)]
    return plan


def _remove(paths: list[Path], result: CleanupResult) -> None:
    for path in paths:
        try:
            size = path.stat().st_size
            path.unlink()
        except OSError:
            continue
        result.removed += 1
        result.freed += size


def _prune_empty(folder: Path | None) -> None:
    if folder is None or not folder.is_dir():
        return
    for current, dirs, files in os.walk(folder, topdown=False):
        if current != str(folder) and not dirs and not files:
            try:
                os.rmdir(current)
            except OSError:
                pass


def apply(project: Project, plan: CleanupPlan, *, history: str | None = None, icons: bool = False, custom: bool = False) -> CleanupResult:
    """Apaga o escolhido. `history`: None, "old" (os antigos) ou "all" (todos os backups)."""
    result = CleanupResult()
    if history == "all":
        _remove(plan.history_all, result)
    elif history == "old":
        _remove(plan.history_old, result)
    if history:
        _prune_empty(project.history_dir)
    if icons and plan.icons:
        _remove(plan.icons, result)
        _prune_empty(project.ui_dir)
        # Sem nenhum ícone editado, o projeto volta a ser "sem ícones" (como na criação padrão).
        remaining = any(
            folder.is_dir() and folder.name.lower() in GAME_ASSET_FOLDERS and any(_walk(folder))
            for folder in project.ui_dir.iterdir()
        )
        if not remaining:
            project.include_assets = False
            project.save_manifest()
        project.invalidate_changes()
        project.files(refresh=True)
    if custom and plan.custom:
        _remove(plan.custom, result)
        _prune_empty(plan.custom_dir)
    _remove(plan.temporary, result)
    return result


__all__ = ["CleanupPlan", "CleanupResult", "OLD_DAYS", "apply", "folder_size", "scan", "size_of"]
