import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from gf_ui_editor.app import EditorWindow
from gf_ui_editor.xml_document import UIDocument


def group_window(tmp_path: Path):
    application = QApplication.instance() or QApplication([])
    path = tmp_path / "Grupo.xml"
    path.write_text('''<Root_Node UI_File_Name="Grupo.xml">
      <BaseWndProperty WindowID="1" WindowHeight="500" WindowWidth="500">
        <Container_Node Child_Cnt="3">
          <Style CtrlType="268435456" />
          <BaseWndProperty WindowID="2" WindowLeft="10" WindowTop="20" WindowHeight="40" WindowWidth="30" />
          <Style CtrlType="268435456" ParentNode="2" />
          <BaseWndProperty WindowID="3" WindowLeft="100" WindowTop="80" WindowHeight="50" WindowWidth="30" />
          <BaseWndProperty WindowID="4" WindowLeft="60" WindowTop="50" WindowHeight="0" WindowWidth="0" />
        </Container_Node>
      </BaseWndProperty>
    </Root_Node>''', encoding="ascii")
    window = EditorWindow(path)
    window.select_element(1)
    window.items[2].setSelected(True)
    return application, window


def geometries(window):
    return [element.geometry for element in window.document.elements]


def test_group_resize_scales_positions_and_sizes_with_atomic_undo_and_save(tmp_path):
    application, window = group_window(tmp_path)
    before = geometries(window)
    item = window.items[1]  # A parent and its selected child scale exactly once.
    item.begin_resize(QPointF())
    item.resize_to(QPointF(140, 90))
    assert window.items[2].pos() == QPointF(190, 140)
    assert window.items[2].rect().width() == 100
    assert geometries(window) == before  # Preview only until release.
    item.end_resize()
    application.processEvents()
    after = geometries(window)
    assert after == [before[0], (10, 20, 80, 60), (190, 140, 100, 60), before[3]]
    assert window.undo_stack.count() == 1
    window.undo_stack.undo()
    assert geometries(window) == before
    assert not window.document.is_dirty
    window.undo_stack.redo()
    assert geometries(window) == after
    window.document.save()
    assert [e.geometry for e in UIDocument.load(window.document.path).elements] == after
    window.deleteLater()


def test_group_resize_shift_can_toggle_without_accumulating_and_repeat(tmp_path):
    application, window = group_window(tmp_path)
    item = window.items[2]
    item.begin_resize(QPointF())
    item.resize_to(QPointF(70, 0), proportional=True)
    assert window.items[1].rect().size().toSize().width() == 60
    assert window.items[1].rect().height() == 45
    item.resize_to(QPointF(70, 0), proportional=False)
    assert window.items[1].rect().height() == 30
    item.end_resize()
    assert geometries(window)[1:3] == [(10, 20, 60, 30), (145, 80, 75, 30)]
    item.begin_resize(QPointF())
    item.resize_to(QPointF(210, 90))
    item.end_resize()
    assert geometries(window)[1:3] == [(10, 20, 120, 60), (280, 140, 150, 60)]
    window.deleteLater()


def test_group_resize_preserves_zero_dimensions_and_ignores_locked_items(tmp_path):
    application, window = group_window(tmp_path)
    window.items[3].setSelected(True)
    window.locked_indexes.add(2)
    window.items[2].set_locked(True)
    before = geometries(window)
    item = window.items[1]
    item.begin_resize(QPointF())
    item.resize_to(QPointF(51, 31))  # Bounds include the 1px display of zero-size text.
    item.end_resize()
    assert geometries(window)[1:] == [(10, 20, 80, 60), before[2], (110, 80, 0, 0)]
    window.undo_stack.undo()
    assert geometries(window) == before
    item.begin_resize(QPointF())
    item.resize_to(QPointF(-10000, -10000), proportional=True)
    item.end_resize()
    assert geometries(window)[1][2:] == (1, 1)
    assert geometries(window)[3][2:] == (0, 0)
    window.deleteLater()


def test_group_resize_no_motion_creates_no_undo_step(tmp_path):
    application, window = group_window(tmp_path)
    before = geometries(window)
    item = window.items[1]
    item.begin_resize(QPointF())
    item.resize_to(QPointF())
    item.end_resize()
    assert geometries(window) == before
    assert window.undo_stack.count() == 0
    window.deleteLater()


def test_mouse_drag_handle_keeps_selection_and_resizes_group(tmp_path):
    application, window = group_window(tmp_path)
    window.show()
    window.view.resetTransform()
    application.processEvents()
    start = window.view.mapFromScene(window.items[2].resize_handle.scenePos())
    end = start + QPoint(140, 90)
    QTest.mousePress(window.view.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(window.view.viewport(), end, 20)
    QTest.mouseRelease(window.view.viewport(), Qt.MouseButton.LeftButton, pos=end)
    application.processEvents()
    assert geometries(window)[1:3] == [(10, 20, 80, 60), (190, 140, 100, 60)]
    assert {i for i, item in window.items.items() if item.isSelected()} == {1, 2}
    assert window.undo_stack.count() == 1
    window.deleteLater()
