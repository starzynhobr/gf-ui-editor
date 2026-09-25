from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QGraphicsScene

from gf_ui_editor.app import EditorWindow
from gf_ui_editor.atlas_dialog import AtlasDialog, AtlasView
from gf_ui_editor.editor_widgets import EditorView
from gf_ui_editor.xml_document import UVRect


SAMPLE = """<?xml version="1.0" ?>
<Root_Node UI_File_Name="Teste.xml">
  <BaseWndProperty WindowID="1" WindowHeight="100" WindowWidth="80" />
</Root_Node>
"""


def create_window(tmp_path: Path) -> tuple[QApplication, EditorWindow]:
    application = QApplication.instance() or QApplication([])
    path = tmp_path / "Teste.xml"
    path.write_bytes(SAMPLE.encode("big5"))
    window = EditorWindow(path)
    window.select_element(0)
    return application, window


def test_numeric_property_updates_canvas_immediately(tmp_path: Path) -> None:
    application, window = create_window(tmp_path)

    window.properties.x_spin.setValue(17)
    application.processEvents()

    assert window.document is not None
    assert window.document.elements[0].x == 17
    assert round(window.items[0].pos().x()) == 17
    assert window.undo_stack.count() == 1
    window.undo_stack.undo()
    assert not window.document.is_dirty
    window.deleteLater()


def test_resize_handle_updates_size_and_supports_undo(tmp_path: Path) -> None:
    application, window = create_window(tmp_path)
    item = window.items[0]

    item.begin_resize(QPointF(0, 0))
    item.resize_to(QPointF(24, 13))
    item.end_resize()
    application.processEvents()

    assert window.document is not None
    assert window.document.elements[0].geometry == (0, 0, 124, 93)
    assert window.properties.width_spin.value() == 124
    assert window.properties.height_spin.value() == 93
    window.undo_stack.undo()
    assert window.document.elements[0].geometry == (0, 0, 100, 80)
    assert not window.document.is_dirty
    window.deleteLater()


def test_shift_resize_preserves_original_aspect_ratio(tmp_path: Path) -> None:
    application, window = create_window(tmp_path)
    item = window.items[0]

    item.begin_resize(QPointF(0, 0))
    item.resize_to(QPointF(50, 5), proportional=True)
    item.end_resize()
    application.processEvents()

    assert window.document is not None
    assert window.document.elements[0].geometry == (0, 0, 150, 120)
    assert window.document.elements[0].width / window.document.elements[0].height == 1.25
    window.deleteLater()


def test_middle_mouse_drag_pans_canvas() -> None:
    application = QApplication.instance() or QApplication([])
    view = EditorView(lambda _dx, _dy: None)
    view.setScene(QGraphicsScene(0, 0, 2000, 2000))
    view.resize(320, 240)
    view.show()
    view.centerOn(1000, 1000)
    coordinates: list[tuple[int, int]] = []
    view.cursor_scene_moved.connect(lambda x, y: coordinates.append((x, y)))
    application.processEvents()
    before = (
        view.horizontalScrollBar().value(),
        view.verticalScrollBar().value(),
    )

    QTest.mousePress(
        view.viewport(),
        Qt.MouseButton.MiddleButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(150, 110),
    )
    QTest.mouseMove(view.viewport(), QPoint(190, 140), 20)
    QTest.mouseRelease(
        view.viewport(),
        Qt.MouseButton.MiddleButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(190, 140),
    )
    application.processEvents()

    after = (
        view.horizontalScrollBar().value(),
        view.verticalScrollBar().value(),
    )
    assert after == (before[0] - 40, before[1] - 30)
    assert coordinates
    view.close()


