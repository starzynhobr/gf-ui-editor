"""Feedback de cursor para comandos clicáveis da interface Qt."""

from PySide6.QtCore import QCoreApplication, QEvent, QObject, Qt
from PySide6.QtWidgets import QAbstractButton, QAbstractScrollArea, QAbstractSpinBox, QComboBox, QMenu, QMenuBar, QWidget


def _clickable_cursor(widget: QWidget) -> Qt.CursorShape:
    return Qt.CursorShape.PointingHandCursor if widget.isEnabled() else Qt.CursorShape.ArrowCursor


class PointerCursorFilter(QObject):
    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if isinstance(watched, (QAbstractButton, QComboBox)) and event.type() == QEvent.Type.EnabledChange:
            watched.setCursor(_clickable_cursor(watched))
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
    for widget in root.findChildren(QAbstractButton) + root.findChildren(QComboBox):
        widget.setCursor(_clickable_cursor(widget))
        widget.installEventFilter(cursor_filter)
    for menu in root.findChildren(QMenu):
        menu.setMouseTracking(True)
        menu.installEventFilter(cursor_filter)
    for menu_bar in root.findChildren(QMenuBar):
        menu_bar.setMouseTracking(True)
        menu_bar.installEventFilter(cursor_filter)


class WheelPassThrough(QObject):
    """A roda do mouse sobre listas suspensas e campos numéricos rola o painel, sem mudar o valor.

    Rolando o painel de propriedades, o cursor passava por cima de um campo e trocava o
    valor sem a pessoa perceber.
    """

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() != QEvent.Type.Wheel:
            return False
        parent = watched.parentWidget() if isinstance(watched, QWidget) else None
        while parent is not None and not isinstance(parent, QAbstractScrollArea):
            parent = parent.parentWidget()
        if parent is not None:
            QCoreApplication.sendEvent(parent.viewport(), event)
        return True


def disable_wheel_changes(*widgets: QWidget) -> None:
    """Liga o WheelPassThrough nos campos (combos e spinboxes) passados."""
    for widget in widgets:
        guard = getattr(widget, "_wheel_guard", None)
        if guard is None:
            guard = WheelPassThrough(widget)
            widget._wheel_guard = guard
            widget.installEventFilter(guard)
        if isinstance(widget, (QComboBox, QAbstractSpinBox)):
            widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
