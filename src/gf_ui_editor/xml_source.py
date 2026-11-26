"""Texto do XML aberto como ele ficaria ao salvar ("Ver código XML" da interface nova).

Sem Qt. Devolve o texto renderizado (com as edições ainda não salvas) e, para cada
elemento, a linha (1 em diante) da tag <BaseWndProperty> dele nesse texto, para o painel de
código levar à linha do elemento selecionado e selecionar o elemento ao clicar numa linha.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from .xml_document import DocumentError, NOR_UV_TAG_RE, START_TAG_RE, UIDocument


class SourceError(ValueError):
    def __init__(self, message: str, line: int, column: int) -> None:
        super().__init__(message)
        self.line = line
        self.column = column


def _location(text: str, offset: int) -> tuple[int, int]:
    prefix = text[:offset].replace("\r\n", "\n").replace("\r", "\n")
    return prefix.count("\n") + 1, len(prefix.rsplit("\n", 1)[-1]) + 1


def encode_source(text: str, encoding: str) -> bytes:
    try:
        return text.encode(encoding)
    except UnicodeEncodeError as exc:
        codepoint = ord(text[exc.start])
        raise SourceError(
            f"Caractere U+{codepoint:04X} não pode ser gravado em {'Big5' if encoding == 'big5' else encoding.upper()}.",
            *_location(text, exc.start),
        ) from exc


def replace_source(document: UIDocument, text: str) -> UIDocument:
    """Validate editable XML and keep the original bytes for diff and external-change checks."""
    encode_source(text, document.encoding)
    try:
        return document.with_text(text)
    except DocumentError as exc:
        cause = exc.details.get("error")
        if isinstance(cause, ET.ParseError):
            line, column = cause.position
            raise SourceError(str(exc), line, column + 1) from exc
        pattern = START_TAG_RE if exc.code == "element_count" else NOR_UV_TAG_RE
        match = pattern.search(text)
        raise SourceError(str(exc), *_location(text, match.start() if match else 0)) from exc


def element_lines(text: str, count: int) -> list[int]:
    """Linha de cada tag <BaseWndProperty>, na ordem dos elementos; [] se a contagem não bate."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
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
