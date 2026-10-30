from __future__ import annotations

from collections.abc import Callable
import math
import os
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QPointF, QRectF, QSizeF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QFontMetricsF,
    QImage,
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
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QWidget,
)

from .theme import qcolor
from .i18n import kind_label
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
    """Alça de redimensionamento com tamanho constante na tela."""

    HIT_RECT = QRectF(-9, -9, 18, 18)

    def __init__(self, owner: "ElementItem"):
        super().__init__(QRectF(-5, -5, 10, 10), owner)
        self.owner = owner
        self.axes: tuple[int, int] | None = None
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
            self.owner.begin_resize(event.scenePos(), axes=self.axes)
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


class WindowFrameItem(QGraphicsRectItem):
    """Permite arrastar a janela também pela área fora do conteúdo."""

    def __init__(self, owner: "ElementItem"):
        super().__init__(owner)
        self.owner = owner
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)

    def mousePressEvent(self, event):  # noqa: N802
        self.owner.mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        self.owner.mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        self.owner.mouseReleaseEvent(event)


# Fonte da UI no cliente em português/inglês (Font.ini: DefMainFont=Arial, DefMainFontSize=8).
# O FontFace do XML (細明體) só vale no cliente chinês.
GAME_FONT_FAMILY = "Arial"
GAME_FONT_PIXELS = 11
TEXT_OUTLINE = 1  # FontStyle="1": contorno preto em volta das letras


_game_font_family: str | None = None


def game_font_family() -> str:
    """Carrega a Arial do Windows uma vez: sem ela o Qt troca por outra fonte e as medidas mudam."""
    global _game_font_family
    if _game_font_family is None:
        _game_font_family = GAME_FONT_FAMILY
        windows_font = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "arial.ttf"
        if windows_font.is_file():
            font_id = QFontDatabase.addApplicationFont(str(windows_font))
            families = QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
            if families:
                _game_font_family = families[0]
    return _game_font_family


