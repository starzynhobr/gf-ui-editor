from __future__ import annotations

from collections.abc import Callable
import math
from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QSignalBlocker, QTimer, Signal, QUrl
from PySide6.QtGui import QDesktopServices, QPainter, QPen, QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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
        self._resize_rect: QRectF | None = None
        # Fora do modo de edição o atlas só navega: clicar não altera o recorte.
        self.editable = True
        self._panning = False
        self._pan_button = Qt.MouseButton.NoButton
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
        visible = not rect.isEmpty() and self.editable
        for corner, handle in self._resize_handles.items():
            handle.setPos(positions[corner])
            handle.setVisible(visible)

    def set_editable(self, editable: bool) -> None:
        self.editable = editable
        self._update_resize_handles()
        self.viewport().unsetCursor()

    def _corner_at(self, viewport_position: QPoint) -> str | None:
        """Alça sob o cursor: um canto ("top_left"…) ou uma borda ("top", "left"…)."""
        for corner, handle in self._resize_handles.items():
            if not handle.isVisible():
                continue
            handle_position = self.mapFromScene(handle.scenePos())
            if (
                abs(handle_position.x() - viewport_position.x()) <= 8
                and abs(handle_position.y() - viewport_position.y()) <= 8
            ):
                return corner
        rect = self._selection_item.rect().normalized()
        if not self.editable or rect.isEmpty():
            return None
        top_left = self.mapFromScene(rect.topLeft())
        bottom_right = self.mapFromScene(rect.bottomRight())
        x, y = viewport_position.x(), viewport_position.y()
        within_x = top_left.x() <= x <= bottom_right.x()
        within_y = top_left.y() <= y <= bottom_right.y()
        if within_x and abs(y - top_left.y()) <= 5:
            return "top"
        if within_x and abs(y - bottom_right.y()) <= 5:
            return "bottom"
        if within_y and abs(x - top_left.x()) <= 5:
            return "left"
        if within_y and abs(x - bottom_right.x()) <= 5:
            return "right"
        return None

    def _resized(self, point: QPointF) -> UVRect:
        """Move só os lados da alça arrastada; os outros ficam onde estavam."""
        assert self._resize_corner is not None and self._resize_rect is not None
        rect = self._resize_rect
        left, top, right, bottom = rect.left(), rect.top(), rect.right(), rect.bottom()
        if "left" in self._resize_corner:
            left = point.x()
        if "right" in self._resize_corner:
            right = point.x()
        if "top" in self._resize_corner:
            top = point.y()
        if "bottom" in self._resize_corner:
            bottom = point.y()
        return self._uv_between(QPointF(left, top), QPointF(right, bottom))

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
        if event.button() == Qt.MouseButton.MiddleButton or (
            event.button() == Qt.MouseButton.LeftButton and not self.editable
        ):
            self._panning = True
            self._pan_button = event.button()
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
                self._resize_rect = self._selection_item.rect().normalized()
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
        if self._resize_corner is not None and self._resize_rect is not None:
            uv = self._resized(point)
            self.set_selection(uv)
            self.selection_changed.emit(uv)
            event.accept()
            return
        if not self.editable:
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
            super().mouseMoveEvent(event)
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
        elif corner in {"left", "right"}:
            self.viewport().setCursor(Qt.CursorShape.SizeHorCursor)
        elif corner in {"top", "bottom"}:
            self.viewport().setCursor(Qt.CursorShape.SizeVerCursor)
        else:
            self.viewport().unsetCursor()
        super().mouseMoveEvent(event)

    def _over_offset_box(self, scene_point: QPointF) -> bool:
        return (
            self.editable
            and self.offset_editable
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
        if self._panning and event.button() == self._pan_button:
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
            uv = self._resized(point)
            self._resize_corner = None
            self._resize_rect = None
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
        button_uvs: dict[str, UVRect] | None = None,
        apply_button_uvs: Callable[[dict[str, UVRect], bool], None] | None = None,
    ):
        super().__init__(parent)
        self.texture_name = texture_name
        self.texture_path = texture_path
        self._apply_callback = apply_callback
        self._button_apply_callback = apply_button_uvs if button_uvs is not None else None
        self._button_uvs = {"NorUV": uv, **button_uvs} if button_uvs is not None else None
        self._active_uv_state = "NorUV"
        self._source_pixmap = pixmap
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
        self.edit_button = QPushButton(self.tr("Editar posição"))
        self.edit_button.setCheckable(True)
        self.edit_button.setObjectName("accentPush")
        self.edit_button.setIcon(icon("frame", "#ffffff", size=16))
        self.edit_button.setToolTip(
            self.tr("Libera o recorte para ser marcado ou ajustado. Sem isto, arrastar só move a vista.")
        )
        self.edit_button.setAutoDefault(False)
        self.edit_button.toggled.connect(self._set_editing)

        self.left_spin = self._spinbox(minimum=-100000)
        self.top_spin = self._spinbox(minimum=-100000)
        self.width_spin = self._spinbox(minimum=0 if button_uvs is not None else 1)
        self.height_spin = self._spinbox(minimum=0 if button_uvs is not None else 1)
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
        self.focus_button.setText(self.tr("Centralizar"))
        self.full_atlas_button.setText(self.tr("Atlas inteiro"))
        self.title.setText(texture_name)
        self.explanation = explanation
        self.view_hint = self.tr("Arraste para mover a vista · roda = zoom · Editar posição libera o recorte")
        self.edit_hint = self.tr("Arraste para marcar · cantos e bordas ajustam · botão do meio navega · roda = zoom")

        self.uv_heading = QLabel(self.tr("RECORTE NORMAL (NorUV)"))
        uv_card = self._card(
            self._legend(qcolor("SELECTION_GOLD"), self.uv_heading),
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

        self.state_combo = QComboBox()
        self.state_combo.setAccessibleName(self.tr("Estado do botão"))
        for state, label in (
            ("NorUV", self.tr("Normal")),
            ("FocusUV", self.tr("Mouse sobre (hover)")),
            ("DownUV", self.tr("Pressionado")),
            ("DisableUV", self.tr("Desativado")),
        ):
            available = self._button_uvs is not None and state in self._button_uvs
            text = label if available else self.tr("{state} — não definido").format(state=label)
            self.state_combo.addItem(text, state)
            self.state_combo.model().item(self.state_combo.count() - 1).setEnabled(available)
        self.state_preview = QLabel()
        self.state_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.state_preview.setFixedHeight(64)
        self.state_card = self._card(QLabel(self.tr("Estado do botão")), None, self.state_combo, self.state_preview)
        self.state_card.setVisible(button_uvs is not None)

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
        side.addWidget(self.edit_button)
        side.addWidget(self.state_card)
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
        self.apply_button = apply_button

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
        self.state_combo.currentIndexChanged.connect(self._state_changed)
        self._offset_allowed = self.view.offset_editable
        self._set_editing(False)
        self._framed = False
        install_pointer_cursors(self)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._framed:
            # Abre já no recorte; com o atlas inteiro não dá para ver o que está selecionado.
            self._framed = True
            QTimer.singleShot(0, self.view.focus_selection)

    def _set_editing(self, editing: bool) -> None:
        self.view.set_editable(editing)
        for spin in (self.left_spin, self.top_spin, self.width_spin, self.height_spin):
            spin.setReadOnly(not editing)
        for spin in (self.offset_x_spin, self.offset_y_spin):
            spin.setEnabled(editing and self._offset_allowed)
        self.resize_element.setEnabled(editing and self._active_uv_state == "NorUV")
        self.apply_button.setEnabled(editing)
        self.explanation.setText(self.edit_hint if editing else self.view_hint)
        self.edit_button.setText(self.tr("Editando posição") if editing else self.tr("Editar posição"))

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
    def _legend(color, text: str | QLabel) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        swatch = QLabel()
        swatch.setFixedSize(10, 10)
        swatch.setStyleSheet(f"background: {color.name()}; border-radius: 2px;")
        label = text if isinstance(text, QLabel) else QLabel(text)
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
        self._source_pixmap = pixmap
        self.view.set_pixmap(pixmap)
        self.details.setText(f"{pixmap.width()} × {pixmap.height()} px")
        self.left_spin.setMaximum(max(0, pixmap.width() - 1))
        self.top_spin.setMaximum(max(0, pixmap.height() - 1))
        self.width_spin.setMaximum(max(1, pixmap.width()))
        self.height_spin.setMaximum(max(1, pixmap.height()))
        if fit:
            self.view.fit_texture()
        self._update_state_preview()

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
        self._update_state_preview()

    def _remember_current_state(self) -> None:
        if self._button_uvs is not None:
            self._button_uvs[self._active_uv_state] = self.current_uv()

    def _state_changed(self, _index: int) -> None:
        state = self.state_combo.currentData()
        if self._button_uvs is None or state not in self._button_uvs:
            return
        self._remember_current_state()
        self._active_uv_state = state
        self.set_uv(self._button_uvs[state])
        self.uv_heading.setText(f"{self.state_combo.currentText()} ({state})")
        for spin, suffix in zip(
            (self.left_spin, self.top_spin, self.width_spin, self.height_spin),
            ("Left", "Top", "Width", "Height"), strict=True,
        ):
            spin.setToolTip(state + suffix)
        self.resize_element.setEnabled(state == "NorUV" and self.edit_button.isChecked())
        self.view.focus_selection()

    def _update_state_preview(self) -> None:
        if self._button_uvs is None:
            return
        uv = self.current_uv()
        image = QPixmap(112, 64)
        image.fill(qcolor("CHECKER_LIGHT"))
        painter = QPainter(image)
        for row in range(8):
            for column in range(row % 2, 14, 2):
                painter.fillRect(column * 8, row * 8, 8, 8, qcolor("CHECKER_DARK"))
        if uv.width > 0 and uv.height > 0:
            cropped = self._source_pixmap.copy(uv.left, uv.top, uv.width, uv.height).scaled(
                56, 56, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation
            )
            painter.drawPixmap((image.width() - cropped.width()) // 2, (image.height() - cropped.height()) // 2, cropped)
        painter.end()
        self.state_preview.setPixmap(image)

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
        self._update_state_preview()

    def current_uv(self) -> UVRect:
        return UVRect(
            self.left_spin.value(),
            self.top_spin.value(),
            self.width_spin.value(),
            self.height_spin.value(),
        )

    def _apply(self) -> None:
        if self._button_apply_callback is not None:
            self._remember_current_state()
            self._button_apply_callback(dict(self._button_uvs), self.resize_element.isChecked())
            return
        self._apply_callback(self.current_uv(), self.resize_element.isChecked(), self.current_offset())
