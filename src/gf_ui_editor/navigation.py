"""Roda do mouse por estilo de navegação, a mesma regra no canvas e no atlas (e no web, canvas/wheel.ts).

"corel" sempre dá zoom; "paintnet" rola, Shift vai para os lados e Ctrl dá zoom; "photoshop" rola,
Ctrl ou Shift vão para os lados e Alt dá zoom.
"""

from __future__ import annotations

from typing import Literal

NAVIGATION_STYLES = ("corel", "paintnet", "photoshop")
WheelAction = Literal["zoom", "horizontal", "vertical"]


def wheel_action(style: str, *, ctrl: bool, shift: bool, alt: bool) -> WheelAction:
    if style == "paintnet":
        return "zoom" if ctrl else "horizontal" if shift else "vertical"
    if style == "photoshop":
        return "zoom" if alt else "horizontal" if ctrl or shift else "vertical"
    return "zoom"
