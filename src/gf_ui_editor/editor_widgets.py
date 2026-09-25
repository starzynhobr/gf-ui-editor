from __future__ import annotations

from collections.abc import Callable
import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QKeyEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QTransform,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsSimpleTextItem,
    QGraphicsView,
)

from .theme import qcolor
from .xml_document import UIElement


def constrain_to_axis(
    dx: float, dy: float, locked_axis: str | None = None
) -> tuple[float, float, str]:
    """Trava um deslocamento no eixo dominante e mantém a escolha durante o arraste."""
    axis = locked_axis
    if axis not in {"horizontal", "vertical"}:
        axis = "horizontal" if abs(dx) >= abs(dy) else "vertical"
    if axis == "horizontal":
        return dx, 0.0, axis
    return 0.0, dy, axis


class ResizeHandle(QGraphicsRectItem):
    """Alça inferior direita com tamanho constante na tela."""

    HIT_RECT = QRectF(-9, -9, 18, 18)

    def __init__(self, owner: "ElementItem"):
        super().__init__(QRectF(-5, -5, 10, 10), owner)
        self.owner = owner
        self._dragging = False
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self.setBrush(qcolor("SELECTION_GOLD"))
        self.setPen(QPen(qcolor("HANDLE_BORDER"), 1))
        self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        self.setZValue(20)

    def boundingRect(self) -> QRectF:  # noqa: N802
        return super().boundingRect().united(self.HIT_RECT)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRect(self.HIT_RECT)
        return path

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self.owner.begin_resize(event.scenePos())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        if self._dragging:
            self.owner.resize_to(
                event.scenePos(),
                proportional=bool(
                    event.modifiers() & Qt.KeyboardModifier.ShiftModifier
                ),
            )
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        if self._dragging and event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self.owner.end_resize()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class ElementItem(QGraphicsRectItem):
    SELECTION_Z_BASE = 1_000_000.0

    def __init__(
        self,
        element: UIElement,
        pixmap: QPixmap | None,
        selected_callback: Callable[[int], None],
        moved_callback: Callable[
            [dict[int, tuple[tuple[int, int, int, int], tuple[int, int, int, int]]]],
            None,
        ],
    ):
        super().__init__(QRectF(0, 0, max(1, element.width), max(1, element.height)))
        self.element_index = element.index
        self._selected_callback = selected_callback
        self._moved_callback = moved_callback
        self._drag_start_geometry = element.geometry
        self._drag_start_position = QPointF(element.x, element.y)
        self._group_drag_starts: dict[
            int, tuple["ElementItem", QPointF, tuple[int, int, int, int]]
        ] = {}
        self._element_width = element.width
        self._element_height = element.height
        self._locked_axis: str | None = None
        self._locked = False
        self._resize_start_scene_position = QPointF()
        self._resize_start_geometry = element.geometry
        self._labels_enabled = False
        self._textures_enabled = True
        self._base_z = float(element.index)
        self.setPos(element.x, element.y)
        self.setZValue(self._base_z)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.setBrush(qcolor("ELEMENT_OVERLAY", 8))
        self._normal_pen = QPen(qcolor("ELEMENT_OUTLINE", 110), 0, Qt.PenStyle.DashLine)
        self._selected_pen = QPen(qcolor("SELECTION_GOLD"), 0, Qt.PenStyle.SolidLine)
        self.setPen(self._normal_pen)

        self.texture_item: QGraphicsPixmapItem | None = None
        if pixmap is not None:
            self.texture_item = QGraphicsPixmapItem(pixmap, self)
            self.texture_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self.texture_item.setZValue(-1)

        label = f"{element.window_id} · {element.kind}"
        if element.window_text:
            label += f" · {element.window_text}"
        self.label_item = QGraphicsSimpleTextItem(label, self)
        self.label_item.setBrush(qcolor("LABEL_YELLOW"))
        self.label_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self.label_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.label_item.setPos(2, 1)
        self.drag_position_item = QGraphicsSimpleTextItem("", self)
        self.drag_position_item.setBrush(qcolor("POSITION_CYAN"))
        self.drag_position_item.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations
        )
        self.drag_position_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.drag_position_item.setZValue(2)
        self.drag_position_item.setVisible(False)
        self.resize_handle = ResizeHandle(self)
        self.resize_handle.setVisible(False)
        self._update_overlays()
        details = [f"WindowID: {element.window_id}", f"Tipo: {element.kind}"]
        if element.window_text:
            details.append(f"Texto: {element.window_text}")
        if element.parent_id:
            details.append(f"ParentNode: {element.parent_id}")
        details.append(
            f"Posição: ({element.x}, {element.y}) · Tamanho: {element.width} × {element.height}"
        )
        if element.texture_name:
            details.append(f"Textura: {element.texture_name}")
        self.setToolTip("\n".join(details))

    def set_labels_visible(self, visible: bool) -> None:
        if self._labels_enabled != visible:
            self.prepareGeometryChange()
        self._labels_enabled = visible
        self.label_item.setVisible(visible or self.isSelected())

    def boundingRect(self) -> QRectF:  # noqa: N802
        bounds = super().boundingRect()
        if hasattr(self, "label_item") and (
            self.isSelected() or self._labels_enabled
        ):
            bounds = bounds.united(
                self.label_item.mapRectToParent(self.label_item.boundingRect())
            )
        return bounds

    def shape(self) -> QPainterPath:
        path = super().shape()
        if not self.isSelected() or not hasattr(self, "label_item"):
            return path
        rect = self.rect()
        hit_width = max(10.0, rect.width())
        hit_height = max(10.0, rect.height())
        path.addRect(QRectF(rect.left(), rect.top(), hit_width, hit_height))
        path.addRect(self.label_item.mapRectToParent(self.label_item.boundingRect()))
        return path

    def contains_scene_point_for_interaction(self, scene_position: QPointF) -> bool:
        local_position = self.mapFromScene(scene_position)
        if self.shape().contains(local_position):
            return True
        return self.resize_handle.isVisible() and self.resize_handle.shape().contains(
            self.resize_handle.mapFromScene(scene_position)
        )

    def set_texture_visible(self, visible: bool) -> None:
        self._textures_enabled = visible
        if self.texture_item is not None:
            self.texture_item.setVisible(visible)

    def set_pixmap(self, pixmap: QPixmap | None) -> None:
        if self.texture_item is None:
            if pixmap is None:
                return
            self.texture_item = QGraphicsPixmapItem(pixmap, self)
            self.texture_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self.texture_item.setZValue(-1)
        else:
            self.texture_item.setPixmap(pixmap or QPixmap())
        self.texture_item.setVisible(self._textures_enabled and pixmap is not None)
        self._update_texture_transform()

    def set_locked(self, locked: bool) -> None:
        self._locked = locked
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, not locked)
        self.resize_handle.setVisible(self.isSelected() and not locked)
        self.setCursor(
            Qt.CursorShape.ArrowCursor if locked else Qt.CursorShape.SizeAllCursor
        )

    def apply_element(self, element: UIElement) -> None:
        self._element_width = element.width
        self._element_height = element.height
        self.setPos(element.x, element.y)
        self.setRect(QRectF(0, 0, max(1, element.width), max(1, element.height)))
        self._update_texture_transform()
        self._update_overlays()

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value):  # noqa: N802
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            position = QPointF(value)
            return QPointF(round(position.x()), round(position.y()))
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            self.prepareGeometryChange()
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            selected = bool(value)
            self.setZValue(
                self.SELECTION_Z_BASE + self._base_z if selected else self._base_z
            )
            self.setPen(self._selected_pen if selected else self._normal_pen)
            self.label_item.setVisible(self._labels_enabled or selected)
            self.resize_handle.setVisible(selected and not self._locked)
            self._selected_callback(self.element_index)
        return super().itemChange(change, value)

    def mousePressEvent(self, event):  # noqa: N802
        position = self.pos()
        self._drag_start_position = QPointF(position)
        self._locked_axis = None
        self._drag_start_geometry = (
            round(position.x()),
            round(position.y()),
            self._element_width,
            self._element_height,
        )
        selected_items = [
            item
            for item in (self.scene().selectedItems() if self.scene() is not None else [])
            if isinstance(item, ElementItem) and not item._locked
        ]
        if self not in selected_items and not self._locked:
            selected_items.append(self)
        self._group_drag_starts = {
            item.element_index: (
                item,
                QPointF(item.pos()),
                (
                    round(item.pos().x()),
                    round(item.pos().y()),
                    item._element_width,
                    item._element_height,
                ),
            )
            for item in selected_items
        }
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        if self._locked:
            super().mouseMoveEvent(event)
            return
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            delta = event.scenePos() - event.buttonDownScenePos(Qt.MouseButton.LeftButton)
            dx, dy, self._locked_axis = constrain_to_axis(
                delta.x(), delta.y(), self._locked_axis
            )
            for item, start_position, _geometry in self._group_drag_starts.values():
                item.setPos(start_position + QPointF(dx, dy))
            self._show_drag_position(self._locked_axis)
            event.accept()
            return
        # Soltar Shift durante o arraste devolve imediatamente o movimento livre.
        self._locked_axis = None
        super().mouseMoveEvent(event)
        self._show_drag_position()

    def mouseReleaseEvent(self, event):  # noqa: N802
        super().mouseReleaseEvent(event)
        changes = {}
        for index, (item, _start_position, old_geometry) in self._group_drag_starts.items():
            position = item.pos()
            new_geometry = (
                round(position.x()),
                round(position.y()),
                item._element_width,
                item._element_height,
            )
            if new_geometry != old_geometry:
                changes[index] = (old_geometry, new_geometry)
        if changes:
            self._moved_callback(changes)
        self._group_drag_starts.clear()
        self._locked_axis = None
        self.drag_position_item.setVisible(False)

    def _show_drag_position(self, axis: str | None = None) -> None:
        position = self.pos()
        suffix = ""
        if axis == "horizontal":
            suffix = " · eixo horizontal"
        elif axis == "vertical":
            suffix = " · eixo vertical"
        self.drag_position_item.setText(
            f"X {round(position.x())} · Y {round(position.y())}{suffix}"
        )
        self._update_overlays()
        self.drag_position_item.setVisible(True)

    def _update_overlays(self) -> None:
        rect = self.rect()
        self.resize_handle.setPos(rect.width(), rect.height())
        self.drag_position_item.setPos(2, max(1, rect.height()) + 7)

    def _update_texture_transform(self) -> None:
        if self.texture_item is None or self.texture_item.pixmap().isNull():
            return
        pixmap = self.texture_item.pixmap()
        self.texture_item.setTransform(
            QTransform.fromScale(
                self.rect().width() / pixmap.width(),
                self.rect().height() / pixmap.height(),
            )
        )

    def begin_resize(self, scene_position: QPointF) -> None:
        if self._locked:
            return
        position = self.pos()
        self._resize_start_scene_position = QPointF(scene_position)
        self._resize_start_geometry = (
            round(position.x()),
            round(position.y()),
            self._element_width,
            self._element_height,
        )

    def resize_to(
        self, scene_position: QPointF, *, proportional: bool = False
    ) -> None:
        if self._locked:
            return
        delta = scene_position - self._resize_start_scene_position
        _, _, semantic_width, semantic_height = self._resize_start_geometry
        start_width = max(1, semantic_width)
        start_height = max(1, semantic_height)
        if proportional:
            width_scale = (start_width + delta.x()) / start_width
            height_scale = (start_height + delta.y()) / start_height
            scale = (
                width_scale
                if abs(width_scale - 1) >= abs(height_scale - 1)
                else height_scale
            )
            scale = max(scale, 1 / start_width, 1 / start_height)
            width = max(1, round(start_width * scale))
            height = max(1, round(start_height * scale))
        else:
            width = max(1, round(start_width + delta.x()))
            height = max(1, round(start_height + delta.y()))
        self.setRect(QRectF(0, 0, width, height))
        self._update_texture_transform()
        self._update_overlays()
        self.drag_position_item.setText(f"L {width} · A {height}")
        self.drag_position_item.setVisible(True)

    def end_resize(self) -> None:
        self.drag_position_item.setVisible(False)
        position = self.pos()
        rect = self.rect()
        new_geometry = (
            round(position.x()),
            round(position.y()),
            round(rect.width()),
            round(rect.height()),
        )
        if new_geometry != self._resize_start_geometry:
            self._moved_callback(
                {self.element_index: (self._resize_start_geometry, new_geometry)}
            )


