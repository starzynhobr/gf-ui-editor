import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image
from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialogButtonBox

from gf_ui_editor.app import EditorWindow
from gf_ui_editor.atlas_dialog import AtlasDialog
from gf_ui_editor.xml_document import UIDocument, UVRect


XML = '''<?xml version="1.0" ?>
<Root_Node>
  <BaseWndProperty WindowID="1" WindowHeight="100" WindowWidth="80">
    <Container_Node Child_Cnt="3">
      <Style CtrlType="262144" />
      <BaseWndProperty WindowID="5010" WindowText="測試" WindowHeight="4" WindowWidth="4">
        <BackGroundMap BGmap="atlas.dds"><NorUV NorUVLeft="0" NorUVTop="0" NorUVWidth="4" NorUVHeight="4" /></BackGroundMap>
        <ButtonNode BtnState="0">
          <FocusUV FocusUVLeft="8" FocusUVTop="0" FocusUVWidth="4" FocusUVHeight="4" />
          <DownUV DownUVLeft="0" DownUVTop="8" DownUVWidth="4" DownUVHeight="4" />
          <DisableUV DisableUVLeft="8" DisableUVTop="8" DisableUVWidth="4" DisableUVHeight="4" />
        </ButtonNode>
      </BaseWndProperty>
      <BaseWndProperty WindowID="5020" WindowHeight="4" WindowWidth="4">
        <BackGroundMap BGmap="atlas.dds"><NorUV NorUVLeft="0" NorUVTop="0" NorUVWidth="4" NorUVHeight="4" /></BackGroundMap>
        <ButtonNode><FocusUV FocusUVWidth="4" FocusUVHeight="4" /></ButtonNode>
      </BaseWndProperty>
      <BaseWndProperty WindowID="6000" WindowHeight="4" WindowWidth="4">
        <PictureNode><FocusUV FocusUVLeft="8" FocusUVTop="0" FocusUVWidth="4" FocusUVHeight="4" /></PictureNode>
      </BaseWndProperty>
    </Container_Node>
  </BaseWndProperty>
</Root_Node>
'''


def write_xml(tmp_path):
    path = tmp_path / "Buttons.xml"
    raw = XML.replace("\n", "\r\n").encode("big5")
    path.write_bytes(raw)
    return path, raw


@pytest.mark.parametrize("state", ["FocusUV", "DownUV", "DisableUV"])
def test_state_edit_preserves_every_other_byte_and_survives_save(tmp_path, state):
    path, raw = write_xml(tmp_path)
    document = UIDocument.load(path)
    assert document.button_states_editable
    assert document.elements[1].button_uvs == {
        "FocusUV": UVRect(8, 0, 4, 4), "DownUV": UVRect(0, 8, 4, 4), "DisableUV": UVRect(8, 8, 4, 4),
    }
    old = document.elements[1].button_uvs[state]
    document.set_button_uv(1, state, UVRect(12, old.top, 4, 4))
    assert document.is_dirty
    assert document.render_text().encode("big5") == raw.replace(
        f'{state}Left="{old.left}"'.encode(), f'{state}Left="12"'.encode(), 1,
    )
    backup = document.save()
    assert backup.read_bytes() == raw
    assert not document.is_dirty
    assert UIDocument.load(path).elements[1].button_uvs[state] == UVRect(12, old.top, 4, 4)
    document.set_button_uv(1, state, UVRect(12, old.top, 4, 4))
    assert not document.is_dirty


def test_missing_attributes_are_inserted_before_the_self_closing_suffix(tmp_path):
    path, raw = write_xml(tmp_path)
    document = UIDocument.load(path)
    document.set_button_uv(2, "FocusUV", UVRect(3, 5, 4, 4))
    expected = raw.replace(
        b'<FocusUV FocusUVWidth="4" FocusUVHeight="4" />',
        b'<FocusUV FocusUVWidth="4" FocusUVHeight="4" FocusUVLeft="3" FocusUVTop="5" />',
    )
    document.save()
    assert path.read_bytes() == expected
    assert UIDocument.load(path).elements[2].button_uvs["FocusUV"] == UVRect(3, 5, 4, 4)
    with pytest.raises(ValueError):
        document.set_button_uv(2, "DownUV", UVRect(1, 2, 3, 4))


def test_nested_buttons_and_comments_do_not_confuse_the_owner(tmp_path):
    path, _ = write_xml(tmp_path)
    xml = '''<Root_Node><BaseWndProperty WindowID="1">
      <ButtonNode><FocusUV FocusUVLeft="1" /></ButtonNode>
      <Container_Node><BaseWndProperty WindowID="2" />
        <BaseWndProperty WindowID="3"><ButtonNode><FocusUV FocusUVLeft="3" /></ButtonNode></BaseWndProperty>
      </Container_Node>
      <!-- <FocusUV FocusUVLeft="9" /> -->
    </BaseWndProperty></Root_Node>'''
    path.write_bytes(xml.encode("big5"))
    document = UIDocument.load(path)
    assert document.button_states_editable
    document.set_button_uv(2, "FocusUV", UVRect(5, 0, 0, 0))
    assert document.render_text() == xml.replace('FocusUVLeft="3"', 'FocusUVLeft="5"')


def create_window(tmp_path, index=1):
    application = QApplication.instance() or QApplication([])
    path, raw = write_xml(tmp_path)
    image = Image.new("RGBA", (24, 24), "black")
    for x, y, color in [(0, 0, "red"), (8, 0, "green"), (0, 8, "blue"), (8, 8, "gray"), (12, 8, "purple")]:
        image.paste(color, (x, y, x + 4, y + 4))
    image.save(tmp_path / "atlas.dds", format="DDS")
    window = EditorWindow(path)
    for _ in range(100):
        if not window._textures_pending:
            break
        QTest.qWait(20)
    assert not window._textures_pending
    window.select_element(index)
    window.open_selected_atlas()
    application.processEvents()
    window.atlas_dialog.edit_button.setChecked(True)
    return application, window, window.atlas_dialog, path, raw


