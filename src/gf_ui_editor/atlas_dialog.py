from __future__ import annotations

from collections.abc import Callable
import math
from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QSignalBlocker, Signal, QUrl
from PySide6.QtGui import QDesktopServices, QPainter, QPen, QPixmap, QWheelEvent
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
    QMessageBox,
    QPushButton,
    QSpinBox,
    QFrame,
    QGridLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .icons import icon

from .theme import qcolor
from .interaction import install_pointer_cursors
from .xml_document import UVRect


class AtlasView(QGraphicsView):
    selection_changed = Signal(object)
    offset_changed = Signal(int, int)
    cursor_moved = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(qcolor("ATLAS_BG"))
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pixmap_item = QGraphicsPixmapItem()
        self._scene.addItem(self._pixmap_item)
        self._selection_item = QGraphicsRectItem()
        selection_pen = QPen(qcolor("SELECTION_GOLD"))
        selection_pen.setWidthF(1.0)
        selection_pen.setCosmetic(True)
        self._selection_item.setPen(selection_pen)
        self._selection_item.setBrush(qcolor("SELECTION_GOLD", 18))
        self._selection_item.setZValue(10)
        self._scene.addItem(self._selection_item)
        self._resize_handles: dict[str, QGraphicsRectItem] = {}
        for corner in ("top_left", "top_right", "bottom_left", "bottom_right"):
            handle = QGraphicsRectItem(QRectF(-4, -4, 8, 8))
            handle.setFlag(
                QGraphicsRectItem.GraphicsItemFlag.ItemIgnoresTransformations
            )
            handle.setBrush(qcolor("SELECTION_GOLD"))
            handle.setPen(QPen(qcolor("HANDLE_BORDER"), 1))
            handle.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            handle.setZValue(11)
            self._scene.addItem(handle)
            self._resize_handles[corner] = handle
        self._progress_item = QGraphicsRectItem()
        progress_pen = QPen(qcolor("PROGRESS_CYAN"))
        progress_pen.setWidthF(1.0)
        progress_pen.setCosmetic(True)
        progress_pen.setStyle(Qt.PenStyle.DashLine)
        self._progress_item.setPen(progress_pen)
        self._progress_item.setBrush(qcolor("PROGRESS_CYAN", 18))
        self._progress_item.setZValue(9)
        self._progress_item.setVisible(False)
        self._scene.addItem(self._progress_item)
        self._progress_offset: tuple[int, int] | None = None
        self.offset_editable = False
        self._offset_drag_start: QPointF | None = None
        self._offset_at_drag: tuple[int, int] | None = None
        self._selection_start: QPointF | None = None
        self._resize_corner: str | None = None
        self._resize_anchor: QPointF | None = None
        self._panning = False
        self._pan_start: QPoint | None = None

    def set_pixmap(self, pixmap: QPixmap) -> None:
        self._pixmap_item.setPixmap(pixmap)
        self._scene.setSceneRect(QRectF(pixmap.rect()))

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:  # noqa: N802
        """Xadrez sob a textura, como nos editores de imagem: mostra o que é transparente."""
        painter.fillRect(rect, qcolor("ATLAS_BG"))
        texture = self._pixmap_item.boundingRect()
        if texture.isEmpty():
            return
        painter.save()
        painter.setClipRect(texture)
        painter.fillRect(texture, qcolor("CHECKER_LIGHT"))
        cell = 8 / max(self.transform().m11(), 0.01)  # 8 px de tela em qualquer zoom
        visible = rect.intersected(texture)
        start_x = math.floor(visible.left() / cell)
        start_y = math.floor(visible.top() / cell)
        dark = qcolor("CHECKER_DARK")
        for row in range(start_y, math.ceil(visible.bottom() / cell) + 1):
            for column in range(start_x + (row + start_x) % 2, math.ceil(visible.right() / cell) + 1, 2):
                painter.fillRect(QRectF(column * cell, row * cell, cell, cell), dark)
        painter.restore()

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
            scene_point = self.mapToScene(event.position().toPoint())
            if self._over_offset_box(scene_point):
                # Arrastar a caixa do estado preenchido altera o SOffset, não o recorte.
                self._offset_drag_start = scene_point
                self._offset_at_drag = self._progress_offset
                self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
                event.accept()
                return
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
        if self._offset_drag_start is not None and self._offset_at_drag is not None:
            raw = self.mapToScene(event.position().toPoint())
            dx = round(raw.x() - self._offset_drag_start.x())
            dy = round(raw.y() - self._offset_drag_start.y())
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                # Shift trava no eixo dominante, como no canvas.
                if abs(dx) >= abs(dy):
                    dy = 0
                else:
                    dx = 0
            offset = (self._offset_at_drag[0] + dx, self._offset_at_drag[1] + dy)
            if offset != self._progress_offset:
                self.set_progress_offset(offset)
                self.offset_changed.emit(*offset)
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
        if corner is None and self._over_offset_box(self.mapToScene(event.position().toPoint())):
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
            super().mouseMoveEvent(event)
            return
        if corner in {"top_left", "bottom_right"}:
            self.viewport().setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif corner in {"top_right", "bottom_left"}:
            self.viewport().setCursor(Qt.CursorShape.SizeBDiagCursor)
        else:
            self.viewport().unsetCursor()
        super().mouseMoveEvent(event)

    def _over_offset_box(self, scene_point: QPointF) -> bool:
        return (
            self.offset_editable
            and self._progress_item.isVisible()
            and self._progress_item.rect().normalized().contains(scene_point)
        )

    def offsets_overlap(self) -> bool:
        if not self._progress_item.isVisible():
            return False
        return self._selection_item.rect().normalized().intersects(self._progress_item.rect().normalized())

    def mouseReleaseEvent(self, event):  # noqa: N802
        if self._offset_drag_start is not None and event.button() == Qt.MouseButton.LeftButton:
            self._offset_drag_start = None
            self._offset_at_drag = None
            self.viewport().unsetCursor()
            event.accept()
            return
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
        apply_callback: Callable[[UVRect, bool, tuple[int, int] | None], None],
        parent=None,
        progress_offset: tuple[int, int] | None = None,
        offset_editable: bool = False,
        texture_path: Path | None = None,
    ):
        super().__init__(parent)
        self.texture_name = texture_name
        self.texture_path = texture_path
        self._apply_callback = apply_callback
        self.setWindowTitle(self.tr("Atlas DDS — {name}").format(name=texture_name))
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
        self.resize(1180, 820)

        self.title = QLabel(texture_name)
        self.title.setObjectName("panelTitle")
        self.details = QLabel()
        self.details.setObjectName("panelSubtitle")
        self.cursor_label = QLabel(self.tr("Cursor: —"))
        self.cursor_label.setObjectName("monoCaption")

        self.view = AtlasView()
        self.view.setMinimumSize(760, 560)
        self.view.selection_changed.connect(self._selection_changed)
        self.view.offset_changed.connect(self._offset_dragged)
        self.view.offset_editable = offset_editable and progress_offset is not None
        self.view.cursor_moved.connect(
            lambda x, y: self.cursor_label.setText(self.tr("Cursor: X {x} · Y {y}").format(x=x, y=y))
        )
        self.focus_button = QPushButton(self.tr("Centralizar seleção"))
        self.focus_button.setToolTip(
            self.tr("Aproxima e enquadra o recorte NorUV selecionado atualmente.")
        )
        self.focus_button.clicked.connect(self.view.focus_selection)
        self.full_atlas_button = QPushButton(self.tr("Ver atlas inteiro"))
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

        self.resize_element = QCheckBox(self.tr("Elemento com o tamanho do recorte"))
        explanation = QLabel(
            self.tr(
                "Arraste sobre a imagem para marcar o recorte ou use as alças nos cantos "
                "para ajustar a seleção atual. As coordenadas começam em "
                "(0, 0) no canto superior esquerdo. O botão do meio navega e a roda aplica zoom."
            )
        )
        explanation.setWordWrap(True)
        explanation.setObjectName("panelSubtitle")
        self.progress_explanation = QLabel()
        self.progress_explanation.setWordWrap(True)
        self.progress_explanation.setObjectName("progressHint")
        self.offset_x_spin = QSpinBox()
        self.offset_y_spin = QSpinBox()
        for spin in (self.offset_x_spin, self.offset_y_spin):
            spin.setRange(-100000, 100000)
            spin.setEnabled(self.view.offset_editable)
            spin.valueChanged.connect(self._offset_spins_changed)
        self.overlap_warning = QLabel(
            self.tr("Os dois estados se sobrepõem: cada um vai mostrar pedaços do outro no jogo.")
        )
        self.overlap_warning.setWordWrap(True)
        self.overlap_warning.setObjectName("warningHint")
        self.overlap_warning.hide()
        if progress_offset is not None:
            self.progress_explanation.setText(
                self.tr("Arraste a caixa ciano até o desenho do estado preenchido; o jogo o desenha deslocado do recorte normal por este SOffset.")
                if self.view.offset_editable
                else self.tr("O jogo desenha o estado preenchido deslocado do recorte normal por este SOffset.")
            )
            with QSignalBlocker(self.offset_x_spin), QSignalBlocker(self.offset_y_spin):
                self.offset_x_spin.setValue(progress_offset[0])
                self.offset_y_spin.setValue(progress_offset[1])
        else:
            self.progress_explanation.hide()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Apply
            | QDialogButtonBox.StandardButton.Close
        )
        buttons.button(QDialogButtonBox.StandardButton.Apply).setText(self.tr("Aplicar"))
        buttons.button(QDialogButtonBox.StandardButton.Close).setText(self.tr("Fechar"))
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(
            self._apply
        )
        buttons.rejected.connect(self.close)

        # Campos compactos com prefixo, como no inspector; o nome no XML vai na dica.
        for spin, prefix, tip in (
            (self.left_spin, "X   ", "NorUVLeft"),
            (self.top_spin, "Y   ", "NorUVTop"),
            (self.width_spin, self.tr("L   "), "NorUVWidth"),
            (self.height_spin, self.tr("A   "), "NorUVHeight"),
            (self.offset_x_spin, "X   ", "SOffset-0 x"),
            (self.offset_y_spin, "Y   ", "SOffset-0 y"),
        ):
            spin.setPrefix(prefix)
            spin.setToolTip(tip)
            spin.setObjectName("monoSpin")
            spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
            spin.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        uv_grid = QGridLayout()
        uv_grid.setSpacing(8)
        uv_grid.addWidget(self.left_spin, 0, 0)
        uv_grid.addWidget(self.top_spin, 0, 1)
        uv_grid.addWidget(self.width_spin, 1, 0)
        uv_grid.addWidget(self.height_spin, 1, 1)
        offset_grid = QGridLayout()
        offset_grid.setContentsMargins(0, 0, 0, 0)
        offset_grid.setSpacing(8)
        offset_grid.addWidget(self.offset_x_spin, 0, 0)
        offset_grid.addWidget(self.offset_y_spin, 0, 1)
        self.offset_box = QWidget()
        self.offset_box.setLayout(offset_grid)

        self.focus_button.setIcon(icon("focus", size=16))
        self.full_atlas_button.setIcon(icon("frame", size=16))
        self.focus_button.setText(self.tr("Recorte"))
        self.full_atlas_button.setText(self.tr("Atlas inteiro"))
        self.title.setText(texture_name)
        explanation.setText(
            self.tr("Arraste para marcar · alças ajustam · botão do meio navega · roda = zoom")
        )

        uv_card = self._card(
            self._legend(qcolor("SELECTION_GOLD"), self.tr("RECORTE NORMAL (NorUV)")),
            uv_grid,
            self.resize_element,
        )
        self.offset_card = self._card(
            self._legend(qcolor("PROGRESS_CYAN"), self.tr("ESTADO PREENCHIDO (SOffset)")),
            None,
            self.progress_explanation,
            self.offset_box,
            self.overlap_warning,
        )
        self.offset_card.setVisible(progress_offset is not None)

        self.open_dds_button = QPushButton(self.tr("Abrir .dds"))
        self.open_dds_button.setIcon(icon("image", size=16))
        self.open_dds_button.setToolTip(
            self.tr("Abre esta textura no aplicativo padrão do sistema.")
        )
        self.open_dds_button.setEnabled(texture_path is not None)
        self.open_dds_button.setAutoDefault(False)
        self.open_dds_button.clicked.connect(self._open_dds)

        side_widget = QWidget()
        side_widget.setObjectName("propertiesPanel")
        side_widget.setFixedWidth(320)
        side = QVBoxLayout(side_widget)
        side.setContentsMargins(16, 16, 16, 16)
        side.setSpacing(12)
        side.addWidget(self.title)
        side.addWidget(self.details)
        side.addLayout(view_buttons)
        side.addWidget(uv_card)
        side.addWidget(self.offset_card)
        side.addWidget(self.open_dds_button)
        side.addStretch(1)
        side.addWidget(explanation)
        side.addWidget(self.cursor_label)
        side.addWidget(buttons)
        apply_button = buttons.button(QDialogButtonBox.StandardButton.Apply)
        apply_button.setObjectName("accentPush")
        apply_button.setDefault(True)

        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)
        content.addWidget(self.view, 1)
        content.addWidget(side_widget)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(content)

        self.reload_pixmap(pixmap, fit=True)
        self.view.set_progress_offset(progress_offset)
        self.set_uv(uv)
        install_pointer_cursors(self)

    def _open_dds(self) -> None:
        path = self.texture_path
        if path is None:
            return
        if not path.is_file():
            QMessageBox.warning(
                self,
                self.tr("Abrir .dds"),
                self.tr("O arquivo de textura não foi encontrado: {path}").format(path=path),
            )
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve()))):
            QMessageBox.warning(
                self,
                self.tr("Abrir .dds"),
                self.tr("Não foi possível abrir {name}. Verifique o aplicativo padrão para arquivos .dds no sistema.").format(name=path.name),
            )

    @staticmethod
    def _legend(color, text: str) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        swatch = QLabel()
        swatch.setFixedSize(10, 10)
        swatch.setStyleSheet(f"background: {color.name()}; border-radius: 2px;")
        label = QLabel(text)
        label.setObjectName("sectionLabel")
        layout.addWidget(swatch)
        layout.addWidget(label)
        layout.addStretch(1)
        return row

    @staticmethod
    def _card(header: QWidget, inner_layout, *widgets: QWidget) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        layout.addWidget(header)
        if inner_layout is not None:
            layout.addLayout(inner_layout)
        for widget in widgets:
            layout.addWidget(widget)
        return card

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
        self._update_overlap()

    def _update_overlap(self) -> None:
        self.overlap_warning.setVisible(self.view.offsets_overlap())

    def current_offset(self) -> tuple[int, int] | None:
        if self.offset_card.isHidden():
            return None
        return self.offset_x_spin.value(), self.offset_y_spin.value()

    def _offset_dragged(self, x: int, y: int) -> None:
        with QSignalBlocker(self.offset_x_spin), QSignalBlocker(self.offset_y_spin):
            self.offset_x_spin.setValue(x)
            self.offset_y_spin.setValue(y)
        self._update_overlap()

    def _offset_spins_changed(self, _value: int) -> None:
        self.view.set_progress_offset(self.current_offset())
        self._update_overlap()

    def _selection_changed(self, uv: UVRect) -> None:
        self.set_uv(uv)

    def _spins_changed(self, _value: int) -> None:
        self.view.set_selection(self.current_uv())
        self._update_overlap()

    def current_uv(self) -> UVRect:
        return UVRect(
            self.left_spin.value(),
            self.top_spin.value(),
            self.width_spin.value(),
            self.height_spin.value(),
        )

    def _apply(self) -> None:
        self._apply_callback(self.current_uv(), self.resize_element.isChecked(), self.current_offset())
