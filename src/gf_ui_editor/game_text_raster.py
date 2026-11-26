"""Monochrome game text shared by the classic canvas and the web bridge."""

from __future__ import annotations

from base64 import b64encode
from functools import lru_cache
import math
import os
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetricsF, QGuiApplication, QImage, QPainter


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


def game_font(outline: bool) -> QFont:
    font = QFont(game_font_family())
    font.setPixelSize(GAME_FONT_PIXELS)
    font.setStyleStrategy(QFont.StyleStrategy.NoAntialias)
    if outline:
        # In the game, an outlined glyph advances one extra pixel.
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1)
    return font


def text_flags(align: str, multiline: bool) -> int:
    horizontal = {"1": Qt.AlignmentFlag.AlignHCenter, "2": Qt.AlignmentFlag.AlignRight}.get(
        align, Qt.AlignmentFlag.AlignLeft
    )
    vertical = Qt.AlignmentFlag.AlignTop if multiline else Qt.AlignmentFlag.AlignVCenter
    # Small controls still paint their text outside the box in the game.
    flags = int(horizontal | vertical) | int(Qt.TextFlag.TextDontClip)
    return flags | int(Qt.TextFlag.TextWordWrap) if multiline else flags


def paint_text(
    text: str, box: QRectF, bounds: QRectF, font: QFont, flags: int, color: QColor, outline: bool,
) -> tuple[QImage, int, int]:
    """Draw at game scale, preserving pixel placement in box-local coordinates."""
    margin = TEXT_OUTLINE + 1
    area = bounds.adjusted(-margin, -margin, margin, margin)
    left, top = math.floor(area.left()), math.floor(area.top())
    image = QImage(
        math.ceil(area.right()) - left, math.ceil(area.bottom()) - top,
        QImage.Format.Format_ARGB32_Premultiplied,
    )
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, False)
    painter.setFont(font)
    target = box.translated(-left, -top)
    if outline:
        # Uma máscara do texto, carimbada em preto nos 8 vizinhos: contorno sem falhas.
        mask = QImage(image.size(), QImage.Format.Format_ARGB32_Premultiplied)
        mask.fill(Qt.GlobalColor.transparent)
        mask_painter = QPainter(mask)
        mask_painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, False)
        mask_painter.setFont(font)
        mask_painter.setPen(QColor(0, 0, 0))
        mask_painter.drawText(target, flags, text)
        mask_painter.end()
        for dx in (-TEXT_OUTLINE, 0, TEXT_OUTLINE):
            for dy in (-TEXT_OUTLINE, 0, TEXT_OUTLINE):
                if dx or dy:
                    painter.drawImage(dx, dy, mask)
    painter.setPen(color)
    painter.drawText(target, flags, text)
    painter.end()
    return image, left, top


_offscreen_app: QGuiApplication | None = None


def prepare_web_rasterizer() -> None:
    """Initialize Qt on the main thread before WebView starts dispatching bridge calls."""
    global _offscreen_app
    if QGuiApplication.instance() is None:
        # Paint to QImage without a Qt window. On Windows the native plugin
        # supplies the same font engine as the classic desktop application.
        platform = "windows" if sys.platform == "win32" else "offscreen"
        _offscreen_app = QGuiApplication(["gf-ui-editor", "-platform", platform])
    game_font_family()


@lru_cache(maxsize=2048)
def web_text_mask(
    text: str, color: str, outline: bool, multiline: bool, align: str, width: int, height: int,
) -> tuple[int, int, str]:
    """Return box-local origin and a compact PNG containing only fill and outline."""
    box = QRectF(0, 0, width, height)
    font = game_font(outline)
    flags = text_flags(align, multiline)
    bounds = QFontMetricsF(font).boundingRect(box, flags, text)
    image, left, top = paint_text(text, box, bounds, font, flags, game_color(color), outline)
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise ValueError("Failed to encode game text")
    return left, top, b64encode(buffer.data().data()).decode("ascii")
