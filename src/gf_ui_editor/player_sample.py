"""Personagem de exemplo nas janelas que o jogo preenche com dados do jogador.

Nick, nível, HP/MP e os ícones de classe e reencarnação não estão no XML: o cliente os
escreve pelo código (CMiniInfo, MiniInfo.cpp, para o BasicChar.xml). Mostrar um valor
de exemplo ajuda a reservar o espaço certo ao mexer no layout.

Fonte no GrandFantasia.exe:
- FUN_008817c0 escreve o nível no 5000, o nick no 5010 e "%d/%d" de HP e MP no 5060 e 5070;
  põe o ícone da classe no 4010 (FUN_006e6700: um quadro de 16px do main.dds por classe)
  e o de reencarnação no 4011 (main.dds, x = 205 + 24 x reencarnações, y = 511, 20x20).
- CCreateCharacterWnd (FUN_009c19f0) limita a caixa do nome (elemento 6000) a 12 caracteres.
"""

from __future__ import annotations

NICK_MAX_LENGTH = 12
SAMPLE_NICK = "StarzynhoBR3"  # 12 caracteres: o maior nick que a criação de personagem aceita

# arquivo -> WindowID -> texto
SAMPLE_TEXTS: dict[str, dict[str, str]] = {
    "basicchar.xml": {
        "5000": "100",
        "5010": SAMPLE_NICK,
        "5060": "9999999/9999999",
        "5070": "999999/999999",
    },
    # CTargetWnd (FUN_00885b70): nível no 2020, "%d/%d" de HP e MP no 3100 e 3200. O nome
    # vai no 2000, o único texto do quadro de cima que o código não preenche com número.
    "target.xml": {
        "2000": SAMPLE_NICK,
        "2020": "100",
        "3100": "9999999/9999999",
        "3200": "999999/999999",
    },
}

# arquivo -> WindowID -> (textura, (x, y, largura, altura))
SAMPLE_ICONS: dict[str, dict[str, tuple[str, tuple[int, int, int, int]]]] = {
    "basicchar.xml": {
        "4010": ("main.dds", (812, 149, 16, 16)),  # classe 0 (Novato)
        "4011": ("main.dds", (229, 511, 20, 20)),  # 1 reencarnação
    },
    # CTargetWnd liga os mesmos 4010/4011 (FUN_00884d50) e põe os mesmos ícones.
    "target.xml": {
        "4010": ("main.dds", (812, 149, 16, 16)),
        "4011": ("main.dds", (229, 511, 20, 20)),
    },
}


def sample_text(xml_name: str, window_id: str) -> str:
    return SAMPLE_TEXTS.get(xml_name.lower(), {}).get(window_id, "")


def sample_icon(xml_name: str, window_id: str) -> tuple[str, tuple[int, int, int, int]] | None:
    return SAMPLE_ICONS.get(xml_name.lower(), {}).get(window_id)


def has_sample(xml_name: str) -> bool:
    name = xml_name.lower()
    return name in SAMPLE_TEXTS or name in SAMPLE_ICONS
