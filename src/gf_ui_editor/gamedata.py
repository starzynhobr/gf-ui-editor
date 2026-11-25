"""Lista oficial do launcher (`GameDataFileList.txt`): tamanho e CRC32 de cada arquivo oficial.

Cada linha é ``caminho|tamanho|CRC32|tamanho compactado|flag|`` (ex.:
``UI\\Bank.xml|27012|CE2F48EF|1829|0|``). Serve para saber se um arquivo da UI é igual ao
oficial sem ter a cópia oficial: basta comparar tamanho e CRC.

O launcher aplica uma UI copiando os arquivos dela por cima da pasta UI (o que ela não traz
continua como está), então uma UI só precisa levar o que difere do oficial
(vault/launcher.md).
"""

from __future__ import annotations

import os
from pathlib import Path
import zlib

FILE_LIST = "GameDataFileList.txt"
_CHUNK = 1 << 20

# Valem enquanto data e tamanho não mudam: a lista tem 74 mil linhas e os DDS somam centenas de MB.
_list_cache: dict[str, tuple[tuple[int, int], dict[str, tuple[int, str]]]] = {}
_crc_cache: dict[str, tuple[int, int, str]] = {}


def _signature(path: Path) -> tuple[int, int] | None:
    try:
        stat = os.stat(path)
    except OSError:
        return None
    return stat.st_mtime_ns, stat.st_size


def official_ui_files(game_dir: Path) -> dict[str, tuple[int, str]]:
    """Arquivos oficiais da pasta UI: caminho relativo a UI/ em minúsculas com "/" -> (tamanho, CRC)."""
    path = game_dir / FILE_LIST
    signature = _signature(path)
    if signature is None:
        return {}
    cached = _list_cache.get(str(path))
    if cached is not None and cached[0] == signature:
        return cached[1]
    try:
        lines = path.read_text(encoding="latin-1").splitlines()
    except OSError:
        return {}
    files: dict[str, tuple[int, str]] = {}
    for line in lines:
        parts = line.split("|")
        if len(parts) < 3:
            continue
        name = parts[0].replace("\\", "/")
        if not name.lower().startswith("ui/"):
            continue
        try:
            size = int(parts[1])
        except ValueError:
            continue
        files[name[3:].lower()] = (size, parts[2].strip().upper())
    _list_cache[str(path)] = (signature, files)
    return files


def file_crc(path: Path) -> str:
    """CRC32 do arquivo em hexadecimal maiúsculo (como na lista), com cache por data e tamanho."""
    stat = os.stat(path)
    key = os.path.normcase(os.path.abspath(path))
    cached = _crc_cache.get(key)
    if cached is not None and cached[:2] == (stat.st_mtime_ns, stat.st_size):
        return cached[2]
    value = 0
    with open(path, "rb") as handle:
        while chunk := handle.read(_CHUNK):
            value = zlib.crc32(chunk, value)
    crc = f"{value & 0xFFFFFFFF:08X}"
    _crc_cache[key] = (stat.st_mtime_ns, stat.st_size, crc)
    return crc


def is_official(path: Path, relative: str, official: dict[str, tuple[int, str]]) -> bool:
    """O arquivo é idêntico ao oficial? Tamanho diferente já responde sem ler o arquivo."""
    entry = official.get(relative.replace("\\", "/").lower())
    if entry is None:
        return False
    try:
        if os.stat(path).st_size != entry[0]:
            return False
        return file_crc(path) == entry[1]
    except OSError:
        return False
