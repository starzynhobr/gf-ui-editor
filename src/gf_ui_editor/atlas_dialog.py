from __future__ import annotations

from collections.abc import Callable
import math

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QSignalBlocker, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from .xml_document import UVRect


class AtlasView(QGraphicsView):
    selection_changed = Signal(object)
    cursor_moved = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(QColor(28, 33, 42))
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pixmap_item = QGraphicsPixmapItem()
        self._scene.addItem(self._pixmap_item)
        self._selection_item = QGraphicsRectItem()
        selection_pen = QPen(QColor(255, 190, 30))
        selection_pen.setWidthF(1.0)
        selection_pen.setCosmetic(True)
        self._selection_item.setPen(selection_pen)
        self._selection_item.setBrush(QColor(255, 190, 30, 18))
        self._selection_item.setZValue(10)
        self._scene.addItem(self._selection_item)
        self._resize_handles: dict[str, QGraphicsRectItem] = {}
        for corner in ("top_left", "top_right", "bottom_left", "bottom_right"):
            handle = QGraphicsRectItem(QRectF(-4, -4, 8, 8))
            handle.setFlag(
                QGraphicsRectItem.GraphicsItemFlag.ItemIgnoresTransformations
            )
            handle.setBrush(QColor(255, 190, 30))
            handle.setPen(QPen(QColor(24, 28, 36), 1))
            handle.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            handle.setZValue(11)
            self._scene.addItem(handle)
            self._resize_handles[corner] = handle
        self._progress_item = QGraphicsRectItem()
        progress_pen = QPen(QColor(65, 220, 255))
        progress_pen.setWidthF(1.0)
        progress_pen.setCosmetic(True)
        progress_pen.setStyle(Qt.PenStyle.DashLine)
        self._progress_item.setPen(progress_pen)
        self._progress_item.setBrush(QColor(65, 220, 255, 18))
        self._progress_item.setZValue(9)
        self._progress_item.setVisible(False)
        self._scene.addItem(self._progress_item)
        self._progress_offset: tuple[int, int] | None = None
        self._selection_start: QPointF | None = None
        self._resize_corner: str | None = None
        self._resize_anchor: QPointF | None = None
        self._panning = False
        self._pan_start: QPoint | None = None

    def set_pixmap(self, pixmap: QPixmap) -> None:
        self._pixmap_item.setPixmap(pixmap)
        self._scene.setSceneRect(QRectF(pixmap.rect()))

    def set_selection(self, uv: UVRect) -> None:
        self._selection_item.setRect(uv.left, uv.top, uv.width, uv.height)
        self._update_resize_handles()
        if self._progress_offset is not None:
            offset_x, offset_y = self._progress_offset
            self._progress_item.setRect(
                uv.left + offset_x,
                uv.top + offset_y,
                uv.width,
                uv.height,
            )

    def _update_resize_handles(self) -> None:
        rect = self._selection_item.rect().normalized()
        positions = {
            "top_left": rect.topLeft(),
            "top_right": rect.topRight(),
            "bottom_left": rect.bottomLeft(),
            "bottom_right": rect.bottomRight(),
        }
        visible = not rect.isEmpty()
        for corner, handle in self._resize_handles.items():
            handle.setPos(positions[corner])
            handle.setVisible(visible)

    def _corner_at(self, viewport_position: QPoint) -> str | None:
        for corner, handle in self._resize_handles.items():
            if not handle.isVisible():
                continue
            handle_position = self.mapFromScene(handle.scenePos())
            if (
                abs(handle_position.x() - viewport_position.x()) <= 8
                and abs(handle_position.y() - viewport_position.y()) <= 8
            ):
                return corner
        return None

    def _opposite_corner(self, corner: str) -> QPointF:
        rect = self._selection_item.rect().normalized()
        return {
            "top_left": rect.bottomRight(),
            "top_right": rect.bottomLeft(),
            "bottom_left": rect.topRight(),
            "bottom_right": rect.topLeft(),
        }[corner]

    def _uv_between(self, first: QPointF, second: QPointF) -> UVRect:
        bounds = self._pixmap_item.boundingRect()
        left = max(0, min(math.floor(min(first.x(), second.x())), int(bounds.width()) - 1))
        top = max(0, min(math.floor(min(first.y(), second.y())), int(bounds.height()) - 1))
        right = max(left + 1, min(math.ceil(max(first.x(), second.x())), int(bounds.width())))
        bottom = max(top + 1, min(math.ceil(max(first.y(), second.y())), int(bounds.height())))
        return UVRect(left, top, right - left, bottom - top)

    def set_progress_offset(self, offset: tuple[int, int] | None) -> None:
        self._progress_offset = offset
        self._progress_item.setVisible(offset is not None)
        if offset is not None:
            rect = self._selection_item.rect()
            self.set_selection(
                UVRect(
                    round(rect.left()),
                    round(rect.top()),
                    round(rect.width()),
                    round(rect.height()),
                )
            )

    def fit_texture(self) -> None:
        if not self._pixmap_item.pixmap().isNull():
            self.fitInView(
                self._pixmap_item.boundingRect(), Qt.AspectRatioMode.KeepAspectRatio
            )

    def focus_selection(self) -> None:
        rect = self._selection_item.rect().normalized()
        if rect.isEmpty():
            return
        if self._progress_item.isVisible():
            rect = rect.united(self._progress_item.rect().normalized())
        margin = max(4.0, min(24.0, max(rect.width(), rect.height()) * 0.2))
        target = rect.adjusted(-margin, -margin, margin, margin)
        self.fitInView(target, Qt.AspectRatioMode.KeepAspectRatio)
        self.centerOn(rect.center())

    def _clamp(self, point: QPointF) -> QPointF:
        bounds = self._pixmap_item.boundingRect()
        return QPointF(
            max(bounds.left(), min(point.x(), bounds.right())),
            max(bounds.top(), min(point.y(), bounds.bottom())),
        )

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_start = event.position().toPoint()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            corner = self._corner_at(event.position().toPoint())
            if corner is not None:
                self._resize_corner = corner
                self._resize_anchor = self._opposite_corner(corner)
                event.accept()
                return
            self._selection_start = self._clamp(
                self.mapToScene(event.position().toPoint())
            )
            self._selection_item.setRect(QRectF(self._selection_start, self._selection_start))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        point = self._clamp(self.mapToScene(event.position().toPoint()))
        self.cursor_moved.emit(math.floor(point.x()), math.floor(point.y()))
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
        if self._selection_start is not None:
            self._selection_item.setRect(
                QRectF(self._selection_start, point).normalized()
            )
            event.accept()
            return
        if self._resize_corner is not None and self._resize_anchor is not None:
            uv = self._uv_between(self._resize_anchor, point)
            self.set_selection(uv)
            self.selection_changed.emit(uv)
            event.accept()
            return
        corner = self._corner_at(event.position().toPoint())
        if corner in {"top_left", "bottom_right"}:
            self.viewport().setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif corner in {"top_right", "bottom_left"}:
            self.viewport().setCursor(Qt.CursorShape.SizeBDiagCursor)
        else:
            self.viewport().unsetCursor()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        if self._panning and event.button() == Qt.MouseButton.MiddleButton:
            self._panning = False
            self._pan_start = None
            self.viewport().unsetCursor()
            event.accept()
            return
        if self._selection_start is not None and event.button() == Qt.MouseButton.LeftButton:
            point = self._clamp(self.mapToScene(event.position().toPoint()))
            uv = self._uv_between(self._selection_start, point)
            self._selection_start = None
            self.set_selection(uv)
            self.selection_changed.emit(uv)
            event.accept()
            return
        if self._resize_corner is not None and event.button() == Qt.MouseButton.LeftButton:
            point = self._clamp(self.mapToScene(event.position().toPoint()))
            assert self._resize_anchor is not None
            uv = self._uv_between(self._resize_anchor, point)
            self._resize_corner = None
            self._resize_anchor = None
            self.set_selection(uv)
            self.selection_changed.emit(uv)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)


