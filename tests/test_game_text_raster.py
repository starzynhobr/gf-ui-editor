from base64 import b64decode
from io import BytesIO

from PIL import Image
from PySide6.QtCore import QBuffer, QIODevice, QRectF
from PySide6.QtWidgets import QApplication, QGraphicsRectItem
import pytest

from gf_ui_editor.editor_widgets import GameTextItem
from gf_ui_editor.web_api.canvas import CanvasApi


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize(("text", "width", "height", "props", "button", "align"), [
    ("Itens Deixados", 1, 1, {"FontStyle": "1", "FontColor": "65535"}, False, "0"),
    ("Armadura", 64, 18, {"FontStyle": "1", "TextAlign": "2"}, True, "1"),
    ("Preço de oferta\nMais informações", 45, 11, {"MultiLine": "1", "TextAlign": "2"}, False, "2"),
    ("Preço\nOferta", 1, 1, {"FontStyle": "1", "TextAlign": "1"}, False, "1"),
])
def test_mask_matches_classic_layout(qt_app, text, width, height, props, button, align):
    owner = QGraphicsRectItem(QRectF(0, 0, width, height))
    classic = GameTextItem(owner, props, button)
    classic.set_text(text)
    request = [text, props.get("FontColor", "16777215"), props.get("FontStyle") == "1",
               props.get("MultiLine") == "1", align, width, height]
    [(x, y, png)] = CanvasApi().canvas_text_masks([request])
    mask = Image.open(BytesIO(b64decode(png))).convert("RGBA")

    reference_png = QBuffer()
    reference_png.open(QIODevice.OpenModeFlag.WriteOnly)
    assert classic._image.save(reference_png, "PNG")
    reference = Image.open(BytesIO(bytes(reference_png.data()))).convert("RGBA")
    actual = Image.new("RGBA", reference.size)
    actual.paste(mask, (x - int(classic._image_origin.x()), y - int(classic._image_origin.y())))
    assert actual.tobytes() == reference.tobytes()
    assert set(mask.getchannel("A").tobytes()) == {0, 255}
    assert mask.getbbox()
