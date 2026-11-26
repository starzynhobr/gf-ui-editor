"""Enviar para o jogo (F5), sem Qt.

A UI vai por ``Project.publish`` (UICustom, pasta UI e Launcher.ini); os textos editados
vão para data/Translate, porque o launcher pode ter baixado os originais de novo. A
interface só pergunta, mostra o progresso e avisa o resultado.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Iterable

from . import text_data

if TYPE_CHECKING:
    from .game_updates import FileDiff
    from .project import Progress, Project, PublishResult


@dataclass
class TextsOutcome:
    changed: int = 0  # arquivos de data/Translate regravados
    warnings: list[str] = field(default_factory=list)  # textos editados que o jogo não tem mais
    blocked: bool = False  # havia textos, mas o envio deles está desligado pelo manifesto remoto


@dataclass
class PublishOutcome:
    result: "PublishResult"
    texts: TextsOutcome


def pending_new_controls(official_diffs: Iterable["FileDiff"]) -> list[str]:
    """Arquivos sem controles que a atualização do jogo trouxe (o jogo pode acusar erro)."""
    return sorted(diff.relative for diff in official_diffs if diff.new_ids)


def _snapshot_official_texts(game_dir, edits: dict) -> None:
    """Antes de gravar as edições, guarda o retrato dos arquivos que ainda são os oficiais.

    Depois do envio o arquivo do jogo tem as edições e não serve mais de referência para o
    aviso de atualização dos textos (game_text_updates). Falhar aqui não impede o envio.
    """
    try:
        from . import game_text_updates
        from . import project as project_module

        crcs = game_text_updates.official_crcs(game_dir)
        wanted = {name: crc for name, crc in crcs.items() if name in edits}
        game_text_updates.TextSnapshots(project_module.PROJECTS_ROOT).capture(game_dir, wanted)
    except Exception:  # noqa: BLE001 - o retrato é só para o aviso; o envio segue
        pass


def publish_texts(project: "Project", texts_disabled: bool, now: datetime | None = None) -> TextsOutcome:
    """Grava os textos editados do projeto no jogo, com cópia do anterior no histórico.

    Erros de disco (OSError) sobem para quem chamou, como os de ``Project.publish``.
    """
    edits = text_data.load_edits(project.root)
    blocked = bool(edits) and texts_disabled
    if blocked:
        edits = {}  # textos desligados pelo manifesto: a UI segue sendo enviada
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    if edits:
        _snapshot_official_texts(project.game_dir, edits)
    changed, warnings = text_data.publish_edits(
        project.game_dir, edits, project.history_dir / "data" / stamp
    ) if edits else (0, [])
    # Textos que voltaram ao original já foram gravados no jogo: a edição sai do projeto.
    kept = {
        name: {record_id: edit for record_id, edit in records.items() if edit.fields != edit.original}
        for name, records in edits.items()
    }
    if kept != edits:
        text_data.save_edits(project.root, kept)
    return TextsOutcome(changed, warnings, blocked)


def publish_project(project: "Project", texts_disabled: bool, progress: "Progress" = None) -> PublishOutcome:
    """UI e textos de uma vez (a interface Qt chama as duas partes separadas, com progresso só na UI)."""
    result = project.publish(progress=progress)
    return PublishOutcome(result, publish_texts(project, texts_disabled))


def needs_launcher_selection(result: "PublishResult", custom_name: str) -> bool:
    """Launcher aberto com outra UI selecionada: ele reaplicaria a anterior ao clicar Jogar."""
    return result.launcher_running and result.previous_selection != f"custom:{custom_name}"
