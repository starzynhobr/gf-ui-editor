"""Paleta única para o stylesheet Qt e as cores desenhadas no canvas."""

from string import Template

from PySide6.QtGui import QColor


COLORS = {
    "WINDOW_BG": "#171b23",
    "CHROME_BG": "#141820",
    "PANEL_BG": "#1b2029",
    "INPUT_BG": "#222934",
    "INPUT_READONLY_BG": "#1d232c",
    "TREE_ALTERNATE_BG": "#1e242e",
    "TOOLTIP_BG": "#11151b",
    "TEXT_PRIMARY": "#d8dee9",
    "TEXT_BRIGHT": "#edf2f7",
    "TEXT_TITLE": "#f3f6fa",
    "TEXT_MUTED": "#9ca3af",
    "TEXT_SECTION": "#8fa3bd",
    "TEXT_SUBTITLE": "#8491a3",
    "TEXT_DISABLED": "#687386",
    "TEXT_READONLY": "#aab4c3",
    "TEXT_HEADER": "#9facbd",
    "TEXT_STATUS": "#93a0b2",
    "WHITE": "#ffffff",
    "BORDER_CHROME": "#2b3340",
    "BORDER_PANEL": "#303846",
    "BORDER_INPUT": "#364151",
    "BORDER_TOOLTIP": "#445066",
    "MENU_HOVER_BG": "#2b3442",
    "BUTTON_HOVER_BG": "#252c38",
    "BUTTON_HOVER_BORDER": "#394455",
    "BUTTON_PRESSED_BG": "#303a49",
    "TREE_HOVER_BG": "#252d39",
    "TREE_SELECTED_BG": "#2563a9",
    "SCROLLBAR_HANDLE": "#465164",
    "SELECTION_BLUE": "#3b82f6",
    "FOCUS_BLUE": "#60a5fa",
    "SELECTION_GOLD": "#ffbe1e",
    "HANDLE_BORDER": "#181c24",
    "ELEMENT_OVERLAY": "#2896dc",
    "ELEMENT_OUTLINE": "#5abeff",
    "LABEL_YELLOW": "#ffeb78",
    "POSITION_CYAN": "#6ee6ff",
    "PROGRESS_CYAN": "#41dcff",
    "CANVAS_BG": "#24272e",
    "ATLAS_BG": "#1c212a",
}


def qcolor(token: str, alpha: int | None = None) -> QColor:
    color = QColor(COLORS[token])
    if alpha is not None:
        color.setAlpha(alpha)
    return color


def stylesheet(template: str) -> str:
    return Template(template).substitute(COLORS)