def test_drag_snaps_to_integer_pixel_grid_before_release(tmp_path: Path) -> None:
    application, window = create_window(tmp_path)
    window.show()
    window.view.resetTransform()
    window.view.scale(1.37, 1.37)
    application.processEvents()
    item = window.items[0]
    start = window.view.mapFromScene(item.sceneBoundingRect().center())

    QTest.mousePress(window.view.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(window.view.viewport(), start + QPoint(1, 1), 20)
    application.processEvents()

    assert item.pos() == QPointF(1, 1)
    assert window.document is not None
    assert window.document.elements[0].geometry == (0, 0, 100, 80)

    QTest.mouseRelease(
        window.view.viewport(), Qt.MouseButton.LeftButton, pos=start + QPoint(1, 1)
    )
    application.processEvents()
    assert window.document.elements[0].geometry == (1, 1, 100, 80)
    window.deleteLater()


def test_tree_selected_item_has_drag_priority_over_overlapping_panel(
    tmp_path: Path,
) -> None:
    application = QApplication.instance() or QApplication([])
    xml = """<?xml version="1.0" ?>
<Root_Node UI_File_Name="Sobreposto.xml">
  <BaseWndProperty WindowID="1" WindowHeight="200" WindowWidth="100">
    <Container_Node Child_Cnt="2">
      <Style CtrlType="33554432" />
      <BaseWndProperty WindowID="2" WindowLeft="40" WindowTop="30" WindowHeight="0" WindowWidth="0"><TextNode /></BaseWndProperty>
      <Style CtrlType="268435456" />
      <BaseWndProperty WindowID="3" WindowHeight="200" WindowWidth="100" />
    </Container_Node>
  </BaseWndProperty>
</Root_Node>
"""
    path = tmp_path / "Sobreposto.xml"
    path.write_bytes(xml.encode("big5"))
    window = EditorWindow(path)
    window.show()
    window.tree.setCurrentItem(window.tree_items[1])
    application.processEvents()
    text_item = window.items[1]
    covering_item = window.items[2]
    assert text_item.zValue() > covering_item.zValue()
    start = window.view.mapFromScene(text_item.label_item.sceneBoundingRect().center())

    QTest.mousePress(window.view.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(window.view.viewport(), start + QPoint(30, 15), 20)
    QTest.mouseRelease(
        window.view.viewport(),
        Qt.MouseButton.LeftButton,
        pos=start + QPoint(30, 15),
    )
    application.processEvents()

    assert window.selected_index == 1
    assert window.document is not None
    assert window.document.elements[1].x > 40
    assert window.document.elements[2].x == 0
    window.undo_stack.undo()
    window.deleteLater()


def test_ctrl_selection_moves_multiple_items_as_one_undo_step(tmp_path: Path) -> None:
    application = QApplication.instance() or QApplication([])
    xml = """<?xml version="1.0" ?>
<Root_Node UI_File_Name="Grupo.xml">
  <BaseWndProperty WindowID="1" WindowLeft="10" WindowTop="20" WindowHeight="40" WindowWidth="30" />
  <BaseWndProperty WindowID="2" WindowLeft="100" WindowTop="80" WindowHeight="40" WindowWidth="30" />
</Root_Node>
"""
    path = tmp_path / "Grupo.xml"
    path.write_bytes(xml.encode("big5"))
    window = EditorWindow(path)
    window.show()
    application.processEvents()

    first = window.view.mapFromScene(window.items[0].sceneBoundingRect().center())
    second = window.view.mapFromScene(window.items[1].sceneBoundingRect().center())
    QTest.mouseClick(window.view.viewport(), Qt.MouseButton.LeftButton, pos=first)
    QTest.mouseClick(
        window.view.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.ControlModifier,
        second,
    )
    application.processEvents()

    assert {index for index, item in window.items.items() if item.isSelected()} == {0, 1}
    assert len(window.tree.selectedItems()) == 2

    start = second
    end = second + QPoint(25, 15)
    scene_delta = window.view.mapToScene(end) - window.view.mapToScene(start)
    QTest.mousePress(window.view.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(window.view.viewport(), end, 20)
    QTest.mouseRelease(window.view.viewport(), Qt.MouseButton.LeftButton, pos=end)
    application.processEvents()

    dx, dy = round(scene_delta.x()), round(scene_delta.y())
    assert window.document is not None
    assert window.document.elements[0].geometry == (10 + dx, 20 + dy, 40, 30)
    assert window.document.elements[1].geometry == (100 + dx, 80 + dy, 40, 30)
    assert window.undo_stack.count() == 1

    window.undo_stack.undo()
    assert window.document.elements[0].geometry == (10, 20, 40, 30)
    assert window.document.elements[1].geometry == (100, 80, 40, 30)
    window.deleteLater()


def test_selected_resize_handle_has_priority_over_overlapping_panel(
    tmp_path: Path,
) -> None:
    application = QApplication.instance() or QApplication([])
    xml = """<?xml version="1.0" ?>
<Root_Node UI_File_Name="Sobreposto.xml">
  <BaseWndProperty WindowID="1" WindowHeight="100" WindowWidth="100">
    <Container_Node Child_Cnt="1">
      <BaseWndProperty WindowID="2" WindowHeight="120" WindowWidth="120" />
    </Container_Node>
  </BaseWndProperty>
</Root_Node>
"""
    path = tmp_path / "Sobreposto.xml"
    path.write_bytes(xml.encode("big5"))
    window = EditorWindow(path)
    window.show()
    window.select_element(0)
    application.processEvents()

    # The click is outside the visible 10 px square, but inside its larger hit area.
    start = window.view.mapFromScene(window.items[0].resize_handle.scenePos()) + QPoint(7, 7)
    end = start + QPoint(20, 15)
    scene_delta = window.view.mapToScene(end) - window.view.mapToScene(start)
    QTest.mousePress(window.view.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(window.view.viewport(), end, 20)
    QTest.mouseRelease(
        window.view.viewport(),
        Qt.MouseButton.LeftButton,
        pos=end,
    )
    application.processEvents()

    assert window.selected_index == 0
    assert window.document is not None
    assert window.document.elements[0].geometry == (
        0,
        0,
        100 + round(scene_delta.x()),
        100 + round(scene_delta.y()),
    )
    assert window.document.elements[1].geometry == (0, 0, 120, 120)
    window.deleteLater()


def test_uv_edit_updates_preview_and_undo(tmp_path: Path) -> None:
    application, window = create_window(tmp_path)
    assert window.document is not None
    element = window.document.elements[0]
    element.texture_name = "main.dds"
    element.uv = UVRect(1, 2, 10, 10)
    element.original_uv = element.uv

    window.edit_uv(0, UVRect(8, 9, 20, 12), resize_element=True)
    application.processEvents()

    assert element.uv == UVRect(8, 9, 20, 12)
    assert element.geometry == (0, 0, 20, 12)
    window.undo_stack.undo()
    assert element.uv == UVRect(1, 2, 10, 10)
    assert element.geometry == (0, 0, 100, 80)
    window.deleteLater()


def test_external_dds_save_refreshes_preview(tmp_path: Path) -> None:
    application = QApplication.instance() or QApplication([])
    texture_path = tmp_path / "atlas.dds"
    Image.new("RGBA", (8, 8), (220, 20, 20, 255)).save(texture_path)
    xml = """<?xml version="1.0" ?>
<Root_Node UI_File_Name="Atlas.xml">
  <BaseWndProperty WindowID="1" WindowHeight="8" WindowWidth="8">
    <BackGroundMap BGmap="atlas.dds"><NorUV NorUVLeft="0" NorUVTop="0" NorUVWidth="8" NorUVHeight="8" /></BackGroundMap>
  </BaseWndProperty>
</Root_Node>
"""
    xml_path = tmp_path / "Atlas.xml"
    xml_path.write_bytes(xml.encode("big5"))
    window = EditorWindow(xml_path)
    pixmap_item = window.items[0].texture_item
    assert pixmap_item is not None
    assert pixmap_item.pixmap().toImage().pixelColor(2, 2).red() > 200
    assert str(texture_path) in window.texture_watcher.files()

    Image.new("RGBA", (8, 8), (15, 60, 230, 255)).save(texture_path)
    for _ in range(20):
        QTest.qWait(100)
        application.processEvents()
        pixmap_item = window.items[0].texture_item
        assert pixmap_item is not None
        if pixmap_item.pixmap().toImage().pixelColor(2, 2).blue() > 200:
            break

    assert pixmap_item.pixmap().toImage().pixelColor(2, 2).blue() > 200
    window.deleteLater()


def test_opening_another_xml_reuses_unchanged_decoded_texture(
    tmp_path: Path, monkeypatch
) -> None:
    application = QApplication.instance() or QApplication([])
    texture_path = tmp_path / "atlas.dds"
    Image.new("RGBA", (8, 8), (220, 20, 20, 255)).save(texture_path)
    xml = """<?xml version="1.0" ?>
<Root_Node UI_File_Name="Atlas.xml">
  <BaseWndProperty WindowID="1" WindowHeight="8" WindowWidth="8">
    <BackGroundMap BGmap="atlas.dds"><NorUV NorUVLeft="0" NorUVTop="0" NorUVWidth="8" NorUVHeight="8" /></BackGroundMap>
  </BaseWndProperty>
</Root_Node>
"""
    first_path = tmp_path / "First.xml"
    second_path = tmp_path / "Second.xml"
    first_path.write_bytes(xml.encode("big5"))
    second_path.write_bytes(xml.encode("big5"))

    original_open = Image.open
    opened: list[Path] = []

    def tracked_open(path, *args, **kwargs):
        opened.append(Path(path))
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Image, "open", tracked_open)
    window = EditorWindow(first_path)
    window.open_document(second_path)
    application.processEvents()

    assert opened == [texture_path]

    Image.new("RGBA", (8, 8), (15, 60, 230, 255)).save(texture_path)
    window.open_document(first_path)
    application.processEvents()

    assert opened == [texture_path, texture_path]
    window.deleteLater()


def test_progress_preview_applies_runtime_offset_layer(tmp_path: Path) -> None:
    application = QApplication.instance() or QApplication([])
    texture_path = tmp_path / "atlas.dds"
    atlas = Image.new("RGBA", (4, 8), (0, 0, 0, 0))
    atlas.paste((230, 20, 30, 255), (0, 4, 4, 8))
    atlas.save(texture_path)
    xml = """<?xml version="1.0" ?>
<Root_Node UI_File_Name="Progress.xml">
  <Style CtrlType="67108864" />
  <BaseWndProperty WindowID="3000" WindowHeight="4" WindowWidth="4">
    <BackGroundMap BGmap="atlas.dds"><NorUV NorUVLeft="0" NorUVTop="0" NorUVWidth="4" NorUVHeight="4" /></BackGroundMap>
    <ProgressNode><OffSetUV UVCnt="1"><SOffset-0 x="0" y="4" /></OffSetUV></ProgressNode>
  </BaseWndProperty>
</Root_Node>
"""
    xml_path = tmp_path / "Progress.xml"
    xml_path.write_bytes(xml.encode("big5"))

    window = EditorWindow(xml_path)
    application.processEvents()
    pixmap_item = window.items[0].texture_item

    assert pixmap_item is not None
    color = pixmap_item.pixmap().toImage().pixelColor(2, 2)
    assert color.red() > 200
    assert color.green() < 50
    window.deleteLater()


def test_atlas_can_focus_selection_with_thin_cosmetic_outline() -> None:
    application = QApplication.instance() or QApplication([])
    pixmap = QPixmap(1015, 1014)
    dialog = AtlasDialog(
        "main.dds",
        pixmap,
        UVRect(1, 863, 174, 7),
        lambda _uv, _resize: None,
    )
    dialog.show()
    application.processEvents()
    dialog.view.fit_texture()
    full_scale = dialog.view.transform().m11()

    pen = dialog.view._selection_item.pen()
    assert pen.isCosmetic()
    assert pen.widthF() == 1.0

    dialog.view.focus_selection()
    focused_scale = dialog.view.transform().m11()
    assert focused_scale > full_scale

    dialog.reload_pixmap(QPixmap(1015, 1014))
    assert dialog.view.transform().m11() == focused_scale
    dialog.close()


def test_atlas_selection_can_be_resized_from_each_corner() -> None:
    application = QApplication.instance() or QApplication([])
    view = AtlasView()
    view.resize(320, 240)
    view.set_pixmap(QPixmap(100, 80))
    view.resetTransform()
    view.show()
    application.processEvents()

    cases = {
        "top_left": (QPointF(5, 4), UVRect(5, 4, 25, 26)),
        "top_right": (QPointF(36, 4), UVRect(10, 4, 26, 26)),
        "bottom_left": (QPointF(5, 37), UVRect(5, 10, 25, 27)),
        "bottom_right": (QPointF(36, 37), UVRect(10, 10, 26, 27)),
    }
    emitted: list[UVRect] = []
    view.selection_changed.connect(emitted.append)

    for corner, (destination, expected) in cases.items():
        view.set_selection(UVRect(10, 10, 20, 20))
        start = view.mapFromScene(view._resize_handles[corner].scenePos())
        end = view.mapFromScene(destination)
        QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(view.viewport(), end, 20)
        QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=end)
        application.processEvents()
        assert emitted[-1] == expected

    view.close()


def test_atlas_marks_progress_runtime_region() -> None:
    application = QApplication.instance() or QApplication([])
    dialog = AtlasDialog(
        "main.dds",
        QPixmap(100, 100),
        UVRect(10, 20, 30, 8),
        lambda _uv, _resize: None,
        progress_offset=(2, 12),
    )

    assert dialog.view._progress_item.isVisible()
    assert dialog.view._progress_item.rect() == QRectF(12, 32, 30, 8)
    assert "100%" in dialog.progress_explanation.text()

    dialog.close()


def test_atlas_dialog_has_native_maximize_button() -> None:
    application = QApplication.instance() or QApplication([])
    dialog = AtlasDialog(
        "main.dds",
        QPixmap(32, 32),
        UVRect(0, 0, 16, 16),
        lambda _uv, _resize: None,
    )

    assert dialog.windowFlags() & Qt.WindowType.WindowMaximizeButtonHint

    dialog.close()
