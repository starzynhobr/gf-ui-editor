"""Feedback de cursor para comandos clicáveis da interface Qt."""

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QAbstractButton, QMenu, QMenuBar, QWidget


class PointerCursorFilter(QObject):
    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if isinstance(watched, QAbstractButton) and event.type() == QEvent.Type.EnabledChange:
            watched.setCursor(
                Qt.CursorShape.PointingHandCursor
                if watched.isEnabled() else Qt.CursorShape.ArrowCursor
            )
        elif isinstance(watched, (QMenu, QMenuBar)) and event.type() == QEvent.Type.MouseMove:
            action = watched.actionAt(event.position().toPoint())
            watched.setCursor(
                Qt.CursorShape.PointingHandCursor
                if action is not None and action.isEnabled() and not action.isSeparator()
                else Qt.CursorShape.ArrowCursor
            )
        return False


def install_pointer_cursors(root: QWidget) -> None:
    """Aplica mão apenas a comandos ativos; preserva cursores de edição do canvas."""
    cursor_filter = PointerCursorFilter(root)
    root._pointer_cursor_filter = cursor_filter
    for button in root.findChildren(QAbstractButton):
        button.setCursor(
            Qt.CursorShape.PointingHandCursor
            if button.isEnabled() else Qt.CursorShape.ArrowCursor
        )
        button.installEventFilter(cursor_filter)
    for menu in root.findChildren(QMenu):
        menu.setMouseTracking(True)
        menu.installEventFilter(cursor_filter)
    for menu_bar in root.findChildren(QMenuBar):
        menu_bar.setMouseTracking(True)
        menu_bar.installEventFilter(cursor_filter)
