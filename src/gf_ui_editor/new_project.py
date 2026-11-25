"""Opções do diálogo "Novo projeto", sem Qt.

O mesmo que o `NewProjectDialog` da interface clássica calcula (origens, pastas de envio,
avisos e nome sugerido), em dados, para a interface web. A criação em si é
``project.create_from_source``.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from .game_layout import looks_like_game_dir, normalize_game_dir
from .project import custom_ui_sources, is_backup_file, projects_publishing_to, safe_name


@dataclass(frozen=True)
class Source:
    label: str  # "UI" (UI em uso no jogo) ou "UICustom/<nome>"
    path: Path

    @property
    def is_game_ui(self) -> bool:
        return self.label == "UI"


def sources(game_dir: Path | None) -> list[Source]:
    """UIs da pasta do jogo que podem servir de ponto de partida (sem "outra pasta"/".zip")."""
    if game_dir is None:
        return []
    return [Source(label, path) for label, path in custom_ui_sources(game_dir)]


def game_dir_warning(game_dir: Path | None) -> bool:
    """A pasta escolhida não parece ser a do jogo (sem client.ini nem Launcher.ini)."""
    return game_dir is not None and not looks_like_game_dir(game_dir)


def chosen_game_dir(path: Path) -> Path:
    """Quem escolhe a pasta UI ou UICustom recebe a raiz do jogo."""
    return normalize_game_dir(path)


def origin_folder(source_label: str) -> str:
    """Pasta de UICustom de onde o projeto parte ("" se não for uma UI do UICustom)."""
    return source_label.split("/", 1)[1] if source_label.startswith("UICustom/") else ""


def publish_targets(name: str, source_label: str) -> list[tuple[str, str]]:
    """Destinos do Enviar para o jogo: (valor, nome da pasta). Valor "" = pasta própria."""
    own = safe_name(name.strip()) if name.strip() else ""
    targets = [("", own)]
    origin = origin_folder(source_label)
    if origin:
        targets.append((origin, origin))
    return targets


def publish_warning(
    publish_folder: str, name: str, game_dir: Path | None, projects_root: Path | None = None
) -> tuple[str, dict[str, str]] | None:
    """Aviso sobre a pasta de envio: ("shared", outros projetos) ou ("exists", pasta)."""
    folder = publish_folder or (safe_name(name.strip()) if name.strip() else "")
    if not folder:
        return None
    others = projects_publishing_to(folder, projects_root=projects_root)
    if others:
        return "shared", {"projects": ", ".join(others), "folder": folder}
    if not publish_folder and game_dir is not None and (game_dir / "UICustom" / folder).is_dir():
        return "exists", {"folder": folder}
    return None


def suggested_name(current: str, source_label: str = "", picked: Path | None = None) -> str:
    """Nome sugerido quando o campo está vazio: a UI de UICustom, a pasta ou o .zip escolhido."""
    if current.strip():
        return current
    if picked is not None:
        return picked.stem if picked.suffix.lower() == ".zip" else picked.name
    return origin_folder(source_label)


def loose_files(loose_dir: Path | None, game_sources: list[Source]) -> list[Path]:
    """XMLs soltos que entram por cima da UI de partida (vazio se a pasta já é uma origem)."""
    if loose_dir is None:
        return []
    if any(os.path.normcase(str(source.path)) == os.path.normcase(str(loose_dir)) for source in game_sources):
        return []
    return sorted(
        (path for path in loose_dir.glob("*.xml") if not is_backup_file(path.name)), key=lambda path: path.name.lower()
    )


def projects_root() -> Path:
    """Onde os projetos novos são criados (lido na hora: os testes trocam o PROJECTS_ROOT)."""
    from . import project

    return project.PROJECTS_ROOT


__all__ = [
    "Source", "chosen_game_dir", "game_dir_warning", "loose_files", "origin_folder",
    "projects_root", "publish_targets", "publish_warning", "sources", "suggested_name",
]
