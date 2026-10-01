"""Paleta única para o stylesheet Qt e as cores desenhadas no canvas."""

from string import Template

from PySide6.QtGui import QColor


COLORS = {
    "WINDOW_BG": "#111318",
    "CHROME_BG": "#0c0e12",
    "PANEL_BG": "#14171d",
    "INPUT_BG": "#0f1116",
    "INPUT_READONLY_BG": "#14171d",
    "TREE_ALTERNATE_BG": "#14171d",
    "TOOLTIP_BG": "#0c0e12",
    "TEXT_PRIMARY": "#d9dde6",
    "TEXT_BRIGHT": "#f1f3f8",
    "TEXT_TITLE": "#f1f3f8",
    "TEXT_MUTED": "#8a93a6",
    "TEXT_SECTION": "#8a93a6",
    "TEXT_SUBTITLE": "#8a93a6",
    "TEXT_DISABLED": "#4b5263",
    "TEXT_READONLY": "#aeb6c6",
    "TEXT_HEADER": "#8a93a6",
    "TEXT_STATUS": "#8a93a6",
    "WHITE": "#ffffff",
    "BORDER_CHROME": "#1f232c",
    "BORDER_PANEL": "#1f232c",
    "BORDER_INPUT": "#262b36",
    "BORDER_TOOLTIP": "#2a2f3b",
    "MENU_HOVER_BG": "#1f232c",
    "BUTTON_HOVER_BG": "#1a1e27",
    "BUTTON_HOVER_BORDER": "#262b36",
    "BUTTON_PRESSED_BG": "#232833",
    "TREE_HOVER_BG": "#1a1e27",
    "TREE_SELECTED_BG": "#241d3a",
    "SCROLLBAR_HANDLE": "#2a2f3b",
    "SELECTION_BLUE": "#7c4ce0",
    "FOCUS_BLUE": "#a77bff",
    "SELECTION_GOLD": "#ffbe1e",
    "HANDLE_BORDER": "#181c24",
    "ELEMENT_OVERLAY": "#2896dc",
    "ELEMENT_OUTLINE": "#5abeff",
    "LABEL_YELLOW": "#ffeb78",
    "POSITION_CYAN": "#6ee6ff",
    "PROGRESS_CYAN": "#41dcff",
    "CANVAS_BG": "#0d0f13",
    "ATLAS_BG": "#0f1116",
    "CHECKER_LIGHT": "#2a2d34",
    "CHECKER_DARK": "#20232a",
    "ACCENT_BG": "#7c4ce0",
    "ACCENT_HOVER_BG": "#8c5ff0",
    "ACCENT_BORDER": "#a77bff",
    "ICON": "#aeb6c6",
    "CARD_BG": "#181b22",
    "CARD_BORDER": "#232833",
    "ACCENT_SOFT_BG": "#241d3a",
    "ACCENT_TEXT": "#cbb9ff",
    "CANVAS_DOT": "#22262f",
    "CHIP_BG": "#171a21",
    "GAME_SCREEN_BG": "#0d0f13",
    "GAME_SCREEN_BORDER": "#7c8799",
}


def qcolor(token: str, alpha: int | None = None) -> QColor:
    color = QColor(COLORS[token])
    if alpha is not None:
        color.setAlpha(alpha)
    return color


def stylesheet(template: str) -> str:
    return Template(template).substitute(COLORS)
