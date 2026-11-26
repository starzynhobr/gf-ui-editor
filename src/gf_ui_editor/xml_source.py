"""Texto do XML aberto como ele ficaria ao salvar ("Ver código XML" da interface nova).

Sem Qt. Devolve o texto renderizado (com as edições ainda não salvas) e, para cada
elemento, a linha (1 em diante) da tag <BaseWndProperty> dele nesse texto, para o painel de
código levar à linha do elemento selecionado e selecionar o elemento ao clicar numa linha.
"""

from __future__ import annotations

from .xml_document import START_TAG_RE, UIDocument


def element_lines(text: str, count: int) -> list[int]:
    """Linha de cada tag <BaseWndProperty>, na ordem dos elementos; [] se a contagem não bate."""
    lines: list[int] = []
    line = 1
    cursor = 0
    for match in START_TAG_RE.finditer(text):
        line += text.count("\n", cursor, match.start())
        cursor = match.start()
        lines.append(line)
    return lines if len(lines) == count else []


def source_view(document: UIDocument) -> dict:
    text = document.render_text()
    return {
        "path": str(document.path),
        "text": text,
        "lines": element_lines(text, len(document.elements)),
        "dirty": document.is_dirty,
    }