class AtlasDialog(QDialog):
    def __init__(
        self,
        texture_name: str,
        pixmap: QPixmap,
        uv: UVRect,
        apply_callback: Callable[[UVRect, bool], None],
        parent=None,
        progress_offset: tuple[int, int] | None = None,
    ):
        super().__init__(parent)
        self.texture_name = texture_name
        self._apply_callback = apply_callback
        self.setWindowTitle(f"Atlas DDS — {texture_name}")
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
        self.resize(1180, 820)

        self.title = QLabel(texture_name)
        self.title.setObjectName("panelTitle")
        self.details = QLabel()
        self.details.setObjectName("panelSubtitle")
        self.cursor_label = QLabel("Cursor: —")
        self.cursor_label.setObjectName("panelSubtitle")

        self.view = AtlasView()
        self.view.setMinimumSize(760, 560)
        self.view.selection_changed.connect(self._selection_changed)
        self.view.cursor_moved.connect(
            lambda x, y: self.cursor_label.setText(f"Cursor: X {x} · Y {y}")
        )
        self.focus_button = QPushButton("Centralizar seleção")
        self.focus_button.setToolTip(
            "Aproxima e enquadra o recorte NorUV selecionado atualmente."
        )
        self.focus_button.clicked.connect(self.view.focus_selection)
        self.full_atlas_button = QPushButton("Ver atlas inteiro")
        self.full_atlas_button.clicked.connect(self.view.fit_texture)
        view_buttons = QHBoxLayout()
        view_buttons.addWidget(self.focus_button)
        view_buttons.addWidget(self.full_atlas_button)

        self.left_spin = self._spinbox()
        self.top_spin = self._spinbox()
        self.width_spin = self._spinbox(minimum=1)
        self.height_spin = self._spinbox(minimum=1)
        for spin in (
            self.left_spin,
            self.top_spin,
            self.width_spin,
            self.height_spin,
        ):
            spin.valueChanged.connect(self._spins_changed)

        form = QFormLayout()
        form.addRow("X / NorUVLeft", self.left_spin)
        form.addRow("Y / NorUVTop", self.top_spin)
        form.addRow("Largura / NorUVWidth", self.width_spin)
        form.addRow("Altura / NorUVHeight", self.height_spin)
        self.resize_element = QCheckBox("Ajustar o tamanho do elemento ao recorte")
        explanation = QLabel(
            "Arraste sobre a imagem para marcar o recorte ou use as alças nos cantos "
            "para ajustar a seleção atual. As coordenadas começam em "
            "(0, 0) no canto superior esquerdo. O botão do meio navega e a roda aplica zoom."
        )
        explanation.setWordWrap(True)
        explanation.setObjectName("panelSubtitle")
        self.progress_explanation = QLabel()
        self.progress_explanation.setWordWrap(True)
        self.progress_explanation.setObjectName("progressHint")
        if progress_offset is not None:
            offset_x, offset_y = progress_offset
            self.progress_explanation.setText(
                "Progresso em 100%: amarelo = textura-base; ciano = camada "
                f"preenchida aplicada pelo jogo (offset X {offset_x}, Y {offset_y})."
            )
        else:
            self.progress_explanation.hide()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Apply
            | QDialogButtonBox.StandardButton.Close
        )
        buttons.button(QDialogButtonBox.StandardButton.Apply).setText("Aplicar recorte")
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("Fechar")
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(
            self._apply
        )
        buttons.rejected.connect(self.close)

        side = QVBoxLayout()
        side.addWidget(self.title)
        side.addWidget(self.details)
        side.addLayout(view_buttons)
        side.addSpacing(8)
        side.addLayout(form)
        side.addWidget(self.resize_element)
        side.addWidget(explanation)
        side.addWidget(self.progress_explanation)
        side.addStretch(1)
        side.addWidget(self.cursor_label)
        side.addWidget(buttons)

        content = QHBoxLayout()
        content.addWidget(self.view, 1)
        content.addLayout(side)
        layout = QVBoxLayout(self)
        layout.addLayout(content)

        self.reload_pixmap(pixmap, fit=True)
        self.view.set_progress_offset(progress_offset)
        self.set_uv(uv)

    @staticmethod
    def _spinbox(minimum: int = 0) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(minimum, 100000)
        spin.setKeyboardTracking(True)
        return spin

    def reload_pixmap(self, pixmap: QPixmap, fit: bool = False) -> None:
        self.view.set_pixmap(pixmap)
        self.details.setText(f"{pixmap.width()} × {pixmap.height()} px")
        self.left_spin.setMaximum(max(0, pixmap.width() - 1))
        self.top_spin.setMaximum(max(0, pixmap.height() - 1))
        self.width_spin.setMaximum(max(1, pixmap.width()))
        self.height_spin.setMaximum(max(1, pixmap.height()))
        if fit:
            self.view.fit_texture()

    def set_uv(self, uv: UVRect) -> None:
        for spin, value in zip(
            (self.left_spin, self.top_spin, self.width_spin, self.height_spin),
            (uv.left, uv.top, uv.width, uv.height),
            strict=True,
        ):
            with QSignalBlocker(spin):
                spin.setValue(value)
        self.view.set_selection(uv)

    def _selection_changed(self, uv: UVRect) -> None:
        self.set_uv(uv)

    def _spins_changed(self, _value: int) -> None:
        self.view.set_selection(self.current_uv())

    def current_uv(self) -> UVRect:
        return UVRect(
            self.left_spin.value(),
            self.top_spin.value(),
            self.width_spin.value(),
            self.height_spin.value(),
        )

    def _apply(self) -> None:
        self._apply_callback(self.current_uv(), self.resize_element.isChecked())
