"""Ordenação e dados dos projetos na tela inicial."""
from __future__ import annotations

from collections.abc import Callable, Iterable
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


# ---- dados prontos para a interface web (a clássica monta os mesmos com widgets) ----------
STZ_LABS_URL = "https://stzlabs.com"


def project_rows(roots: Iterable[Path], current_root: Path | None) -> list[dict]:
    """Linhas da lista de projetos: nome, arquivos, data de edição e se é o aberto."""
    rows = []
    for root, edited in home_projects(roots, current_root):
        title, files = storage.peek_project(root)
        rows.append({
            "root": str(root),
            "title": title or root.name,
            "files": files,
            "edited": edited,
            "age": list(relative_age(edited)),
            "current": is_same_root(current_root, root),
        })
    return rows


def continue_summary(project, last_file: str) -> dict:
    """Cartão "Continuar de onde parou" do projeto aberto (`project` é um project.Project)."""
    try:
        modified = len(project.modified_files())
    except OSError:
        modified = 0
    edited = storage.last_modified(project.root)
    return {
        "root": str(project.root),
        "name": project.name,
        "ui_dir": str(project.ui_dir),
        "last_file": Path(last_file).name if last_file else "",
        "modified": modified,
        "custom_name": project.custom_name,
        "has_game": project.game_dir is not None,
        "edited": edited,
        "age": list(relative_age(edited)),
    }


def news_titles(notes, language: str, limit: int = 3) -> list[str]:
    """Títulos das novidades da versão (`notes` é um release_notes.ReleaseNotes ou None)."""
    if notes is None:
        return []
    from .release_notes import SECTIONS

    sections = notes.for_language(language)
    titles = [title.rstrip(".") for section in SECTIONS for title, _text in sections.get(section, [])]
    return titles[:limit]


def how_to_url(language: str) -> str:
    """Página com o vídeo de "Como funciona"."""
    return f"{STZ_LABS_URL}/{'pt' if language == 'pt_BR' else 'en'}/projects/gf-ui-editor"


class SizeCache:
    """Tamanho em disco por projeto, válido enquanto a data de edição dele não muda."""

    def __init__(self) -> None:
        self._sizes: dict[str, tuple[float, int]] = {}

    def get(self, root: Path | str, edited: float) -> int | None:
        cached = self._sizes.get(str(root))
        return cached[1] if cached is not None and cached[0] == edited else None

    def pending(self, roots: Iterable[Path]) -> list[tuple[str, float]]:
        """Projetos sem tamanho guardado (ou com tamanho de uma edição anterior)."""
        result = []
        for root in roots:
            edited = storage.last_modified(root)
            if self.get(root, edited) is None:
                result.append((str(root), edited))
        return result

    def compute(self, pending: Iterable[tuple[str, float]], on_size: Callable[[str, int], None]) -> None:
        """Calcula (devagar, fora da tela) e avisa cada um assim que fica pronto."""
        for key, edited in pending:
            size = project_disk_size(key)
            self._sizes[key] = (edited, size)
            on_size(key, size)

    def forget(self, root: Path | str) -> None:
        self._sizes.pop(str(root), None)
