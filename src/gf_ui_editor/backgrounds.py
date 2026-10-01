"""Fundos do jogo embutidos, um por resolução (capturas sem HUD feitas no próprio jogo)."""

from __future__ import annotations

from pathlib import Path
import re

BACKGROUNDS_DIRECTORY = Path(__file__).resolve().parent / "assets" / "backgrounds"


def available() -> dict[tuple[int, int], Path]:
    sizes: dict[tuple[int, int], Path] = {}
    for path in BACKGROUNDS_DIRECTORY.glob("*.jpg"):
        match = re.fullmatch(r"(\d+)x(\d+)", path.stem)
        if match:
            sizes[(int(match[1]), int(match[2]))] = path
    return sizes


def pick(resolution: tuple[int, int]) -> Path | None:
    """O fundo exato da resolução; senão, o de proporção mais próxima (e maior)."""
    sizes = available()
    if not sizes:
        return None
    if resolution in sizes:
        return sizes[resolution]
    aspect = resolution[0] / resolution[1]
    best = min(
        sizes,
        key=lambda size: (round(abs(size[0] / size[1] - aspect), 2), -size[0] * size[1]),
    )
    return sizes[best]
