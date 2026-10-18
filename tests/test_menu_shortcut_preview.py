import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from gf_ui_editor.app import EditorWindow
from gf_ui_editor.game_layout import menu_shortcut_preview_y


XML = b'''<Root_Node>
  <BaseWndProperty WindowID="1" WindowLeft="-3" WindowTop="-1" WindowHeight="596" WindowWidth="73">
    <Container_Node Child_Cnt="4">
      <Style CtrlType="536870912" ParentNode="4000" />
      <BaseWndProperty WindowID="2013" WindowLeft="5" WindowTop="8" WindowHeight="17" WindowWidth="17"><SlotNode /></BaseWndProperty>
      <Style CtrlType="536870912" />
      <BaseWndProperty WindowID="2001" WindowLeft="27" WindowTop="30" WindowHeight="32" WindowWidth="32"><SlotNode /></BaseWndProperty>
      <Style CtrlType="262144" />
      <BaseWndProperty WindowID="5040" WindowLeft="445" WindowTop="7" WindowHeight="20" WindowWidth="20"><ButtonNode /></BaseWndProperty>
      <Style CtrlType="536870912" ParentNode="4000" />
      <BaseWndProperty WindowID="2036" WindowLeft="425" WindowTop="8" WindowHeight="17" WindowWidth="17"><SlotNode /></BaseWndProperty>
    </Container_Node>
  </BaseWndProperty>
</Root_Node>'''


def create_window(tmp_path, filename="Menu.xml"):
    application = QApplication.instance() or QApplication([])
    path = tmp_path / filename
    path.write_bytes(XML)
    window = EditorWindow(path)
    window.set_game_resolution((2560, 1440))
    return application, window, path


def test_rule_is_restricted_to_menu_and_the_verified_id_range():
    assert menu_shortcut_preview_y("MENU.XML", "2013", -1) == 20
    assert menu_shortcut_preview_y("Menu.xml", "2036", -19) == 2
    assert menu_shortcut_preview_y("Menu.xml", "2013", -1, alternate_layout=True) == 22
    for filename in ["ShortcutBar.xml", "Storage.xml", "CustomMenu.xml", "Target.xml"]:
        assert menu_shortcut_preview_y(filename, "2013", -1) is None
    for window_id in ["2001", "2012", "2037", "4000", "5040", "?"]:
        assert menu_shortcut_preview_y("Menu.xml", window_id, -1) is None


def test_menu_preview_matches_client_position_without_changing_xml(tmp_path):
    application, window, path = create_window(tmp_path)
    slot, lower, button, last = (window.items[i] for i in range(1, 5))
    assert slot.pos() == QPointF(5, 8)
    assert slot.scenePos() == QPointF(5, 20)
    assert last.scenePos() == QPointF(425, 20)
    assert slot.scenePos().y() - button.scenePos().y() == 13
    assert lower.pos() == lower.scenePos() == QPointF(27, 30)
    assert button.pos() == button.scenePos() == QPointF(445, 7)
    window.select_element(1)
    assert not window.properties.anchor_hint.isHidden()
    assert window.properties.y_spin.value() == 8  # Editable XML coordinate.
    screen_y = 20 + window._screen_offset()[1]
    assert f"Y {screen_y}" in window.properties.screen_position_label.text()
    assert not window.document.is_dirty
    assert window.undo_stack.count() == 0
    assert path.read_bytes() == XML
    window.set_game_resolution(None)
    assert slot.scenePos() == slot.pos() == QPointF(5, 8)
    window.set_game_resolution((1280, 720))
    assert slot.scenePos() == QPointF(5, 20)
    window.set_root_mode("xml")
    assert slot.scenePos() == slot.pos()
    window.set_root_mode("auto")
    assert slot.scenePos() == QPointF(5, 20)
    window.deleteLater()


def test_non_slot_control_with_same_id_in_menu_is_not_adjusted(tmp_path):
    application = QApplication.instance() or QApplication([])
    path = tmp_path / "Menu.xml"
    path.write_bytes(XML.replace(b'CtrlType="536870912"', b'CtrlType="262144"').replace(b'<SlotNode />', b'<ButtonNode />'))
    window = EditorWindow(path)
    window.set_game_resolution((2560, 1440))
    assert window.items[1].scenePos() == QPointF(5, 8)
    assert window.items[4].scenePos() == QPointF(425, 8)
    window.deleteLater()


@pytest.mark.parametrize("filename", ["Storage.xml", "ShortcutBar.xml", "CustomMenu.xml"])
def test_same_ids_in_other_files_keep_their_original_positions(tmp_path, filename):
    application, window, path = create_window(tmp_path, filename)
    assert all(item.preview_offset.isNull() for item in window.items.values())
    assert window.items[1].pos() == window.items[1].scenePos() == QPointF(5, 8)
    assert path.read_bytes() == XML
    window.deleteLater()


def test_drag_and_undo_keep_preview_offset_out_of_saved_coordinates(tmp_path):
    application, window, path = create_window(tmp_path)
    window.resize(1500, 900)
    window.show()
    window.view.resetTransform()
    window.select_element(1)
    item = window.items[1]
    window.view.centerOn(item.scenePos())
    application.processEvents()
    start = window.view.mapFromScene(item.mapToScene(QPointF(3, 3)))
    end = start + QPoint(20, 10)
    QTest.mousePress(window.view.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(window.view.viewport(), end, 20)
    QTest.mouseRelease(window.view.viewport(), Qt.MouseButton.LeftButton, pos=end)
    application.processEvents()
    assert window.document.elements[1].geometry == (25, 18, 17, 17)
    assert item.scenePos() == QPointF(25, 20)  # The client overrides Y again.
    window.undo_stack.undo()
    assert window.document.elements[1].geometry == (5, 8, 17, 17)
    assert item.scenePos() == QPointF(5, 20)
    assert not window.document.is_dirty
    assert path.read_bytes() == XML
    window.deleteLater()
