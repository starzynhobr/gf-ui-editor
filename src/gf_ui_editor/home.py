"""Ordenação e dados dos projetos na tela inicial."""
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
import os
from pathlib import Path
import time

from . import storage


def is_same_root(a: Path | None, b: Path) -> bool:
    return a is not None and os.path.normcase(str(a)) == os.path.normcase(str(b))


def home_projects(roots: Iterable[Path], current_root: Path | None) -> list[tuple[Path, float]]:
    """Projeto aberto primeiro, seguido dos mais recentes, com a data de cada um."""
    projects = [(root, storage.last_modified(root)) for root in roots]
    return sorted(projects, key=lambda item: (not is_same_root(current_root, item[0]), -item[1]))


def project_disk_size(root: Path | str) -> int:
    total = 0
    for folder, _dirs, names in os.walk(root):
        for name in names:
            try:
                total += os.stat(os.path.join(folder, name)).st_size
            except OSError:
                pass
    return total


def human_size(size: int) -> str:
    if size >= 1024**3:
        return f"{size / 1024**3:.1f} GB"
    if size >= 1024**2:
        return f"{size / 1024**2:.0f} MB"
    return f"{max(1, size // 1024)} KB"


def relative_age(timestamp: float) -> tuple[str, int | str | None]:
    """Chave para a interface e valor, quando houver contagem ou data."""
    if not timestamp:
        return "date", None
    seconds = max(0.0, time.time() - timestamp)
    if seconds < 90:
        return "now", None
    if seconds < 3600:
        return "minutes", round(seconds / 60)
    if seconds < 86400:
        return "hours", round(seconds / 3600)
    days = int(seconds // 86400)
    if days == 1:
        return "yesterday", None
    if days < 30:
        return "days", days
    return "date", datetime.fromtimestamp(timestamp).strftime("%d/%m/%Y")


def pull_affects_open_file(ui_dir: Path, items: Iterable[tuple[str, Path]], open_path: Path | None) -> bool:
    return open_path is not None and any(is_same_root(open_path, ui_dir / relative) for relative, _ in items)