def select_state(dialog, state):
    dialog.state_combo.setCurrentIndex(dialog.state_combo.findData(state))


def test_atlas_stages_independent_states_and_applies_in_one_undo_step(tmp_path):
    application, window, dialog, path, raw = create_window(tmp_path)
    assert not dialog.state_card.isHidden()
    dialog.state_combo.setFocus()
    QTest.keyClick(dialog.state_combo, Qt.Key.Key_Down)
    assert dialog.state_combo.currentData() == "FocusUV"
    assert dialog.current_uv() == UVRect(8, 0, 4, 4)
    assert dialog.state_preview.pixmap().toImage().pixelColor(56, 32).name() == "#008000"
    assert not dialog.resize_element.isEnabled()
    dialog.left_spin.setValue(12)
    select_state(dialog, "DownUV")
    assert dialog.current_uv() == UVRect(0, 8, 4, 4)
    dialog.left_spin.setValue(12)
    select_state(dialog, "DisableUV")
    assert dialog.current_uv() == UVRect(8, 8, 4, 4)
    select_state(dialog, "FocusUV")
    assert dialog.current_uv() == UVRect(12, 0, 4, 4)
    assert window.document.elements[1].button_uvs["FocusUV"] == UVRect(8, 0, 4, 4)
    assert not window.document.is_dirty
    dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Apply).click()
    assert window.document.elements[1].button_uvs["FocusUV"] == UVRect(12, 0, 4, 4)
    assert window.document.elements[1].button_uvs["DownUV"] == UVRect(12, 8, 4, 4)
    assert window.document.elements[1].uv == UVRect(0, 0, 4, 4)
    assert window.items[1].texture_item.pixmap().toImage().pixelColor(0, 0).name() == "#ff0000"
    assert window.undo_stack.count() == 1
    window.undo_stack.undo()
    assert not window.document.is_dirty
    window.undo_stack.redo()
    window.document.save()
    expected = raw.replace(b'FocusUVLeft="8"', b'FocusUVLeft="12"', 1).replace(b'DownUVLeft="0"', b'DownUVLeft="12"', 1)
    assert path.read_bytes() == expected
    dialog.close()
    window.deleteLater()


def test_close_discards_unapplied_changes_and_missing_states_are_disabled(tmp_path):
    application, window, dialog, path, raw = create_window(tmp_path, 2)
    assert not dialog.state_card.isHidden()
    assert not dialog.state_combo.model().item(2).isEnabled()
    assert not dialog.state_combo.model().item(3).isEnabled()
    select_state(dialog, "FocusUV")
    dialog.left_spin.setValue(8)
    QTest.keyClick(dialog, Qt.Key.Key_Escape)
    application.processEvents()
    assert not window.document.is_dirty
    assert window.undo_stack.count() == 0
    assert path.read_bytes() == raw
    window.deleteLater()


def test_resize_uses_normal_slice_and_reload_preserves_active_draft(tmp_path):
    application, window, dialog, path, raw = create_window(tmp_path)
    dialog.resize_element.setChecked(True)
    dialog.width_spin.setValue(6)
    dialog.height_spin.setValue(5)
    select_state(dialog, "DownUV")
    dialog.width_spin.setValue(2)
    dialog.reload_pixmap(dialog._source_pixmap)
    assert dialog.state_combo.currentData() == "DownUV"
    assert dialog.current_uv() == UVRect(0, 8, 2, 4)
    dialog._apply()
    assert window.document.elements[1].geometry[2:] == (6, 5)
    assert window.document.elements[1].uv == UVRect(0, 0, 6, 5)
    assert window.document.elements[1].button_uvs["DownUV"] == UVRect(0, 8, 2, 4)
    assert window.undo_stack.count() == 1
    window.undo_stack.undo()
    assert not window.document.is_dirty
    dialog.close()
    window.deleteLater()


def test_hover_slice_can_be_selected_by_dragging_the_atlas(tmp_path):
    application, window, dialog, path, raw = create_window(tmp_path)
    select_state(dialog, "FocusUV")
    dialog.view.fit_texture()
    application.processEvents()
    start = dialog.view.mapFromScene(QPointF(9.25, 9.25))
    end = dialog.view.mapFromScene(QPointF(12.75, 12.75))
    QTest.mousePress(dialog.view.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(dialog.view.viewport(), end, 20)
    QTest.mouseRelease(dialog.view.viewport(), Qt.MouseButton.LeftButton, pos=end)
    assert dialog.current_uv() == UVRect(9, 9, 4, 4)
    dialog._apply()
    assert window.document.elements[1].button_uvs["FocusUV"] == UVRect(9, 9, 4, 4)
    assert window.document.elements[1].uv == UVRect(0, 0, 4, 4)
    dialog.close()
    window.deleteLater()


@pytest.mark.parametrize("progress_offset", [None, (0, 4)])
def test_non_button_atlas_keeps_existing_controls(progress_offset):
    application = QApplication.instance() or QApplication([])
    from PySide6.QtGui import QPixmap
    dialog = AtlasDialog("atlas.dds", QPixmap(24, 24), UVRect(0, 0, 4, 4), lambda *_: None,
                         progress_offset=progress_offset, offset_editable=True)
    assert dialog.state_card.isHidden()
    assert dialog.offset_card.isHidden() == (progress_offset is None)
    dialog.close()