class EditorView(QGraphicsView):
    cursor_scene_moved = Signal(int, int)

    def __init__(self, move_selected: Callable[[int, int], None], parent=None):
        super().__init__(parent)
        self._move_selected = move_selected
        self._cycle_signature: tuple[int, int, tuple[int, ...]] | None = None
        self._cycle_offset = -1
        self._panning = False
        self._pan_start = None
        self._preferred_item: ElementItem | None = None
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
            | QPainter.RenderHint.TextAntialiasing
        )
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.setBackgroundBrush(qcolor("CANVAS_BG"))
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

    @staticmethod
    def _element_parent(item: QGraphicsItem | None) -> ElementItem | None:
        while item is not None:
            if isinstance(item, ElementItem):
                return item
            item = item.parentItem()
        return None

    def set_interaction_priority(self, item: ElementItem | None) -> None:
        self._preferred_item = item

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_start = event.position().toPoint()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        if (
            event.button() == Qt.MouseButton.LeftButton
            and not event.modifiers() & Qt.KeyboardModifier.AltModifier
            and self._preferred_item is not None
            and self._preferred_item.isSelected()
            and self._preferred_item.isVisible()
        ):
            scene_position = self.mapToScene(event.position().toPoint())
            if self._preferred_item.contains_scene_point_for_interaction(
                scene_position
            ):
                original_z = self._preferred_item.zValue()
                self._preferred_item.setZValue(2_000_000)
                try:
                    super().mousePressEvent(event)
                finally:
                    self._preferred_item.setZValue(original_z)
                return
            self._preferred_item = None
        if (
            event.button() == Qt.MouseButton.LeftButton
            and event.modifiers() & Qt.KeyboardModifier.AltModifier
        ):
            candidates: list[ElementItem] = []
            seen: set[int] = set()
            for graphics_item in self.items(event.position().toPoint()):
                element_item = self._element_parent(graphics_item)
                if element_item is None or element_item.element_index in seen:
                    continue
                seen.add(element_item.element_index)
                candidates.append(element_item)
            if candidates:
                scene_position = self.mapToScene(event.position().toPoint())
                signature = (
                    round(scene_position.x()),
                    round(scene_position.y()),
                    tuple(item.element_index for item in candidates),
                )
                if signature == self._cycle_signature:
                    self._cycle_offset = (self._cycle_offset + 1) % len(candidates)
                else:
                    self._cycle_signature = signature
                    self._cycle_offset = 0
                target = candidates[self._cycle_offset]
                if self.scene() is not None:
                    self.scene().clearSelection()
                target.setSelected(True)
                event.accept()
                return
        self._cycle_signature = None
        self._cycle_offset = -1
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        scene_position = self.mapToScene(event.position().toPoint())
        self.cursor_scene_moved.emit(
            math.floor(scene_position.x()), math.floor(scene_position.y())
        )
        if self._panning and self._pan_start is not None:
            current = event.position().toPoint()
            delta = current - self._pan_start
            self._pan_start = current
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x()
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y()
            )
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        if self._panning and event.button() == Qt.MouseButton.MiddleButton:
            self._panning = False
            self._pan_start = None
            self.viewport().unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        directions = {
            Qt.Key.Key_Left: (-1, 0),
            Qt.Key.Key_Right: (1, 0),
            Qt.Key.Key_Up: (0, -1),
            Qt.Key.Key_Down: (0, 1),
        }
        if event.key() in directions:
            dx, dy = directions[event.key()]
            multiplier = 10 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
            self._move_selected(dx * multiplier, dy * multiplier)
            event.accept()
            return
        super().keyPressEvent(event)
