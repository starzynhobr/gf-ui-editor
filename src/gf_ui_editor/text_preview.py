"""Que texto o canvas mostra em cada controle, sem Qt.

O modo de texto ("off", "game", "xml", "short", "long") decide entre o rótulo que o jogo
escreve, o WindowText do XML e uma amostra para medir o espaço. As amostras saem como
``SHORT``/``LONG``: a interface troca pelos textos traduzidos.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .xml_document import UIElement


class Sample(Enum):
    SHORT = "short"  # "Texto"
    LONG = "long"  # "Texto de exemplo bem comprido para testar o espaço"


SHORT = Sample.SHORT
LONG = Sample.LONG

Labels = Mapping[str, str]


def takes_text(element: "UIElement") -> bool:
    """O jogo só escreve o WindowText em controles de texto ou botões; painéis e a raiz
    guardam ali só um nome interno ("PX1-1")."""
    return "TextNode" in element.child_tags or "ButtonNode" in element.child_tags


def element_text(
    element: "UIElement", mode: str, labels: Labels | Callable[[], Labels], sample: str | None = None
) -> str | Sample:
    """Texto do controle no canvas.

    ``labels``: WindowID -> rótulo que o jogo escreve (ou uma função que o calcula; só é
    chamada no modo "game"). ``sample``: texto do personagem de exemplo (nick, nível, HP/MP),
    quando ele está visível; vale antes de tudo.
    """
    if sample:
        # Nick, nível e HP/MP vêm dos dados do jogador, não do XML nem do T_TextIndex.
        return sample
    if mode == "off":
        return ""
    if mode == "game":
        # O jogo troca o WindowText pelo rótulo que o código escreve, quando há um.
        fallback = element.window_text if takes_text(element) else ""
        return (labels() if callable(labels) else labels).get(element.window_id, fallback)
    if element.window_text or mode == "xml":
        return element.window_text
    if not takes_text(element):
        return ""
    if not element.text_props or element.width < 4:
        return ""
    if mode == "short":
        return SHORT
    return LONG


def layer_text(element: "UIElement", labels: Labels, sample: str | None = None) -> str:
    """Texto de um controle numa camada de referência (rótulo do jogo, senão o WindowText)."""
    text = labels.get(element.window_id, element.window_text if takes_text(element) else "")
    return sample or text


def search_text(element: "UIElement", kind: str, game_label: str) -> str:
    """O que o filtro da árvore de elementos procura, já em casefold.

    ``kind`` é o rótulo traduzido do tipo (vem do i18n, que usa Qt).
    """
    return " ".join(
        (
            element.window_id,
            kind,
            element.parent_id or "",
            element.window_text,
            element.texture_name or "",
            element.ctrl_type or "",
            game_label,
        )
    ).casefold()
