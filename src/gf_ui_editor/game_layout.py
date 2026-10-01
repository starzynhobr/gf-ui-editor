"""Posição da janela raiz na tela do jogo, conforme o cliente a calcula.

O cliente ignora `Screen_X`/`Screen_Y` do XML (são gravados e nunca lidos) e não
escala a interface. Por padrão, a raiz fica em `WindowLeft`/`WindowTop`, presa
aos limites da tela. Algumas classes reposicionam a raiz ao mudar a resolução;
as regras abaixo vêm da análise do `GrandFantasia.exe` no Ghidra (endereços da
função de cada classe entre parênteses; largura/altura da tela em
`DAT_00DE3FE4`/`DAT_00DE3FE8`).

Janelas arrastadas pelo jogador têm a posição salva no `User.ini` da pasta do
jogo (gravada em 0x00A12C70, lida em 0x00A12B20), usada quando a janela cabe
inteira na tela. Janelas ancoradas são reposicionadas depois (slot 24, ao ajustar
a resolução), então a regra delas vence: o relógio aparece em (1179, 180) a
1280×720 mesmo com (1146, 18) salvo.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import struct


Rect = tuple[int, int, int, int]


def _half(value: int) -> int:
    # Divisão inteira do C: trunca em direção a zero.
    return int(value / 2)


@dataclass(frozen=True)
class AnchorRule:
    description: str
    position: Callable[[int, int, Rect], tuple[int, int]]


def _clamp(screen_w: int, screen_h: int, rect: Rect) -> tuple[int, int]:
    """CWnd::SetPos (0x00A126F0): mantém a janela inteira dentro da tela."""
    x, y, width, height = rect
    x = max(0, x)
    y = max(0, y)
    if x + width > screen_w:
        x = screen_w - width
    if y + height > screen_h:
        y = screen_h - height
    return x, y


def _top_right(margin: int) -> Callable[[int, int, Rect], tuple[int, int]]:
    return lambda screen_w, _screen_h, rect: (screen_w - rect[2] - margin, 0)


RULES: dict[str, AnchorRule] = {
    "radar.xml": AnchorRule("canto superior direito", _top_right(0)),  # 0x00879230
    "tinyclock.xml": AnchorRule(  # 0x007A2CA0
        "direita (margem 30), Y fixo 180",
        lambda screen_w, _h, rect: (screen_w - rect[2] - 30, 180),
    ),
    "gametimer.xml": AnchorRule("topo à direita (margem 150)", _top_right(150)),  # 0x009418D0
    "pkpalace.xml": AnchorRule("topo à direita (margem 130)", _top_right(130)),  # 0x00947B60
    "battlefield.xml": AnchorRule("topo à direita (margem 145)", _top_right(145)),  # 0x009B58F0
    "beaststowerinfo.xml": AnchorRule("topo à direita (margem 160)", _top_right(160)),  # 0x00908FF0
    "menu.xml": AnchorRule(  # 0x00703D80
        "centralizado na base",
        lambda screen_w, screen_h, rect: (
            _half(screen_w) - _half(rect[2]),
            screen_h - rect[3],
        ),
    ),
    "target.xml": AnchorRule(  # 0x00884550
        "centralizado na horizontal",
        lambda screen_w, screen_h, rect: (
            _half(screen_w) - _half(rect[2]),
            _clamp(screen_w, screen_h, rect)[1],
        ),
    ),
    "channel.xml": AnchorRule(  # 0x007197A0
        "à esquerda, 72 px acima da base",
        lambda _w, screen_h, rect: (0, screen_h - rect[3] - 72),
    ),
}


# Seção do User.ini usada por cada XML (chamadas a 0x00A12B20 por classe).
# Ficaram de fora janelas com várias instâncias por XML (SHORTCUTnn, ENCHANTLISTn).
INI_SECTIONS = {
    "inventory.xml": "INVENTORY",
    "spellview.xml": "SPELLVIEW",
    "auctionbuy.xml": "AUCTION",
    "storage.xml": "STORAGE",
    "maillist.xml": "MAIL",
    "tinyclock.xml": "TINYCLOCK",
    "diary_autoacceptmission.xml": "AAMISSION",
    "race_timer.xml": "RACETIMER",
    "questtracewnd.xml": "QUESTTRACE",
    "spellaa.xml": "SPELLAA",
    "gamehelp.xml": "GAMEHELPLOG",
    "npctalk.xml": "NPCTALK",
    "diary_questlog.xml": "QUESTLOG",
    "fellowship_friends.xml": "FELLOWSHIP",
    "rankinfo.xml": "RANKINFOLOG",
    "carvingwnd.xml": "STRENGTHEN",
    "strengthen.xml": "STRENGTHEN",
    "equipment.xml": "EQUIPMENT",
    "spellst.xml": "SPELLST",
    "awake.xml": "AWAKE",
    "itemexchange.xml": "ITEM_EXCHANGE",
    "kusocombine.xml": "KUSOCOMBINE",
    "combine.xml": "COMBINE",
    "shop.xml": "SHOP",
}


def decode_position(text: str) -> Rect | None:
    """`Position=` guarda 4 int32 (x, y, largura, altura); cada byte vira duas
    letras 'A'..'P', nibble baixo primeiro."""
    text = text.strip()
    if len(text) != 32 or any(not "A" <= char <= "P" for char in text):
        return None
    data = bytes(
        (ord(text[i]) - 65) | ((ord(text[i + 1]) - 65) << 4) for i in range(0, 32, 2)
    )
    return struct.unpack("<4i", data)


def load_user_positions(path: Path) -> dict[str, Rect]:
    positions: dict[str, Rect] = {}
    section = None
    try:
        lines = path.read_text(encoding="latin-1").splitlines()
    except OSError:
        return positions
    for line in lines:
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].upper()
        elif section and line.lower().startswith("position="):
            rect = decode_position(line.split("=", 1)[1])
            if rect is not None:
                positions[section] = rect
    return positions


def saved_section_for(filename: str) -> str | None:
    return INI_SECTIONS.get(filename.lower())


def rule_for(filename: str) -> AnchorRule | None:
    return RULES.get(filename.lower())


def saved_position_applies(screen: tuple[int, int], rect: Rect, saved: Rect | None) -> bool:
    """O cliente só usa a posição salva se a janela couber inteira na tela."""
    if saved is None:
        return False
    x, y = saved[0], saved[1]
    return x >= 0 and y >= 0 and x + rect[2] <= screen[0] and y + rect[3] <= screen[1]


def root_screen_position(
    filename: str, screen: tuple[int, int], rect: Rect, saved: Rect | None = None
) -> tuple[int, int]:
    """Onde a raiz (`rect` = x, y, largura, altura do XML) aparece na tela."""
    rule = rule_for(filename)
    if rule is None and saved is not None and saved_position_applies(screen, rect, saved):
        return saved[0], saved[1]
    screen_w, screen_h = screen
    if rule is None:
        return _clamp(screen_w, screen_h, rect)
    return rule.position(screen_w, screen_h, rect)


def client_resolution(game_dir: Path) -> tuple[int, int] | None:
    """Resolução configurada no jogo (`client.ini`, seção [Option])."""
    try:
        lines = (game_dir / "client.ini").read_text(encoding="latin-1").splitlines()
    except OSError:
        return None
    values: dict[str, str] = {}
    in_option = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("["):
            in_option = stripped.lower() == "[option]"
        elif in_option and "=" in stripped:
            key, value = stripped.split("=", 1)
            values[key.strip().lower()] = value.strip()
    try:
        width, height = int(values["screenwidth"]), int(values["screenheight"])
    except (KeyError, ValueError):
        return None
    return (width, height) if width > 0 and height > 0 else None
