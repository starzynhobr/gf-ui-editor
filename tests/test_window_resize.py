import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from gf_ui_editor.app import EditorWindow
from gf_ui_editor.xml_document import UIDocument


@pytest.mark.parametrize(
    ("filename", "delta", "size"),
    [
        ("Menu.xml", QPoint(40, 20), (660, 98)),
        ("Storage.xml", QPoint(40, 20), (660, 78)),
        ("Radar.xml", QPoint(40, 20), (700, 138)),
    ],
)
def test_real_window_handle_resizes_xml_and_keeps_content_fixed(tmp_path, filename, delta, size):
    application = QApplication.instance() or QApplication([])
    path = tmp_path / filename
    path.write_bytes(b'''<Root_Node>
      <BaseWndProperty WindowID="1" WindowLeft="-63" WindowTop="-12" WindowHeight="740" WindowWidth="118">
        <Container_Node Child_Cnt="1">
          <BaseWndProperty WindowID="2" WindowLeft="0" WindowTop="0" WindowHeight="592" WindowWidth="72" />
        </Container_Node>
      </BaseWndProperty>
    </Root_Node>''')
    window = EditorWindow(path)
    window.resize(1500, 900)
    window.set_game_resolution((2560, 1440))
    window.show()
    window.view.resetTransform()
    window.select_element(0)
    item = window.items[0]
    window.view.centerOn(item.window_bounds_item.sceneBoundingRect().center())
    application.processEvents()
    assert item.frame_mode
    assert item.window_bounds_item.isVisible()
    assert item.window_bounds_item.rect().size() == QRectF(0, 0, 740, 118).size()
    assert item.resize_handle.isVisible()
    assert item.window_size_item.text() == "740 × 118"
    original_root = window.document.elements[0].geometry
    child_geometry = window.document.elements[1].geometry
    child_screen = window.items[1].pos() + QPointF(*window._screen_offset())
    start = window.view.mapFromScene(item.resize_handle.scenePos())
    end = start + delta
    QTest.mousePress(window.view.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(window.view.viewport(), end, 20)
    application.processEvents()
    assert item.window_size_item.text() == f"{size[0]} × {size[1]}"
    assert window.document.elements[0].geometry == original_root
    QTest.mouseRelease(window.view.viewport(), Qt.MouseButton.LeftButton, pos=end)
    application.processEvents()
    assert window.document.elements[0].geometry[2:] == size
    assert (window.properties.width_spin.value(), window.properties.height_spin.value()) == size
    assert item.window_bounds_item.mapRectToScene(item.window_bounds_item.rect()) == QRectF(
        *window.document.elements[0].geometry
    )
    assert window.document.elements[1].geometry == child_geometry
    assert window.items[1].pos() + QPointF(*window._screen_offset()) == child_screen
    assert window.undo_stack.count() == 1
    window.undo_stack.undo()
    assert window.document.elements[0].geometry == original_root
    assert not window.document.is_dirty
    window.undo_stack.redo()
    assert window.document.elements[0].geometry[2:] == size
    window.document.save()
    assert UIDocument.load(path).elements[0].geometry == window.document.elements[0].geometry
    window.select_element(1)
    assert not item.window_bounds_item.isVisible()
    window.deleteLater()


def test_real_window_resize_supports_shift_and_locking(tmp_path: Path):
    application = QApplication.instance() or QApplication([])
    path = tmp_path / "Menu.xml"
    path.write_bytes(b'''<Root_Node>
      <BaseWndProperty WindowID="1" WindowHeight="200" WindowWidth="100" />
      <BaseWndProperty WindowID="2" WindowHeight="80" WindowWidth="40" />
    </Root_Node>''')
    window = EditorWindow(path)
    window.set_game_resolution((800, 600))
    window.select_element(0)
    item = window.items[0]
    item.set_locked(True)
    assert not item.resize_handle.isVisible()
    assert not any(handle.isVisible() for handle in item.window_resize_handles.values())
    item.set_locked(False)
    assert item.resize_handle.isVisible()
    assert all(handle.isVisible() for handle in item.window_resize_handles.values())
    before = window._screen_offset()
    item.begin_resize(QPointF())
    item.resize_to(QPointF(-50, -5), proportional=True)
    item.end_resize()
    assert window.document.elements[0].geometry[2:] == (300, 150)
    assert window._screen_offset() == before
    window.deleteLater()


def window_for_edges(tmp_path: Path):
    application = QApplication.instance() or QApplication([])
    path = tmp_path / "Menu.xml"
    path.write_bytes(b'''<Root_Node>
      <BaseWndProperty WindowID="1" WindowHeight="200" WindowWidth="100" />
      <BaseWndProperty WindowID="2" WindowLeft="40" WindowTop="20" WindowHeight="60" WindowWidth="20" />
    </Root_Node>''')
    window = EditorWindow(path)
    window.resize(1400, 850)
    window.set_game_resolution((800, 600))
    window.show()
    window.select_element(0)
    window.view.resetTransform()
    window.view.centerOn(window.items[0].window_bounds_item.sceneBoundingRect().center())
    application.processEvents()
    return application, window


@pytest.mark.parametrize(
    ("handle_key", "size"),
    [
        ("top_left", (180, 92)), ("top", (200, 92)),
        ("top_right", (220, 92)), ("right", (220, 100)),
        ("bottom_right", (220, 108)), ("bottom", (200, 108)),
        ("bottom_left", (180, 108)), ("left", (180, 100)),
    ],
)
def test_all_window_handles_resize_using_their_own_axes(tmp_path, handle_key, size):
    application, window = window_for_edges(tmp_path)
    item = window.items[0]
    assert len(item.window_resize_handles) == 8
    handle = item.window_resize_handles[handle_key]
    start = window.view.mapFromScene(handle.scenePos())
    before_offset = window._screen_offset()
    child_geometry = window.document.elements[1].geometry
    end = start + QPoint(10, 8)
    QTest.mousePress(window.view.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(window.view.viewport(), end, 20)
    QTest.mouseRelease(window.view.viewport(), Qt.MouseButton.LeftButton, pos=end)
    application.processEvents()
    assert window.document.elements[0].geometry[2:] == size
    assert window.document.elements[1].geometry == child_geometry
    assert window._screen_offset() == before_offset
    assert window.undo_stack.count() == 1
    window.undo_stack.undo()
    assert window.document.elements[0].geometry == (0, 0, 200, 100)
    assert not window.document.is_dirty
    window.undo_stack.redo()
    assert window.document.elements[0].geometry[2:] == size
    window.deleteLater()


def test_dragging_the_real_window_area_moves_content_without_resizing(tmp_path):
    application, window = window_for_edges(tmp_path)
    item = window.items[0]
    child = window.items[1]
    # This point is in the real window, well outside its content frame.
    start = window.view.mapFromScene(QPointF(150, 70))
    end = start + QPoint(15, -5)
    before_screen = child.pos() + QPointF(*window._screen_offset())
    before_geometry = window.document.elements[1].geometry
    QTest.mousePress(window.view.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(window.view.viewport(), end, 20)
    application.processEvents()
    assert child.pos() + QPointF(*window._screen_offset()) == before_screen + QPointF(15, -5)
    QTest.mouseRelease(window.view.viewport(), Qt.MouseButton.LeftButton, pos=end)
    application.processEvents()
    assert window.document.elements[0].geometry == (-15, 5, 200, 100)
    assert window.document.elements[1].geometry == before_geometry
    assert child.pos() + QPointF(*window._screen_offset()) == before_screen + QPointF(15, -5)
    assert window.undo_stack.count() == 1
    window.undo_stack.undo()
    assert child.pos() + QPointF(*window._screen_offset()) == before_screen
    window.deleteLater()
