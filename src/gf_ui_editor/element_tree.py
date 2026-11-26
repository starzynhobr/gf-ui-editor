"""Dados da árvore de elementos e do painel que o canvas não manda, sem Qt.

O canvas recebe geometria, textura e textos de preview (canvas_document). A árvore precisa
também do rótulo que o jogo mostra em cada controle (coluna Tipo: "Botão · Nome"), do
WindowText (título do painel) e do texto que o filtro procura (text_preview.search_text).
O rótulo do tipo é traduzido na interface e chega pronto em ``kinds``.
"""

from __future__ import annotations

from pathlib import Path

from . import game_texts, text_preview
from .canvas_document import _preview_context
from .xml_document import UIDocument

TREE_COLUMNS = ("0", "2")  # colunas que dá para esconder: WindowID e ParentNode


def tree_rows(path: Path, kinds: list[str]) -> list[dict]:
    """Por elemento: rótulo do jogo, WindowText e o texto (casefold) que o filtro procura."""
    document = UIDocument.load(path)
    game_dir, _mode, overrides = _preview_context(document.path)
    labels = game_texts.labels_for(document.path.name, game_dir, overrides)
    rows = []
    for element in document.elements:
        label = labels.get(element.window_id, "").strip()
        kind = kinds[element.index] if element.index < len(kinds) else element.kind
        rows.append({
            "index": element.index,
            "label": label,
            "text": element.window_text,
            "search": text_preview.search_text(element, kind, labels.get(element.window_id, "")),
        })
    return rows


def hidden_columns(saved: list[str]) -> list[str]:
    """Colunas escondidas válidas (o padrão da clássica esconde ParentNode)."""
    return [column for column in saved if column in TREE_COLUMNS]
