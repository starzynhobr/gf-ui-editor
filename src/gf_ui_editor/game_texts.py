"""Rótulos que o jogo escreve nos controles, lidos do T_TextIndex.ini da pasta do jogo.

O XML quase nunca traz o texto (WindowText vem vazio): o cliente o preenche pelo código.
`child_texts.CHILD_TEXTS` diz qual TextID vai em cada WindowID; o texto em si é do jogo
instalado, então segue o idioma que o usuário tem.
"""

from __future__ import annotations

import re
from pathlib import Path

from .child_texts import CHILD_TEXTS
from .error_sources import CPP_TO_XML

TEXT_INDEX = Path("data") / "Translate" / "T_TextIndex.ini"
_LINE = re.compile(r"^(\d+)\|(.*?)\|")
_cache: dict[Path, tuple[float, dict[int, str]]] = {}


def _decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", "replace")


def text_index(game_dir: Path) -> dict[int, str]:
    path = game_dir / TEXT_INDEX
    try:
        modified = path.stat().st_mtime
    except OSError:
        return {}
    cached = _cache.get(path)
    if cached is not None and cached[0] == modified:
        return cached[1]
    texts: dict[int, str] = {}
    for line in _decode(path.read_bytes()).splitlines():
        match = _LINE.match(line)
        if match is not None:
            texts.setdefault(int(match.group(1)), match.group(2))
    _cache[path] = (modified, texts)
    return texts


def text_ids_for(xml_name: str) -> dict[str, int]:
    """WindowID -> TextID de todos os .cpp que carregam este XML."""
    name = xml_name.lower()
    result: dict[str, int] = {}
    for cpp, xml_files in CPP_TO_XML.items():
        if name in (xml.lower() for xml in xml_files):
            for window_id, text_id in CHILD_TEXTS.get(cpp, {}).items():
                result.setdefault(str(window_id), text_id)
    return result


def labels_for(xml_name: str, game_dir: Path | None) -> dict[str, str]:
    """WindowID -> texto que o jogo mostra; vazio sem a pasta do jogo."""
    if game_dir is None:
        return {}
    texts = text_index(game_dir)
    return {
        window_id: texts[text_id]
        for window_id, text_id in text_ids_for(xml_name).items()
        if text_id in texts
    }