def game_color(value: str) -> QColor:
    """FontColor vem como inteiro BGR do Windows (65535 = amarelo)."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = 0xFFFFFF
    return QColor(number & 0xFF, (number >> 8) & 0xFF, (number >> 16) & 0xFF)


class GameTextItem(QGraphicsItem):
    """Texto desenhado como o jogo: Arial 8 sem suavização, cor, contorno e alinhamento do XML.

    O jogo escreve os textos por cima de todas as texturas, então o item fica acima dos
    elementos na cena e acompanha o controle dono (ver ElementItem.itemChange).
    """

    Z_VALUE = 900_000.0

    def __init__(self, owner: "ElementItem", props: dict[str, str], is_button: bool = False):
        super().__init__()
        self.owner = owner
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setZValue(self.Z_VALUE)
        self.text = ""
        self.color = game_color(props.get("FontColor", "16777215"))
        self.outline = props.get("FontStyle") == "1"
        # Botões o jogo centraliza sempre; os demais seguem o TextAlign.
        self.align = "1" if is_button else props.get("TextAlign", "0")
        self.multiline = props.get("MultiLine") == "1"
        self.font = QFont(game_font_family())
        self.font.setPixelSize(GAME_FONT_PIXELS)
        self.font.setStyleStrategy(QFont.StyleStrategy.NoAntialias)
        if self.outline:
            # Medido no jogo: texto com contorno sai com 1 px a mais entre as letras
            # ("Ranque da Guilda" 99 px em vez de 84).
            self.font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1)
        self.overflows = False
        self._image: QImage | None = None
        self._image_origin = QPointF()

    def _box(self) -> QRectF:
        return self.owner.rect()

    def _flags(self) -> int:
        horizontal = {"1": Qt.AlignmentFlag.AlignHCenter, "2": Qt.AlignmentFlag.AlignRight}.get(
            self.align, Qt.AlignmentFlag.AlignLeft
        )
        vertical = Qt.AlignmentFlag.AlignTop if self.multiline else Qt.AlignmentFlag.AlignVCenter
        # Caixas minúsculas (1-2 px) são comuns: o jogo escreve o texto mesmo assim, para fora.
        flags = int(horizontal | vertical) | int(Qt.TextFlag.TextDontClip)
        if self.multiline:
            flags |= int(Qt.TextFlag.TextWordWrap)
        return flags

    def set_text(self, text: str) -> None:
        self.prepareGeometryChange()
        self.text = text
        box = self._box()
        needed = QFontMetricsF(self.font).boundingRect(box, self._flags(), text)
        # Só estouro na largura conta: linhas de lista têm a altura justa do texto.
        # Caixas minúsculas são reposicionadas pelo próprio jogo.
        self.overflows = bool(text) and box.width() >= 4 and needed.width() > box.width() + 0.5
        self._render(box, needed)
        self.update()

    def _render(self, box: QRectF, needed: QRectF) -> None:
        """Desenha o texto uma vez, em pixels do jogo; com zoom só a imagem é ampliada.

        Desenhar o texto direto na cena com zoom deixa o Qt reposicionar cada cópia do
        contorno de um jeito e o contorno sai com falhas, o que o jogo não faz.
        """
        self._image = None
        if not self.text:
            return
        margin = TEXT_OUTLINE + 1
        area = box.united(needed).adjusted(-margin, -margin, margin, margin)
        left, top = math.floor(area.left()), math.floor(area.top())
        image = QImage(
            math.ceil(area.right()) - left, math.ceil(area.bottom()) - top,
            QImage.Format.Format_ARGB32_Premultiplied,
        )
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, False)
        painter.setFont(self.font)
        flags = self._flags()
        target = box.translated(-left, -top)
        if self.outline:
            # Uma máscara do texto, carimbada em preto nos 8 vizinhos: contorno sem falhas.
            mask = QImage(image.size(), QImage.Format.Format_ARGB32_Premultiplied)
            mask.fill(Qt.GlobalColor.transparent)
            mask_painter = QPainter(mask)
            mask_painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, False)
            mask_painter.setFont(self.font)
            mask_painter.setPen(QColor(0, 0, 0))
            mask_painter.drawText(target, flags, self.text)
            mask_painter.end()
            for dx in (-TEXT_OUTLINE, 0, TEXT_OUTLINE):
                for dy in (-TEXT_OUTLINE, 0, TEXT_OUTLINE):
                    if dx or dy:
                        painter.drawImage(dx, dy, mask)
        painter.setPen(self.color)
        painter.drawText(target, flags, self.text)
        painter.end()
        self._image = image
        self._image_origin = QPointF(left, top)

    def boundingRect(self) -> QRectF:  # noqa: N802
        if self._image is None:
            return QRectF()
        return QRectF(self._image_origin, QSizeF(self._image.size())).united(self._box())

    def paint(self, painter: QPainter, _option, _widget=None) -> None:
        if self._image is None:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.drawImage(self._image_origin, self._image)
        if self.overflows:
            # Texto maior que a caixa: no jogo ele vaza por cima dos vizinhos.
            painter.setPen(QPen(QColor(255, 60, 60), 0))
            painter.drawRect(self._box())
        painter.restore()


class ElementItem(QGraphicsRectItem):
    SELECTION_Z_BASE = 1_000_000.0
    WINDOW_HANDLE_AXES = {
        "top_left": (-1, -1), "top": (0, -1), "top_right": (1, -1),
        "right": (1, 0), "bottom_right": (1, 1), "bottom": (0, 1),
        "bottom_left": (-1, 1), "left": (-1, 0),
    }

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
        self._group_resize_starts: dict[
            int, tuple["ElementItem", tuple[int, int, int, int]]
        ] = {}
        self._resize_bounds = QRectF()
        self._labels_enabled = False
        self._textures_enabled = True
        self._preview_mode = False
        self.preview_offset = QPointF()
        # Moldura da janela: a raiz é desenhada em volta do conteúdo e arrastá-la
        # leva os demais elementos junto (ver set_content_frame).
        self._frame_mode = False
        # Janela principal: arrastá-la sozinha leva os outros elementos junto.
        self.carries_content = False
        self._frame_offset = (0, 0)
        self._frame_geometry: Callable[[int, int], QRectF] | None = None
        self._frame_window_rect = QRectF()
        self._frame_resize_scale = (1.0, 1.0)
        self._frame_anchor_delta = (0.0, 0.0)
        self._active_resize_scale = (1.0, 1.0)
        self._followers: list[tuple["ElementItem", QPointF]] = []
        self._base_z = float(element.index)
        self._element_position = QPointF(element.x, element.y)
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
        self.text_item: GameTextItem | None = None
        self._text_props = dict(element.text_props)
        self._is_button = "ButtonNode" in element.child_tags
        if pixmap is not None:
            self.texture_item = QGraphicsPixmapItem(pixmap, self)
            self.texture_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self.texture_item.setZValue(-1)

        label = f"{element.window_id} · {kind_label(element.kind, element.ctrl_type)}"
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
        self.window_resize_handles: dict[str, ResizeHandle] = {}
        self.window_bounds_item = WindowFrameItem(self)
        self.window_bounds_item.setPen(self._selected_pen)
        self.window_bounds_item.setZValue(10)
        self.window_bounds_item.setVisible(False)
        self.window_size_item = QGraphicsSimpleTextItem(self.window_bounds_item)
        self.window_size_item.setBrush(qcolor("SELECTION_GOLD"))
        self.window_size_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self.window_size_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self._update_overlays()
        self._update_texture_transform()
        details = [
            f"WindowID: {element.window_id}",
            QCoreApplication.translate("ElementItem", "Tipo: {kind}").format(
                kind=kind_label(element.kind, element.ctrl_type)
            ),
        ]
        if element.window_text:
            details.append(QCoreApplication.translate("ElementItem", "Texto: {text}").format(text=element.window_text))
        if element.parent_id:
            details.append(f"ParentNode: {element.parent_id}")
        details.append(
            QCoreApplication.translate("ElementItem", "Posição: ({x}, {y}) · Tamanho: {width} × {height}").format(
                x=element.x, y=element.y, width=element.width, height=element.height
            )
        )
        if element.texture_name:
            details.append(QCoreApplication.translate("ElementItem", "Textura: {name}").format(name=element.texture_name))
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
        handles = self.window_resize_handles.values() if self._frame_mode else [self.resize_handle]
        if any(handle.isVisible() and handle.shape().contains(handle.mapFromScene(scene_position))
               for handle in handles):
            return True
        return self.window_bounds_item.isVisible() and self.window_bounds_item.shape().contains(
            self.window_bounds_item.mapFromScene(scene_position)
        )

    def set_preview_mode(self, enabled: bool) -> None:
        """Esconde contornos do editor para aproximar a visão do jogo."""
        self._preview_mode = enabled
        self.setBrush(Qt.BrushStyle.NoBrush if enabled else qcolor("ELEMENT_OVERLAY", 8))
        if not self.isSelected():
            self.setPen(self._idle_pen())

    def set_preview_offset(self, offset: QPointF) -> None:
        """Ajusta só a exibição; pos() continua sendo a coordenada editável do XML."""
        self.preview_offset = QPointF(offset)
        self.setTransform(QTransform.fromTranslate(offset.x(), offset.y()))

    def _idle_pen(self) -> QPen:
        return QPen(Qt.PenStyle.NoPen) if self._preview_mode else self._normal_pen

    def setRect(self, *args) -> None:  # noqa: N802
        super().setRect(*args)
        if getattr(self, "text_item", None) is not None:
            self.text_item.set_text(self.text_item.text)

    def set_game_text(self, text: str) -> None:
        """Mostra (ou some com, se vazio) o texto como o jogo desenharia."""
        if self.text_item is None:
            if not text:
                return
            self.text_item = GameTextItem(self, self._text_props, self._is_button)
            if self.scene() is not None:
                self.scene().addItem(self.text_item)
            self._sync_text_item()
        self.text_item.set_text(text)

    def _sync_text_item(self) -> None:
        if self.text_item is not None:
            self.text_item.setPos(self.scenePos())
            self.text_item.setVisible(self.isVisible())

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
        self._update_overlays()
        self.setCursor(
            Qt.CursorShape.ArrowCursor if locked else Qt.CursorShape.SizeAllCursor
        )

    def apply_element(self, element: UIElement) -> None:
        self._element_width = element.width
        self._element_height = element.height
        self._frame_mode = False
        self._frame_geometry = None
        self._element_position = QPointF(element.x, element.y)
        self.resize_handle.axes = None
        self.window_bounds_item.setVisible(False)
        self.setPos(element.x, element.y)
        self.setRect(QRectF(0, 0, max(1, element.width), max(1, element.height)))
        self._update_texture_transform()
        self._update_overlays()
        self.resize_handle.setVisible(self.isSelected() and not self._locked)
        if self.texture_item is not None:
            self.texture_item.setVisible(self._textures_enabled and not self.texture_item.pixmap().isNull())

    @property
    def frame_mode(self) -> bool:
        return self._frame_mode

    def set_content_frame(
        self, rect: QRectF, offset: tuple[int, int],
        frame_geometry: Callable[[int, int], QRectF],
    ) -> None:
        """Desenha a raiz em volta do conteúdo, onde o jogo o mostra.

        Numa janela que o jogo posiciona sozinho, o retângulo real da raiz fica
        preso ao centro (ou a um canto) e o que o usuário enxerga como "a janela"
        é o conteúdo. `offset` converte a posição no canvas em posição na tela.
        """
        self._frame_mode = True
        self._frame_offset = offset
        self._frame_geometry = frame_geometry
        self._frame_window_rect = frame_geometry(self._element_width, self._element_height)
        # Choose the corner that actually moves when this anchored window changes
        # size. For a bottom-centred window this is the upper-left corner.
        probe = frame_geometry(self._element_width + 2, self._element_height + 2)
        dx = (probe.left() - self._frame_window_rect.left()) / 2
        dy = (probe.top() - self._frame_window_rect.top()) / 2
        self._frame_anchor_delta = (dx, dy)
        self._frame_resize_scale = (1 / dx if dx else 1.0, 1 / dy if dy else 1.0)
        default_axes = (-1 if dx else 1, -1 if dy else 1)
        default_key = next(key for key, axes in self.WINDOW_HANDLE_AXES.items() if axes == default_axes)
        if not self.window_resize_handles:
            self.window_resize_handles = {
                key: self.resize_handle if key == default_key else ResizeHandle(self)
                for key in self.WINDOW_HANDLE_AXES
            }
        elif self.window_resize_handles[default_key] is not self.resize_handle:
            previous = next(key for key, handle in self.window_resize_handles.items() if handle is self.resize_handle)
            self.window_resize_handles[previous] = self.window_resize_handles[default_key]
            self.window_resize_handles[default_key] = self.resize_handle
        self.setPos(rect.topLeft())
        self.setRect(QRectF(0, 0, max(1, rect.width()), max(1, rect.height())))
        self._update_overlays()
        self.resize_handle.setVisible(self.isSelected() and not self._locked)
        # A textura da raiz continua onde a raiz está no XML (como em "Sem tela do jogo"):
        # em várias janelas, como a da guilda, ela é o fundo dos painéis.
        self._update_texture_transform()

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value):  # noqa: N802
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            position = QPointF(value)
            return QPointF(round(position.x()), round(position.y()))
        if change in (
            QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged,
            QGraphicsItem.GraphicsItemChange.ItemVisibleHasChanged,
        ):
            self._sync_text_item()
        if change == QGraphicsItem.GraphicsItemChange.ItemSceneChange and self.text_item is not None:
            # Elemento saindo da cena (apagado, cena refeita): o texto vai junto.
            if self.text_item.scene() is not None:
                self.text_item.scene().removeItem(self.text_item)
            if value is not None:
                value.addItem(self.text_item)
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            self.prepareGeometryChange()
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            selected = bool(value)
            self.setZValue(
                self.SELECTION_Z_BASE + self._base_z if selected else self._base_z
            )
            self.setPen(self._selected_pen if selected else self._idle_pen())
            self.label_item.setVisible(self._labels_enabled or selected)
            self.resize_handle.setVisible(selected and not self._locked)
            self._update_overlays()
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
        self._followers = []
        carries = self._frame_mode or self.carries_content
        if carries and set(self._group_drag_starts) == {self.element_index} and self.scene() is not None:
            self._followers = [
                (item, QPointF(item.pos()))
                for item in self.scene().items()
                if isinstance(item, ElementItem) and item is not self
            ]
        super().mousePressEvent(event)

    def _move_followers(self) -> None:
        delta = self.pos() - self._drag_start_position
        for item, start_position in self._followers:
            item.setPos(start_position + delta)

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
            self._move_followers()
            self._show_drag_position(self._locked_axis)
            event.accept()
            return
        # Soltar Shift durante o arraste devolve imediatamente o movimento livre.
        self._locked_axis = None
        super().mouseMoveEvent(event)
        self._move_followers()
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
        # O conteúdo só acompanhou o arraste; quem muda no XML é a raiz.
        for item, start_position in self._followers:
            item.setPos(start_position)
        self._followers = []
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
        offset = self._frame_offset if self._frame_mode else (0, 0)
        self.drag_position_item.setText(
            f"X {round(position.x()) + offset[0]} · Y {round(position.y()) + offset[1]}{suffix}"
        )
        self._update_overlays()
        self.drag_position_item.setVisible(True)

    def _update_overlays(self) -> None:
        rect = self.rect()
        if self._frame_mode:
            self.setPen(self._idle_pen())
            bounds = self._frame_window_rect.translated(-self.pos())
            self.window_bounds_item.setRect(bounds)
            self.window_bounds_item.setVisible(self.isSelected())
            self.window_bounds_item.setCursor(
                Qt.CursorShape.ArrowCursor if self._locked else Qt.CursorShape.SizeAllCursor
            )
            self.window_size_item.setText(f"{round(bounds.width())} × {round(bounds.height())}")
            self.window_size_item.setPos(bounds.topLeft() + QPointF(8, 2))
            for key, handle in self.window_resize_handles.items():
                ax, ay = self.WINDOW_HANDLE_AXES[key]
                handle.axes = (ax, ay)
                handle.setPos(
                    bounds.center().x() if not ax else bounds.left() if ax < 0 else bounds.right(),
                    bounds.center().y() if not ay else bounds.top() if ay < 0 else bounds.bottom(),
                )
                handle.setCursor(
                    Qt.CursorShape.SizeVerCursor if not ax else
                    Qt.CursorShape.SizeHorCursor if not ay else
                    Qt.CursorShape.SizeFDiagCursor if ax * ay > 0 else Qt.CursorShape.SizeBDiagCursor
                )
                handle.setVisible(self.isSelected() and not self._locked)
        else:
            for handle in self.window_resize_handles.values():
                if handle is not self.resize_handle:
                    handle.setVisible(False)
            self.resize_handle.setPos(rect.width(), rect.height())
            self.resize_handle.setCursor(Qt.CursorShape.SizeFDiagCursor)
        self.drag_position_item.setPos(2, max(1, rect.height()) + 7)

    def _update_texture_transform(self) -> None:
        if self.texture_item is None or self.texture_item.pixmap().isNull():
            return
        pixmap = self.texture_item.pixmap()
        if self._frame_mode:
            # A moldura cobre o conteúdo; a textura fica no retângulo real da raiz.
            width, height = self._element_width, self._element_height
            self.texture_item.setPos(self._element_position - self.pos())
        else:
            width, height = self.rect().width(), self.rect().height()
            self.texture_item.setPos(0, 0)
        self.texture_item.setTransform(
            QTransform.fromScale(max(1, width) / pixmap.width(), max(1, height) / pixmap.height())
        )

    def begin_resize(
        self, scene_position: QPointF, *, axes: tuple[int, int] | None = None
    ) -> None:
        self._group_resize_starts.clear()
        if self._locked:
            return
        position = self.pos()
        self._resize_start_scene_position = QPointF(scene_position)
        self._active_resize_scale = self._frame_resize_scale
        if self._frame_mode and axes is not None:
            scales = []
            for axis, anchor in zip(axes, self._frame_anchor_delta):
                # The client can pin an edge (Menu's bottom). It still adjusts
                # the size, while the pinned edge stays put in the preview.
                derivative = anchor + (1 if axis > 0 else 0)
                scales.append(0.0 if not axis else 1 / derivative if derivative else float(axis))
            self._active_resize_scale = tuple(scales)
        self._resize_start_geometry = (
            round(position.x()),
            round(position.y()),
            self._element_width,
            self._element_height,
        )
        items = [
            item
            for item in (self.scene().selectedItems() if self.scene() else [])
            if isinstance(item, ElementItem)
            and not item._locked and not item._frame_mode and item.isVisible()
        ] if self.isSelected() and not self._frame_mode else []
        if len(items) > 1:
            bounds = QRectF()
            for item in items:
                geometry = (
                    round(item.pos().x()), round(item.pos().y()),
                    item._element_width, item._element_height,
                )
                self._group_resize_starts[item.element_index] = (item, geometry)
                x, y, width, height = geometry
                bounds = bounds.united(QRectF(x, y, max(1, width), max(1, height)))
            self._resize_bounds = bounds

    def resize_to(
        self, scene_position: QPointF, *, proportional: bool = False
    ) -> None:
        if self._locked:
            return
        delta = scene_position - self._resize_start_scene_position
        if self._frame_mode:
            sx, sy = self._active_resize_scale
            delta = QPointF(delta.x() * sx, delta.y() * sy)
        if self._group_resize_starts:
            self._resize_group(delta, proportional=proportional)
            return
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
        if self._frame_mode and self._frame_geometry is not None:
            self._frame_window_rect = self._frame_geometry(width, height)
        else:
            self.setRect(QRectF(0, 0, width, height))
        self._update_texture_transform()
        self._update_overlays()
        self.drag_position_item.setText(
            QCoreApplication.translate("ElementItem", "L {width} · A {height}").format(
                width=width, height=height
            )
        )
        self.drag_position_item.setVisible(True)

    def _resize_group(self, delta: QPointF, *, proportional: bool) -> None:
        bounds = self._resize_bounds
        sx = (bounds.width() + delta.x()) / bounds.width()
        sy = (bounds.height() + delta.y()) / bounds.height()
        # Keep every nonzero dimension at least one pixel without collapsing gaps.
        min_sx = max(
            (1 / g[2] for _, g in self._group_resize_starts.values() if g[2] > 0),
            default=1 / bounds.width(),
        )
        min_sy = max(
            (1 / g[3] for _, g in self._group_resize_starts.values() if g[3] > 0),
            default=1 / bounds.height(),
        )
        if proportional:
            scale = sx if abs(sx - 1) >= abs(sy - 1) else sy
            sx = sy = max(scale, min_sx, min_sy)
        else:
            sx, sy = max(sx, min_sx), max(sy, min_sy)
        for item, (x, y, width, height) in self._group_resize_starts.values():
            item.setPos(
                round(bounds.left() + (x - bounds.left()) * sx),
                round(bounds.top() + (y - bounds.top()) * sy),
            )
            # Zero dimensions are meaningful in the XML (e.g. text controls).
            new_width = max(1, round(width * sx)) if width else 0
            new_height = max(1, round(height * sy)) if height else 0
            item._element_width, item._element_height = new_width, new_height
            item.setRect(QRectF(0, 0, max(1, new_width), max(1, new_height)))
            item._update_texture_transform()
            item._update_overlays()
        self.drag_position_item.setText(
            QCoreApplication.translate("ElementItem", "L {width} · A {height}").format(
                width=round(bounds.width() * sx), height=round(bounds.height() * sy)
            )
        )
        self.drag_position_item.setVisible(True)

    def end_resize(self) -> None:
        self.drag_position_item.setVisible(False)
        if self._group_resize_starts:
            changes = {}
            for index, (item, old) in self._group_resize_starts.items():
                new = (
                    round(item.pos().x()), round(item.pos().y()),
                    item._element_width, item._element_height,
                )
                if new != old:
                    changes[index] = (old, new)
            self._group_resize_starts.clear()
            if changes:
                self._moved_callback(changes)
            return
        position = self.pos()
        rect = self._frame_window_rect if self._frame_mode else self.rect()
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


class GameDrawnItem(QGraphicsRectItem):
    """Área que o jogo desenha por código (sem textura no XML), como a foto do personagem.

    O jogo a desenha num ponto fixo da tela, não relativo à janela: mover a janela no
    XML não leva a marcação junto. Fica por cima dos elementos para as texturas não a esconderem.
    """

    def __init__(self, rect: QRectF, label: str):
        super().__init__(rect)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setBrush(qcolor("POSITION_CYAN", 40))
        self.setPen(QPen(qcolor("POSITION_CYAN", 220), 0, Qt.PenStyle.DashLine))
        self.setZValue(ElementItem.SELECTION_Z_BASE * 2)
        self.setToolTip(label)
        text = QGraphicsSimpleTextItem(label, self)
        text.setBrush(qcolor("POSITION_CYAN"))
        text.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        text.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        text.setPos(rect.left() + 2, rect.bottom() - 12)


class ReferenceLayerItem(QGraphicsRectItem):
    """Outra janela do projeto desenhada onde o jogo a põe, só para referência.

    Fica abaixo do arquivo em edição e não recebe cliques: serve para montar a tela
    do jogo (BasicChar, Radar, Menu…) em volta do que está sendo editado.
    """

    Z_VALUE = -1000.0

    def __init__(self, name: str, bounds: QRectF):
        super().__init__(bounds)
        self.name = name
        self.setPen(QPen(Qt.PenStyle.NoPen))
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setZValue(self.Z_VALUE)
        self.setToolTip(name)
        self._owners: list[QGraphicsRectItem] = []

    def add_control(self, rect: QRectF, pixmap: QPixmap | None, text: str = "",
                    props: dict[str, str] | None = None, is_button: bool = False) -> None:
        if pixmap is not None and not pixmap.isNull():
            picture = QGraphicsPixmapItem(pixmap, self)
            picture.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            picture.setPos(rect.topLeft())
        if text:
            # GameTextItem mede a caixa pelo dono; aqui o dono é só um retângulo fora da cena.
            owner = QGraphicsRectItem(QRectF(0, 0, max(1, rect.width()), max(1, rect.height())))
            self._owners.append(owner)
            label = GameTextItem(owner, props or {}, is_button)  # type: ignore[arg-type]
            label.setParentItem(self)
            label.setZValue(1)
            label.setPos(rect.topLeft())
            label.set_text(text)


class GhostAreaItem(QGraphicsRectItem):
    """Área que o jogo ainda trata como janela, longe do conteúdo; não interage."""

    def __init__(self, label: str):
        super().__init__()
        self.setZValue(-0.5)  # acima da tela do jogo, abaixo dos elementos
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setAcceptHoverEvents(False)
        self.setBrush(qcolor("GHOST_AREA", 40))
        self.setPen(QPen(qcolor("GHOST_AREA"), 0, Qt.PenStyle.DashLine))
        self.label_item = QGraphicsSimpleTextItem(label, self)
        self.label_item.setBrush(qcolor("GHOST_AREA"))
        self.label_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self.label_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def set_area(self, rect: QRectF) -> None:
        self.setPos(rect.topLeft())
        self.setRect(QRectF(0, 0, rect.width(), rect.height()))
        self.label_item.setPos(2, rect.height() + 4)


class GameScreenItem(QGraphicsRectItem):
    """Moldura da tela do jogo, com captura opcional ao fundo; não interage."""

    def __init__(self, width: int, height: int, background: QPixmap | None = None):
        super().__init__(QRectF(0, 0, width, height))
        self.setZValue(-1_000_000)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setAcceptHoverEvents(False)
        self.setBrush(qcolor("GAME_SCREEN_BG"))
        self.setPen(QPen(qcolor("GAME_SCREEN_BORDER"), 0, Qt.PenStyle.SolidLine))
        self.background_item: QGraphicsPixmapItem | None = None
        if background is not None and not background.isNull():
            # Preenche a moldura sem distorcer: escala pelo maior fator e corta
            # o excesso, centralizado (uma captura de outra proporção não estica).
            clip = QGraphicsRectItem(QRectF(0, 0, width, height), self)
            clip.setPen(QPen(Qt.PenStyle.NoPen))
            clip.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape)
            clip.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self.background_item = QGraphicsPixmapItem(background, clip)
            self.background_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self.background_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
            scale = max(width / background.width(), height / background.height())
            self.background_item.setTransform(QTransform.fromScale(scale, scale))
            self.background_item.setPos(
                (width - background.width() * scale) / 2, (height - background.height() * scale) / 2
            )
        self.size_label = QGraphicsSimpleTextItem(f"{width} × {height}", self)
        self.size_label.setBrush(qcolor("GAME_SCREEN_BORDER"))
        self.size_label.setFont(QFont("IBM Plex Sans", 9))
        self.size_label.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self.size_label.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.size_label.setPos(0, height + 4)

    def set_caption(self, text: str) -> None:
        self.size_label.setText(text)


class EditorView(QGraphicsView):
    cursor_scene_moved = Signal(int, int)
    zoom_changed = Signal(float)
    DOT_SPACING = 16
    # Roda do mouse por estilo: "corel" dá zoom direto; "paintnet" e
    # "photoshop" rolam a tela e dão zoom com Ctrl/Alt. Botão do meio e
    # Espaço+arrastar movem a tela em todos.
    NAVIGATION_STYLES = ("corel", "paintnet", "photoshop")

    def __init__(self, move_selected: Callable[[int, int], None], parent=None):
        super().__init__(parent)
        self._move_selected = move_selected
        self._cycle_signature: tuple[int, int, tuple[int, ...]] | None = None
        self._cycle_offset = -1
        self._panning = False
        self._pan_start = None
        self._pan_button = Qt.MouseButton.NoButton
        self._space_held = False
        self.navigation_style = "corel"
        self._preferred_item: ElementItem | None = None
        # Duplo clique num elemento (ou no texto que o jogo escreve nele, mesmo vazando
        # para fora da caixa): a janela decide o que abrir.
        self.element_double_clicked: Callable[[ElementItem], None] | None = None
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
            | QPainter.RenderHint.TextAntialiasing
        )
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.setBackgroundBrush(qcolor("CANVAS_BG"))
        self._overlays: list[tuple[QWidget, str]] = []
        # Os pontos do fundo ficam fixos na tela; rolar exige redesenhar tudo.
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
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

    def mouseDoubleClickEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.element_double_clicked is not None:
            for item in self.items(event.position().toPoint()):
                if isinstance(item, GameTextItem) and item.isVisible() and item.text:
                    self.element_double_clicked(item.owner)
                    event.accept()
                    return
            element = self._element_parent(self.itemAt(event.position().toPoint()))
            if element is not None:
                self.element_double_clicked(element)
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.MiddleButton or (
            event.button() == Qt.MouseButton.LeftButton and self._space_held
        ):
            self._panning = True
            self._pan_button = event.button()
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
        if self._panning and event.button() == self._pan_button:
            self._panning = False
            self._pan_start = None
            if self._space_held:
                self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
            else:
                self.viewport().unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        delta = event.angleDelta().y() or event.angleDelta().x()
        if not delta:
            return
        modifiers = event.modifiers()
        ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        alt = bool(modifiers & Qt.KeyboardModifier.AltModifier)
        if self.navigation_style == "paintnet":
            action = "zoom" if ctrl else "horizontal" if shift else "vertical"
        elif self.navigation_style == "photoshop":
            action = "zoom" if alt else "horizontal" if ctrl or shift else "vertical"
        else:
            action = "zoom"
        if action == "zoom":
            self.zoom_by(1.15 if delta > 0 else 1 / 1.15)
        else:
            bar = self.horizontalScrollBar() if action == "horizontal" else self.verticalScrollBar()
            bar.setValue(bar.value() - delta)
        event.accept()

    def zoom_by(self, factor: float) -> None:
        current = self.transform().m11()
        factor = min(max(current * factor, 0.05), 32) / current
        self.scale(factor, factor)
        self.notify_zoom()

    def notify_zoom(self) -> None:
        self.zoom_changed.emit(self.transform().m11())

    def add_overlay(self, widget: QWidget, anchor: str) -> None:
        """Widget flutuante sobre o canvas ("top" ou "bottom-left")."""
        self._overlays.append((widget, anchor))
        widget.show()
        self._place_overlays()

    def _place_overlays(self) -> None:
        for widget, anchor in self._overlays:
            widget.adjustSize()
            if anchor == "top":
                widget.move((self.width() - widget.width()) // 2, 14)
            else:
                widget.move(16, self.height() - widget.height() - 16)
            widget.raise_()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._place_overlays()

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:  # noqa: N802
        """Fundo pontilhado fixo na tela, independente do zoom."""
        painter.fillRect(rect, qcolor("CANVAS_BG"))
        painter.save()
        painter.resetTransform()
        viewport = self.viewport().rect()
        step = self.DOT_SPACING
        painter.setPen(QPen(qcolor("CANVAS_DOT"), 1.4))
        points = [
            QPointF(x, y)
            for x in range(step // 2, viewport.width(), step)
            for y in range(step // 2, viewport.height(), step)
        ]
        painter.drawPoints(points)
        painter.restore()

    def keyReleaseEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_held = False
            if not self._panning:
                self.viewport().unsetCursor()
            event.accept()
            return
        super().keyReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Space:
            if not event.isAutoRepeat():
                self._space_held = True
                if not self._panning:
                    self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return
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


# Ícones de estado na lista de elementos, como nas camadas de um editor de imagem.
STATE_SLOTS = ("hidden", "locked", "isolated")
STATE_ROLE = int(Qt.ItemDataRole.UserRole) + 1
STATE_ICON_SIZE = 14
STATE_SLOT_WIDTH = 20


def state_slot_at(rect_left: float, x: float) -> str | None:
    """Qual ícone (ocultar, bloquear, isolar) está na posição x da célula."""
    slot = int((x - rect_left - 4) // STATE_SLOT_WIDTH)
    return STATE_SLOTS[slot] if 0 <= slot < len(STATE_SLOTS) else None


class ElementStateDelegate(QStyledItemDelegate):
    """Desenha olho, cadeado e foco: apagados quando desligados, acesos quando ligados."""

    def __init__(self, icons: dict[tuple[str, bool], "QIcon"], parent=None):
        super().__init__(parent)
        self._icons = icons

    def sizeHint(self, option: QStyleOptionViewItem, index) -> "QSize":  # noqa: N802
        hint = super().sizeHint(option, index)
        hint.setWidth(STATE_SLOT_WIDTH * len(STATE_SLOTS) + 8)
        return hint

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        clean = QStyleOptionViewItem(option)
        clean.text = ""
        style = option.widget.style() if option.widget is not None else None
        if style is not None:
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, clean, painter, option.widget)
        states = index.data(STATE_ROLE) or ()
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        top = option.rect.top() + (option.rect.height() - STATE_ICON_SIZE) // 2
        for slot, name in enumerate(STATE_SLOTS):
            active = name in states
            if not active and not hovered:
                painter.setOpacity(0.18)
            elif not active:
                painter.setOpacity(0.55)
            left = option.rect.left() + 4 + slot * STATE_SLOT_WIDTH + (STATE_SLOT_WIDTH - STATE_ICON_SIZE) // 2
            self._icons[(name, active)].paint(painter, left, top, STATE_ICON_SIZE, STATE_ICON_SIZE)
            painter.setOpacity(1.0)
