from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QGraphicsScene, QToolBar

from gf_ui_editor.app import EditorWindow
from gf_ui_editor.atlas_dialog import AtlasDialog, AtlasView
from gf_ui_editor.editor_widgets import EditorView
from gf_ui_editor.project import Project
from gf_ui_editor.xml_document import UVRect


SAMPLE = """<?xml version="1.0" ?>
<Root_Node UI_File_Name="Teste.xml">
  <BaseWndProperty WindowID="1" WindowHeight="100" WindowWidth="80" />
</Root_Node>
"""


def test_clickable_cursor_tracks_action_availability(tmp_path: Path) -> None:
    application = QApplication.instance() or QApplication([])
    window = EditorWindow()
    toolbar = window.findChild(QToolBar)
    open_button = toolbar.widgetForAction(window.open_project_action)
    fit_button = toolbar.widgetForAction(window.reload_textures_action)
    assert open_button.cursor().shape() == Qt.CursorShape.PointingHandCursor
    assert not window.reload_textures_action.isEnabled()
    assert fit_button.cursor().shape() == Qt.CursorShape.ArrowCursor

    xml_path = tmp_path / "Teste.xml"
    xml_path.write_bytes(SAMPLE.encode("big5"))
    window.open_document(xml_path)
    application.processEvents()
    assert window.reload_textures_action.isEnabled()
    assert fit_button.cursor().shape() == Qt.CursorShape.PointingHandCursor
    window.deleteLater()


def create_window(tmp_path: Path) -> tuple[QApplication, EditorWindow]:
    application = QApplication.instance() or QApplication([])
    path = tmp_path / "Teste.xml"
    path.write_bytes(SAMPLE.encode("big5"))
    window = EditorWindow(path)
    window.select_element(0)
    return application, window


def wait_for_textures(window: EditorWindow) -> None:
    for _ in range(100):
        if not window._textures_pending:
            return
        QTest.qWait(20)
    raise AssertionError("As texturas não terminaram de carregar")


def test_refresh_button_discovers_added_and_removed_xml_without_open_document(tmp_path: Path) -> None:
    application = QApplication.instance() or QApplication([])
    source = tmp_path / "source"
    source.mkdir()
    (source / "Teste.xml").write_bytes(SAMPLE.encode("big5"))
    project = Project.create("Refresh", source, None, projects_root=tmp_path / "projects")
    window = EditorWindow()
    window.open_project(project.root)
    assert window.document is None
    assert window.reload_textures_action.isEnabled()
    assert window.project.files() == [Path("Teste.xml")]
    (project.ui_dir / "Teste.xml").unlink()
    (project.ui_dir / "Novo.xml").write_bytes(SAMPLE.encode("big5"))
    window.file_filter_edit.setText("Novo")
    toolbar = window.findChild(QToolBar)
    toolbar.widgetForAction(window.reload_textures_action).click()
    application.processEvents()
    assert window.project.files() == [Path("Novo.xml")]
    listed = [
        window.files_tree.topLevelItem(i).child(j)
        for i in range(window.files_tree.topLevelItemCount())
        for j in range(window.files_tree.topLevelItem(i).childCount())
    ]
    assert listed and all(item.text(0) == "Novo.xml" for item in listed)
    assert all(not item.isHidden() for item in listed)
    assert window.file_filter_edit.text() == "Novo"
    assert window.document is None
    window.deleteLater()


def test_refresh_updates_textures_and_file_list_preserving_unsaved_xml(tmp_path: Path) -> None:
    application = QApplication.instance() or QApplication([])
    source = tmp_path / "source"
    source.mkdir()
    xml = SAMPLE.replace(
        'WindowWidth="80" />',
        'WindowWidth="80"><BackGroundMap BGmap="main.dds">'
        '<NorUV NorUVWidth="4" NorUVHeight="4" /></BackGroundMap></BaseWndProperty>',
    )
    (source / "Teste.xml").write_bytes(xml.encode("big5"))
    Image.new("RGBA", (4, 4), "red").save(source / "main.dds", format="DDS")
    project = Project.create("Refresh", source, None, projects_root=tmp_path / "projects")
    window = EditorWindow()
    window.open_project(project.root)
    window.watch_textures_action.setChecked(False)
    window.open_document(project.ui_dir / "Teste.xml")
    wait_for_textures(window)
    window.select_element(0)
    window.properties.x_spin.setValue(17)
    document = window.document
    undo_count = window.undo_stack.count()
    assert window.items[0].texture_item.pixmap().toImage().pixelColor(0, 0).name() == "#ff0000"
    Image.new("RGBA", (4, 4), "blue").save(project.ui_dir / "main.dds", format="DDS")
    (project.ui_dir / "Novo.xml").write_bytes(SAMPLE.encode("big5"))
    window.reload_textures_action.trigger()
    assert Path("Novo.xml") in window.project.files()
    assert window.items[0].texture_item.pixmap().toImage().pixelColor(0, 0).name() == "#0000ff"
    assert window.document is document
    assert document.elements[0].x == 17 and document.is_dirty
    assert window.undo_stack.count() == undo_count
    assert (project.ui_dir / "Teste.xml").read_bytes() == xml.encode("big5")
    window.undo_stack.undo()
    assert document.elements[0].x == 0 and not document.is_dirty
    window.deleteLater()


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


def test_external_dds_save_refreshes_preview(tmp_path: Path, monkeypatch) -> None:
    from PySide6.QtGui import QDesktopServices

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
    assert window.items[0].texture_item is None
    wait_for_textures(window)
    pixmap_item = window.items[0].texture_item
    assert pixmap_item is not None
    assert pixmap_item.pixmap().toImage().pixelColor(2, 2).red() > 200
    assert str(texture_path) in window.texture_watcher.files()

    window.select_element(0)
    window.open_selected_atlas()
    dialog = window.atlas_dialog
    assert dialog is not None
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url) or True)
    dialog.open_dds_button.click()
    assert len(opened) == 1
    assert opened[0].isLocalFile()
    assert Path(opened[0].toLocalFile()) == texture_path
    assert window.atlas_dialog is dialog

    Image.new("RGBA", (8, 8), (15, 60, 230, 255)).save(texture_path)
    for _ in range(20):
        QTest.qWait(100)
        application.processEvents()
        pixmap_item = window.items[0].texture_item
        assert pixmap_item is not None
        if pixmap_item.pixmap().toImage().pixelColor(2, 2).blue() > 200:
            break

    assert pixmap_item.pixmap().toImage().pixelColor(2, 2).blue() > 200
    assert dialog.view._pixmap_item.pixmap().toImage().pixelColor(2, 2).blue() > 200
    assert not window.document.is_dirty
    dialog.close()
    window.deleteLater()


def test_open_dds_reports_missing_file_and_launch_failure(tmp_path: Path, monkeypatch) -> None:
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtWidgets import QMessageBox

    application = QApplication.instance() or QApplication([])
    texture_path = tmp_path / "textura com espaços e acentuação.dds"
    texture_path.write_bytes(b"dds")
    dialog = AtlasDialog(
        texture_path.name, QPixmap(8, 8), UVRect(0, 0, 8, 8),
        lambda *_: None, texture_path=texture_path,
    )
    opened = []
    warnings = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url) or False)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))
    dialog.open_dds_button.click()
    assert Path(opened[0].toLocalFile()) == texture_path
    assert len(warnings) == 1
    assert "aplicativo padrão" in warnings[0]
    texture_path.unlink()
    dialog.open_dds_button.click()
    assert len(opened) == 1
    assert len(warnings) == 2
    assert str(texture_path) in warnings[1]
    dialog.deleteLater()


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

    import gf_ui_editor.texture_cache as texture_cache_module

    original_open = texture_cache_module.open_dds_rgba
    opened: list[Path] = []

    def tracked_open(path):
        opened.append(Path(path))
        return original_open(path)

    monkeypatch.setattr(texture_cache_module, "open_dds_rgba", tracked_open)
    window = EditorWindow(first_path)
    wait_for_textures(window)
    window.open_document(second_path)
    application.processEvents()

    # No CI a pasta temporária pode vir com nome curto (RUNNER~1): compara o arquivo, não o texto.
    assert [path.resolve() for path in opened] == [texture_path.resolve()]

    Image.new("RGBA", (8, 8), (15, 60, 230, 255)).save(texture_path)
    window.open_document(first_path)
    wait_for_textures(window)
    application.processEvents()

    assert [path.resolve() for path in opened] == [texture_path.resolve()] * 2
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
    wait_for_textures(window)
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
        lambda _uv, _resize, _offset: None,
        progress_offset=(2, 12),
    )

    assert dialog.view._progress_item.isVisible()
    assert dialog.view._progress_item.rect() == QRectF(12, 32, 30, 8)
    assert "SOffset" in dialog.progress_explanation.text()
    assert not dialog.view.offset_editable  # somente leitura quando o XML não permite

    dialog.close()


def test_dragging_filled_state_box_changes_soffset() -> None:
    application = QApplication.instance() or QApplication([])
    applied: list[tuple] = []
    dialog = AtlasDialog(
        "main.dds",
        QPixmap(200, 200),
        UVRect(10, 20, 30, 8),
        lambda uv, resize, offset: applied.append((uv, offset)),
        progress_offset=(0, 12),
        offset_editable=True,
    )
    dialog.resize(900, 700)
    dialog.show()
    dialog.edit_button.setChecked(True)
    application.processEvents()
    view = dialog.view
    view.resetTransform()
    view.scale(4, 4)
    view.centerOn(25, 30)
    application.processEvents()
    start = view.mapFromScene(QPointF(25, 36))  # centro da caixa ciano (y 32..40)
    end = view.mapFromScene(QPointF(25, 16))  # 20 px para cima
    QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(view.viewport(), end, 20)
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=end)
    application.processEvents()

    assert dialog.current_offset() == (0, -8)
    assert dialog.current_uv() == UVRect(10, 20, 30, 8)  # o recorte normal não mudou
    assert dialog.overlap_warning.isHidden()  # colado logo acima: encaixe ideal, sem sobreposição
    dialog.offset_y_spin.setValue(-4)  # metade por cima do estado normal
    assert not dialog.overlap_warning.isHidden()
    dialog.offset_y_spin.setValue(-9)
    assert dialog.overlap_warning.isHidden()
    dialog._apply()
    assert applied[-1][1] == (0, -9)
    dialog.close()


def test_dragging_inside_cut_moves_it_and_filled_state_stays_on_texture() -> None:
    application = QApplication.instance() or QApplication([])
    dialog = AtlasDialog(
        "main.dds",
        QPixmap(200, 200),
        UVRect(10, 20, 30, 8),
        lambda uv, resize, offset: None,
        progress_offset=(0, 12),
        offset_editable=True,
    )
    dialog.resize(900, 700)
    dialog.show()
    dialog.edit_button.setChecked(True)
    application.processEvents()
    view = dialog.view
    view.resetTransform()
    view.fitInView(0, 0, 200, 200)
    application.processEvents()
    start = view.mapFromScene(QPointF(25, 24))  # dentro do recorte amarelo
    end = view.mapFromScene(QPointF(25, 214))  # bem abaixo da textura
    QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(view.viewport(), end, 20)
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=end)
    application.processEvents()

    assert dialog.current_uv() == UVRect(10, 192, 30, 8)  # mesmo tamanho, parou na borda
    assert dialog.current_offset() == (0, 0)  # a caixa ciano foi puxada de volta pra dentro
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


def test_game_screen_frame_and_preview_mode(tmp_path: Path) -> None:
    from PySide6.QtCore import QSettings
    from gf_ui_editor.app import parse_resolution

    settings = QSettings("Local", "GF UI Editor")
    saved = {key: settings.value(key) for key in ("game_resolution", "game_background")}
    try:
        _check_game_screen_frame(tmp_path, parse_resolution)
    finally:
        for key, value in saved.items():
            if value is None:
                settings.remove(key)
            else:
                settings.setValue(key, value)


def _check_game_screen_frame(tmp_path: Path, parse_resolution) -> None:
    assert parse_resolution("1366x768") == (1366, 768)
    assert parse_resolution("1920 × 1080") == (1920, 1080)
    assert parse_resolution("abc") is None

    application = QApplication.instance() or QApplication([])
    window = EditorWindow()
    xml_path = tmp_path / "Teste.xml"
    xml_path.write_bytes(SAMPLE.encode("big5"))
    window.open_document(xml_path)
    window.set_game_resolution((800, 600))
    application.processEvents()
    assert window.game_screen_item is not None
    assert window.game_screen_item.rect() == QRectF(0, 0, 800, 600)
    assert window.game_screen_item.zValue() < min(item.zValue() for item in window.items.values())

    item = window.items[0]
    window.outlines_action.setChecked(False)
    assert item.pen().style() == Qt.PenStyle.NoPen
    window.outlines_action.setChecked(True)
    assert item.pen().style() == Qt.PenStyle.DashLine

    background = tmp_path / "tela.png"
    QPixmap(1280, 720).save(str(background))
    window.set_game_background(background)
    assert window.game_resolution == (1280, 720)
    assert window.game_screen_item.background_item is not None

    window.set_game_resolution(None)
    assert window.game_screen_item is None
    window.set_game_background(None)


def test_screen_coordinates_are_shown_next_to_xml_coordinates(tmp_path: Path) -> None:
    from PySide6.QtCore import QSettings

    application = QApplication.instance() or QApplication([])
    settings = QSettings("Local", "GF UI Editor")
    saved = {key: settings.value(key) for key in ("game_resolution", "game_background", "background_mode")}
    # Storage.xml é centralizado pelo cliente: a raiz 100x80 vai para (350, 260) em 800x600.
    path = tmp_path / "UI" / "Storage.xml"
    path.parent.mkdir()
    path.write_bytes(
        b'<?xml version="1.0" ?>\n<Root_Node UI_File_Name="Storage.xml">\n'
        b'  <BaseWndProperty WindowID="1" WindowLeft="10" WindowTop="20" WindowHeight="100" WindowWidth="80" />\n'
        b'  <BaseWndProperty WindowID="2" WindowLeft="-5" WindowTop="30" WindowHeight="10" WindowWidth="10" />\n'
        b"</Root_Node>\n"
    )
    try:
        window = EditorWindow(path)
        window.set_game_resolution((800, 600))
        application.processEvents()
        # A raiz (10, 20) vai para o centro (350, 260): somar (340, 240) leva do XML à tela.
        assert window._screen_offset() == (340, 240)

        window._show_cursor_position(10, 20)
        assert "X 10" in window.cursor_position_label.text() and "X 350 · Y 260" in window.cursor_position_label.text()

        window.select_element(1)  # filho 15 px à esquerda e 10 abaixo da raiz
        assert not window.properties.screen_position_label.isHidden()
        assert "X 335 · Y 270" in window.properties.screen_position_label.text()
        window.move_selected(5, 0)
        assert "X 340 · Y 270" in window.properties.screen_position_label.text()

        assert window.manual_position_button.isHidden()
        window.set_root_mode("xml")  # escolha manual: a tela volta a coincidir com o XML
        assert window._screen_offset() == (0, 0)
        assert "X 0 · Y 30" in window.properties.screen_position_label.text()
        # A escolha manual fica à vista na barra do canvas e sai com um clique.
        assert not window.manual_position_button.isHidden()
        window.manual_position_button.click()
        assert window._root_mode() == "auto"
        assert window.manual_position_button.isHidden()
        assert window._screen_offset() != (0, 0)
    finally:
        settings.remove("root_mode/storage.xml")
        for key, value in saved.items():
            settings.remove(key) if value is None else settings.setValue(key, value)


def test_dragging_a_game_centered_window_moves_its_content_on_screen(tmp_path: Path) -> None:
    """Caso medido no jogo: raiz (134, 302) -> (-100, 250) moveu o conteúdo (+234, +52)."""
    application = QApplication.instance() or QApplication([])
    path = tmp_path / "UI" / "Storage.xml"  # centralizada pelo cliente
    path.parent.mkdir()
    path.write_bytes(
        b'<?xml version="1.0" ?>\n<Root_Node UI_File_Name="Storage.xml">\n'
        b'  <BaseWndProperty WindowID="1" WindowLeft="134" WindowTop="302" WindowHeight="434" WindowWidth="306" />\n'
        b'  <BaseWndProperty WindowID="2" WindowLeft="140" WindowTop="310" WindowHeight="20" WindowWidth="20" />\n'
        b"</Root_Node>\n"
    )
    window = EditorWindow(path)
    window.set_game_resolution((1920, 1080))

    def child_on_screen() -> tuple[int, int]:
        offset = window._screen_offset()
        child = window.document.elements[1]
        return child.x + offset[0], child.y + offset[1]

    assert window._screen_offset() == (743 - 134, 387 - 302)  # raiz no centro
    assert child_on_screen() == (749, 395)

    # No painel, X/Y da janela são a posição na tela; o XML recebe os valores do Notepad++ dele.
    window.select_element(0)
    assert (window.properties.x_spin.value(), window.properties.y_spin.value()) == (749, 395)
    window.properties.x_spin.setValue(749 + 234)
    window.properties.y_spin.setValue(395 + 52)
    assert child_on_screen() == (749 + 234, 395 + 52)
    assert window.document.elements[0].geometry == (-100, 250, 434, 306)
    assert (window.properties.x_spin.value(), window.properties.y_spin.value()) == (749 + 234, 395 + 52)
    window.undo_stack.undo()
    window.undo_stack.undo()

    assert window.ghost_item is None  # o conteúdo continua em cima da janela principal

    # Arrastar a janela 463 px para a esquerda: o conteúdo vai para lá e a raiz anda ao contrário.
    # Como o conteúdo sai de cima da janela principal, ela encolhe para 1 × 1 (senão ficaria
    # uma área invisível no centro) com o X/Y compensado: (1920-1)//2 - (1920-434)//2 = 216.
    window.elements_dragged({0: ((134, 302, 434, 306), (134 - 463, 302 + 4, 434, 306))})
    application.processEvents()
    assert window.document.elements[0].geometry == (134 + 463 + 216, 302 - 4 + 152, 1, 1)
    assert window.document.elements[1].geometry == (140, 310, 20, 20)
    assert child_on_screen() == (749 - 463, 395 + 4)
    assert window.ghost_item is None

    # Movendo tudo junto, a diferença não muda: nada é invertido e nada muda no jogo.
    before = child_on_screen()
    window.elements_dragged(
        {0: (window.document.elements[0].geometry, (916, 452, 1, 1)), 1: ((140, 310, 20, 20), (243, 312, 20, 20))}
    )
    assert window.document.elements[0].geometry == (916, 452, 1, 1)
    assert child_on_screen() == before


def test_dragging_a_free_window_keeps_plain_xml_semantics(tmp_path: Path) -> None:
    path = tmp_path / "UI" / "Solta.xml"  # sem regra do jogo: a raiz fica no X/Y do XML
    path.parent.mkdir()
    path.write_bytes(
        b'<?xml version="1.0" ?>\n<Root_Node UI_File_Name="Solta.xml">\n'
        b'  <BaseWndProperty WindowID="1" WindowLeft="100" WindowTop="50" WindowHeight="200" WindowWidth="120" />\n'
        b"</Root_Node>\n"
    )
    window = EditorWindow(path)
    window.set_game_resolution((800, 600))
    window.elements_dragged({0: ((100, 50, 200, 120), (130, 40, 200, 120))})
    assert window.document.elements[0].geometry == (130, 40, 200, 120)


def test_window_frame_follows_the_content_and_stays_where_it_is_dropped(tmp_path: Path) -> None:
    """A raiz de uma janela centralizada é a moldura do conteúdo: arrasta-se como uma janela comum."""
    application = QApplication.instance() or QApplication([])
    path = tmp_path / "UI" / "Storage.xml"
    path.parent.mkdir()
    path.write_bytes(
        b'<?xml version="1.0" ?>\n<Root_Node UI_File_Name="Storage.xml">\n'
        b'  <BaseWndProperty WindowID="1" WindowLeft="134" WindowTop="302" WindowHeight="434" WindowWidth="306" />\n'
        b'  <BaseWndProperty WindowID="2" WindowLeft="140" WindowTop="310" WindowHeight="60" WindowWidth="40" />\n'
        b"</Root_Node>\n"
    )
    window = EditorWindow(path)
    window.set_game_resolution((1920, 1080))
    window.show()
    window.view.resetTransform()
    window.select_element(0)
    window.view.centerOn(window.items[1])
    application.processEvents()
    frame, child, viewport = window.items[0], window.items[1], window.view.viewport()

    def in_view(item):
        return window.view.mapFromScene(item.pos())

    assert frame.sceneBoundingRect().contains(child.mapRectToScene(child.rect()))
    assert frame.rect().size() == child.rect().size()

    for step in (QPoint(-80, 30), QPoint(50, -20)):
        child_before, screen_before = in_view(child), in_view(window.game_screen_item)
        root_before = window.document.elements[0].geometry
        start = window.view.mapFromScene(frame.mapRectToScene(frame.rect()).center())
        QTest.mousePress(viewport, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(viewport, start + step, 20)
        application.processEvents()
        assert in_view(child) == child_before + step  # o conteúdo acompanha durante o arraste
        QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, pos=start + step)
        application.processEvents()

        assert in_view(child) == child_before + step  # e fica onde foi solto
        assert in_view(window.game_screen_item) == screen_before  # a tela não se mexe
        assert in_view(frame) == in_view(child)  # a moldura continua em volta do conteúdo
        assert window.document.elements[1].geometry == (140, 310, 60, 40)
        assert window.document.elements[0].geometry != root_before
    # O conteúdo saiu de cima da janela principal: ela encolheu e não sobra área invisível.
    assert window.document.elements[0].geometry[2:] == (1, 1)
    assert window.ghost_item is None
    window.deleteLater()


def test_dragging_the_main_window_of_a_free_window_moves_everything(tmp_path: Path) -> None:
    """Janela que o jogo não fixa: arrastar a principal leva o conteúdo, ao vivo e no XML."""
    application = QApplication.instance() or QApplication([])
    path = tmp_path / "UI" / "Solta.xml"
    path.parent.mkdir()
    path.write_bytes(
        b'<?xml version="1.0" ?>\n<Root_Node UI_File_Name="Solta.xml">\n'
        b'  <BaseWndProperty WindowID="1" WindowLeft="100" WindowTop="50" WindowHeight="200" WindowWidth="120" />\n'
        b'  <BaseWndProperty WindowID="2" WindowLeft="110" WindowTop="60" WindowHeight="40" WindowWidth="30" />\n'
        b"</Root_Node>\n"
    )
    window = EditorWindow(path)
    window.set_game_resolution((800, 600))
    window.show()
    window.view.resetTransform()
    window.select_element(0)
    window.view.centerOn(window.items[0])
    application.processEvents()
    root, child, viewport = window.items[0], window.items[1], window.view.viewport()
    start = window.view.mapFromScene(QPointF(250, 150))  # dentro da principal, fora do filho
    child_before = window.view.mapFromScene(child.pos())
    step = QPoint(40, -25)
    QTest.mousePress(viewport, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(viewport, start + step, 20)
    application.processEvents()
    assert window.view.mapFromScene(child.pos()) == child_before + step  # acompanha durante o arraste
    QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, pos=start + step)
    application.processEvents()

    assert window.document.elements[0].geometry == (140, 25, 200, 120)
    assert window.document.elements[1].geometry == (150, 35, 40, 30)
    assert root.pos() == QPointF(140, 25) and child.pos() == QPointF(150, 35)
    window.undo_stack.undo()  # um passo só
    assert window.document.elements[0].geometry == (100, 50, 200, 120)
    assert window.document.elements[1].geometry == (110, 60, 40, 30)

    # No painel o X/Y continua sendo o do XML: move só a principal, para ajuste fino.
    window.properties.x_spin.setValue(90)
    assert window.document.elements[0].geometry == (90, 50, 200, 120)
    assert window.document.elements[1].geometry == (110, 60, 40, 30)
    window.deleteLater()


def test_invisible_window_area_is_shown_and_removed_in_one_click(tmp_path: Path) -> None:
    """Arquivo que já chega deslocado (editado à mão): a janela principal sobra longe do conteúdo."""
    application = QApplication.instance() or QApplication([])
    path = tmp_path / "UI" / "Storage.xml"  # centralizada pelo cliente
    path.parent.mkdir()
    path.write_bytes(
        b'<?xml version="1.0" ?>\n<Root_Node UI_File_Name="Storage.xml">\n'
        b'  <BaseWndProperty WindowID="1" WindowLeft="600" WindowTop="50" WindowHeight="200" WindowWidth="100" />\n'
        b'  <BaseWndProperty WindowID="2" WindowLeft="0" WindowTop="0" WindowHeight="200" WindowWidth="100" />\n'
        b"</Root_Node>\n"
    )
    window = EditorWindow(path)
    window.set_game_resolution((1920, 1080))
    window.select_element(0)

    def child_on_screen() -> tuple[int, int]:
        offset = window._screen_offset()
        child = window.document.elements[1]
        return child.x + offset[0], child.y + offset[1]

    before = child_on_screen()
    assert window.ghost_item is not None
    assert window.ghost_item.pos() == QPointF(600, 50)  # o retângulo real da janela principal
    assert not window.properties.ghost_button.isHidden()

    window.properties.ghost_button.click()
    assert window.document.elements[0].geometry[2:] == (1, 1)
    assert child_on_screen() == before
    assert window.ghost_item is None
    assert window.properties.ghost_button.isHidden()

    window.undo_stack.undo()
    assert window.document.elements[0].geometry == (600, 50, 200, 100)
    assert window.ghost_item is not None

    # Sem a moldura do jogo não há como saber onde a janela cai: nenhum aviso.
    window.set_game_resolution(None)
    assert window.ghost_item is None


def test_resizing_a_game_positioned_window_keeps_its_content_in_place(tmp_path: Path) -> None:
    application = QApplication.instance() or QApplication([])
    path = tmp_path / "UI" / "Storage.xml"
    path.parent.mkdir()
    path.write_bytes(
        b'<?xml version="1.0" ?>\n<Root_Node UI_File_Name="Storage.xml">\n'
        b'  <BaseWndProperty WindowID="1" WindowLeft="0" WindowTop="0" WindowHeight="200" WindowWidth="100" />\n'
        b'  <BaseWndProperty WindowID="2" WindowLeft="0" WindowTop="0" WindowHeight="200" WindowWidth="100" />\n'
        b"</Root_Node>\n"
    )
    window = EditorWindow(path)
    window.set_game_resolution((1920, 1080))
    window.select_element(0)
    offset = window._screen_offset()
    window.properties.width_spin.setValue(80)
    window.properties.height_spin.setValue(40)
    assert window.document.elements[0].geometry[2:] == (80, 40)
    assert window._screen_offset() == offset  # o conteúdo não pulou
    assert window.document.elements[1].geometry == (0, 0, 200, 100)


def test_navigation_styles_map_wheel_to_zoom_or_scroll() -> None:
    from PySide6.QtGui import QWheelEvent

    application = QApplication.instance() or QApplication([])
    view = EditorView(lambda dx, dy: None)
    scene = QGraphicsScene(0, 0, 5000, 5000)
    view.setScene(scene)
    view.resize(400, 300)
    view.show()
    application.processEvents()

    def wheel(modifiers=Qt.KeyboardModifier.NoModifier) -> None:
        event = QWheelEvent(
            QPointF(200, 150), QPointF(200, 150), QPoint(), QPoint(0, -120),
            Qt.MouseButton.NoButton, modifiers, Qt.ScrollPhase.NoScrollPhase, False,
        )
        view.wheelEvent(event)

    view.navigation_style = "corel"
    zoom = view.transform().m11()
    wheel()
    assert view.transform().m11() < zoom

    view.navigation_style = "paintnet"
    zoom, top = view.transform().m11(), view.verticalScrollBar().value()
    wheel()
    assert view.transform().m11() == zoom and view.verticalScrollBar().value() > top
    left = view.horizontalScrollBar().value()
    wheel(Qt.KeyboardModifier.ShiftModifier)
    assert view.horizontalScrollBar().value() > left
    wheel(Qt.KeyboardModifier.ControlModifier)
    assert view.transform().m11() < zoom

    view.navigation_style = "photoshop"
    zoom = view.transform().m11()
    wheel(Qt.KeyboardModifier.AltModifier)
    assert view.transform().m11() < zoom
    view.close()


def test_loose_xml_outside_the_game_uses_the_configured_game_folder(tmp_path: Path) -> None:
    from PySide6.QtCore import QSettings

    application = QApplication.instance() or QApplication([])
    game = tmp_path / "Game"
    (game / "UI").mkdir(parents=True)
    (game / "client.ini").write_text("[Option]\n", encoding="utf-8")
    loose = tmp_path / "Downloads" / "Storage.xml"
    loose.parent.mkdir()
    loose.write_bytes(SAMPLE.encode("big5"))
    QSettings("Local", "GF UI Editor").setValue("game_dir", str(game))

    window = EditorWindow(loose)
    assert window._document_game_dir() == game

    inside = game / "UI" / "Storage.xml"
    inside.write_bytes(SAMPLE.encode("big5"))
    window.open_document(inside)
    assert window._document_game_dir() == game
    window.close()


def test_atlas_opens_read_only_framed_on_the_slice_and_edges_resize_when_editing() -> None:
    application = QApplication.instance() or QApplication([])
    dialog = AtlasDialog("main.dds", QPixmap(400, 400), UVRect(100, 120, 40, 20), lambda *_: None)
    dialog.resize(900, 700)
    dialog.show()
    application.processEvents()
    application.processEvents()
    view = dialog.view
    assert view.transform().m11() > 2  # enquadrado no recorte, não no atlas inteiro
    assert not dialog.apply_button.isEnabled() and dialog.left_spin.isReadOnly()

    start = view.mapFromScene(QPointF(110, 125))
    QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(view.viewport(), start + QPoint(40, 30), 20)
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=start + QPoint(40, 30))
    assert dialog.current_uv() == UVRect(100, 120, 40, 20)  # só moveu a vista

    dialog.edit_button.setChecked(True)
    assert dialog.apply_button.isEnabled()
    edge = view.mapFromScene(QPointF(140, 130))  # meio da borda direita
    end = view.mapFromScene(QPointF(149.5, 130))
    QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=edge)
    QTest.mouseMove(view.viewport(), end, 20)
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=end)
    assert dialog.current_uv() == UVRect(100, 120, 50, 20)
    dialog.close()


def test_official_controls_are_inserted_as_an_undoable_edit(tmp_path: Path, monkeypatch) -> None:
    import zlib

    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QDialog

    import gf_ui_editor.app as app_module

    application = QApplication.instance() or QApplication([])
    official = SAMPLE.replace(
        "</Root_Node>",
        '  <BaseWndProperty WindowID="900">\n    <Container_Node Child_Cnt="1">\n'
        '      <Style CtrlType="1" />\n      <BaseWndProperty WindowID="5130" WindowLeft="3" WindowTop="4" WindowHeight="10" WindowWidth="10" />\n'
        "    </Container_Node>\n  </BaseWndProperty>\n</Root_Node>",
    )
    custom = official.replace('Child_Cnt="1"', 'Child_Cnt="0"').replace(
        '      <Style CtrlType="1" />\n      <BaseWndProperty WindowID="5130" WindowLeft="3" WindowTop="4" WindowHeight="10" WindowWidth="10" />\n', ""
    )
    game = tmp_path / "Game"
    (game / "UI").mkdir(parents=True)
    data = official.encode("big5")
    (game / "UI" / "Storage.xml").write_bytes(data)
    (game / "client.ini").write_text("[Option]\n", encoding="utf-8")
    (game / "GameDataFileList.txt").write_text(
        f"UI\\Storage.xml|{len(data)}|{zlib.crc32(data):08X}|1|0|\n", encoding="latin-1"
    )
    loose = tmp_path / "Downloads" / "Storage.xml"
    loose.parent.mkdir()
    loose.write_bytes(custom.encode("big5"))
    QSettings("Local", "GF UI Editor").setValue("game_dir", str(game))

    monkeypatch.setattr(app_module.OfficialControlsDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    window = EditorWindow(loose)
    before = len(window.document.elements)
    window.open_official_compare(focus_id="5130")
    assert len(window.document.elements) == before + 1
    assert window.document.is_dirty
    inserted = next(index for index, element in enumerate(window.document.elements) if element.window_id == "5130")
    assert window.selected_index == inserted

    window.undo_stack.undo()
    assert len(window.document.elements) == before and not window.document.is_dirty
    window.undo_stack.redo()
    monkeypatch.setattr(window, "_confirm_diff_preview", lambda: True)
    monkeypatch.setattr(app_module.QMessageBox, "information", lambda *args, **kwargs: None)
    window.save_document()
    assert loose.read_bytes().decode("big5").count('WindowID="5130"') == 1
    assert 'Child_Cnt="1"' in loose.read_bytes().decode("big5")
    window.close()


def test_texture_of_a_control_can_be_changed_undone_and_saved(tmp_path: Path) -> None:
    import gf_ui_editor.app as app_module

    application = QApplication.instance() or QApplication([])
    xml = (
        '<?xml version="1.0" ?>\n<Root_Node UI_File_Name="T.xml">\n'
        '  <BaseWndProperty WindowID="1" WindowHeight="100" WindowWidth="80">\n'
        '    <BackGroundMap BGmap="main.dds"><NorUV NorUVLeft="0" NorUVTop="0" NorUVWidth="4" NorUVHeight="4" /></BackGroundMap>\n'
        '    <Container_Node Child_Cnt="1">\n      <Style CtrlType="1" />\n'
        '      <BaseWndProperty WindowID="2" WindowHeight="4" WindowWidth="4">\n'
        '        <BackGroundMap BGmap="main.dds"><NorUV NorUVLeft="0" NorUVTop="0" NorUVWidth="4" NorUVHeight="4" /></BackGroundMap>\n'
        "      </BaseWndProperty>\n    </Container_Node>\n  </BaseWndProperty>\n</Root_Node>\n"
    )
    path = tmp_path / "UI" / "T.xml"
    path.parent.mkdir()
    path.write_bytes(xml.encode("big5"))
    window = EditorWindow(path)
    window.undo_stack.push(app_module.TextureCommand(window, {1: ("main.dds", "meu.dds")}))
    assert window.document.elements[1].texture_name == "meu.dds" and window.document.is_dirty
    window.undo_stack.undo()
    assert window.document.elements[1].texture_name == "main.dds" and not window.document.is_dirty
    window.undo_stack.redo()
    window.document.save()
    saved = path.read_bytes().decode("big5")
    assert saved == xml.replace('BGmap="main.dds"><NorUV NorUVLeft="0" NorUVTop="0" NorUVWidth="4" NorUVHeight="4" /></BackGroundMap>\n      </BaseWndProperty>',
                                'BGmap="meu.dds"><NorUV NorUVLeft="0" NorUVTop="0" NorUVWidth="4" NorUVHeight="4" /></BackGroundMap>\n      </BaseWndProperty>')
    assert saved.count('BGmap="main.dds"') == 1  # o controle 1 continua com a textura dele
    window.close()


def test_duplicate_hide_and_delete_controls_with_undo(tmp_path: Path) -> None:
    import zlib

    from PySide6.QtCore import QSettings

    application = QApplication.instance() or QApplication([])
    xml = (
        '<?xml version="1.0" ?>\n<Root_Node UI_File_Name="Storage.xml">\n'
        '  <BaseWndProperty WindowID="1" WindowHeight="100" WindowWidth="80">\n'
        '    <Container_Node Child_Cnt="1">\n      <Style CtrlType="268435456" />\n'
        '      <BaseWndProperty WindowID="2" WindowLeft="10" WindowTop="10" WindowHeight="20" WindowWidth="20" />\n'
        "    </Container_Node>\n  </BaseWndProperty>\n</Root_Node>\n"
    )
    game = tmp_path / "Game"
    (game / "UI").mkdir(parents=True)
    data = xml.encode("big5")
    (game / "UI" / "Storage.xml").write_bytes(data)
    (game / "client.ini").write_text("[Option]\n", encoding="utf-8")
    (game / "GameDataFileList.txt").write_text(f"UI\\Storage.xml|{len(data)}|{zlib.crc32(data):08X}|1|0|\n", encoding="latin-1")
    path = tmp_path / "Downloads" / "Storage.xml"
    path.parent.mkdir()
    path.write_bytes(data)
    QSettings("Local", "GF UI Editor").setValue("game_dir", str(game))

    window = EditorWindow(path)
    window.select_element(1)
    window.duplicate_selected()
    assert [element.window_id for element in window.document.elements] == ["1", "2", "3"]
    copy = window.document.elements[2]
    assert window.selected_index == 2 and (copy.x, copy.y) == (18, 18)

    window.toggle_selected_game_visibility()
    assert not window.document.elements[2].visible
    window.undo_stack.undo()
    assert window.document.elements[2].visible

    window.select_element(2)
    window.delete_selected()  # o 3 não existe no oficial: apaga sem perguntar
    assert [element.window_id for element in window.document.elements] == ["1", "2"]
    window.undo_stack.undo()
    window.undo_stack.undo()
    assert [element.window_id for element in window.document.elements] == ["1", "2"]
    assert not window.document.is_dirty
    window.close()


def test_renaming_a_texture_can_update_the_xml_that_use_it(tmp_path: Path, monkeypatch) -> None:
    import gf_ui_editor.app as app_module

    application = QApplication.instance() or QApplication([])
    source = tmp_path / "source"
    source.mkdir()
    (source / "T.xml").write_bytes(
        b'<?xml version="1.0" ?>\n<Root_Node UI_File_Name="T.xml">\n'
        b'  <BaseWndProperty WindowID="1"><BackGroundMap BGmap="main2.dds" /></BaseWndProperty>\n</Root_Node>\n'
    )
    Image.new("RGBA", (4, 4)).save(source / "main2.dds")
    project = Project.create("Tex", source, None, projects_root=tmp_path / "projects")
    window = EditorWindow()
    window.open_project(project.root)
    monkeypatch.setattr(app_module.QInputDialog, "getText", lambda *args, **kwargs: ("main.dds", True))
    monkeypatch.setattr(app_module.QMessageBox, "question", lambda *args, **kwargs: app_module.QMessageBox.StandardButton.Yes)
    window.rename_project_file(project.ui_dir / "main2.dds")
    assert (project.ui_dir / "main.dds").exists() and not (project.ui_dir / "main2.dds").exists()
    assert b'BGmap="main.dds"' in (project.ui_dir / "T.xml").read_bytes()

    window.delete_project_file(project.ui_dir / "T.xml")
    assert not (project.ui_dir / "T.xml").exists()
    window.close()


def test_escape_clears_the_selection(tmp_path: Path) -> None:
    application = QApplication.instance() or QApplication([])
    path = tmp_path / "Teste.xml"
    path.write_bytes(SAMPLE.encode("big5"))
    window = EditorWindow(path)
    window.select_element(0)
    assert window.selected_index == 0
    window.deselect_action.trigger()
    assert window.selected_index is None
    assert not any(item.isSelected() for item in window.items.values())
    window.close()


def test_basicchar_portrait_marker_stays_fixed_on_the_game_screen(tmp_path: Path) -> None:
    application = QApplication.instance() or QApplication([])
    path = tmp_path / "BasicChar.xml"
    path.write_bytes(
        b'<?xml version="1.0" ?>\r\n<Root_Node UI_File_Name="BasicChar.xml">\r\n'
        b'\t<BaseWndProperty WindowID="1" WindowLeft="0" WindowTop="0" WindowHeight="181" WindowWidth="88" />\r\n'
        b"</Root_Node>\r\n"
    )
    window = EditorWindow()
    window.open_document(path)
    application.processEvents()
    marker = window.game_drawn_item
    if window.game_screen_item is None:
        assert marker is None  # sem tela do jogo não há onde fixar
    else:
        assert marker is not None and marker.scene() is window.scene
        offset = marker.pos() - window.game_screen_item.pos()
        assert (offset.x(), offset.y()) == (23, 7)  # canto da tela, não da janela
    window.close()


def test_portrait_marker_can_be_hidden_from_the_floating_bar(tmp_path: Path) -> None:
    application = QApplication.instance() or QApplication([])
    path = tmp_path / "BasicChar.xml"
    path.write_bytes(b'<?xml version="1.0" ?>\n<Root_Node UI_File_Name="BasicChar.xml">\n  <BaseWndProperty WindowID="1" WindowHeight="181" WindowWidth="88" />\n</Root_Node>\n')
    window = EditorWindow()
    window.open_document(path)
    window.set_game_resolution((1024, 768))
    application.processEvents()
    assert window.game_drawn_item is not None and not window.game_drawn_button.isHidden()
    window.game_drawn_action.setChecked(False)
    assert not window.game_drawn_item.isVisible()
    window.game_drawn_action.setChecked(True)
    assert window.game_drawn_item.isVisible()
    window.set_game_resolution(None)
    assert window.game_drawn_item is None and window.game_drawn_button.isHidden()
    window.close()


def test_missing_official_reference_shows_a_banner_until_dismissed(tmp_path: Path, monkeypatch) -> None:
    import gf_ui_editor.app as app_module

    application = QApplication.instance() or QApplication([])
    (tmp_path / "GameDataFileList.txt").write_text("", encoding="latin-1")
    window = EditorWindow()
    monkeypatch.setattr(window, "_document_game_dir", lambda: tmp_path)
    monkeypatch.setattr(app_module, "reference_ready", lambda game_dir: False)
    window._update_reference_chip()
    assert not window.reference_banner.isHidden()
    window._dismiss_reference_banner()
    window._update_reference_chip()
    assert window.reference_banner.isHidden()  # dispensado vale até fechar o editor
    window.reference_banner_dismissed = False
    monkeypatch.setattr(app_module, "reference_ready", lambda game_dir: True)
    window._update_reference_chip()
    assert window.reference_banner.isHidden()  # quem já tem a referência não vê nada
    window.close()


def test_text_mode_draws_samples_like_the_game_and_flags_overflow(tmp_path: Path) -> None:
    application = QApplication.instance() or QApplication([])
    path = tmp_path / "T.xml"
    path.write_bytes(
        b'<?xml version="1.0" ?>\r\n<Root_Node UI_File_Name="T.xml">\r\n'
        b'\t<BaseWndProperty WindowID="1" WindowHeight="200" WindowWidth="100">\r\n'
        b'\t\t<Container_Node Child_Cnt="2">\r\n'
        b'\t\t\t<Style ParentNode="1" CtrlType="2" />\r\n'
        b'\t\t\t<BaseWndProperty WindowID="10" WindowLeft="0" WindowTop="0" WindowHeight="150" WindowWidth="14">\r\n'
        b'\t\t\t\t<BaseCtrlProperty FontColor="65535" FontStyle="1" />\r\n\t\t\t\t<TextNode TextAlign="1" />\r\n'
        b'\t\t\t</BaseWndProperty>\r\n'
        b'\t\t\t<Style ParentNode="1" CtrlType="2" />\r\n'
        b'\t\t\t<BaseWndProperty WindowID="11" WindowLeft="0" WindowTop="20" WindowHeight="10" WindowWidth="14">\r\n'
        b'\t\t\t\t<BaseCtrlProperty FontColor="16777215" FontStyle="0" />\r\n\t\t\t\t<TextNode TextAlign="0" />\r\n'
        b'\t\t\t</BaseWndProperty>\r\n'
        b'\t\t</Container_Node>\r\n\t</BaseWndProperty>\r\n</Root_Node>\r\n'
    )
    window = EditorWindow()
    window.open_document(path)
    wide, narrow = (window.items[element.index] for element in window.document.elements[1:])
    assert window.document.elements[1].text_props == {"FontColor": "65535", "FontStyle": "1", "TextAlign": "1"}
    assert wide.text_item is None  # desligado por padrão
    window.set_text_mode("short")
    assert wide.text_item.text and wide.text_item.outline and wide.text_item.align == "1"
    assert wide.text_item.color.name() == "#ffff00"  # FontColor é BGR
    assert not wide.text_item.overflows
    assert narrow.text_item.overflows  # 10 px não cabe "Texto"
    window.set_text_mode("off")
    assert wide.text_item.text == ""
    window.close()


def test_checked_files_show_as_reference_layers_where_the_game_draws_them(tmp_path: Path) -> None:
    from gf_ui_editor.editor_widgets import ReferenceLayerItem
    from gf_ui_editor.project import Project

    application = QApplication.instance() or QApplication([])
    source = tmp_path / "source"
    source.mkdir()
    for name in ("Menu.xml", "BasicChar.xml"):
        (source / name).write_bytes(
            f'<?xml version="1.0" ?>\r\n<Root_Node UI_File_Name="{name}">\r\n'
            '\t<BaseWndProperty WindowID="1" WindowLeft="0" WindowTop="0" WindowHeight="100" WindowWidth="40" />\r\n'
            "</Root_Node>\r\n".encode("big5")
        )
    project = Project.create("Camadas", source, None, projects_root=tmp_path / "projects")
    window = EditorWindow()
    window.open_project(project.root)
    window.open_document(project.ui_dir / "Menu.xml")
    window.set_game_resolution((800, 600))
    application.processEvents()

    window.set_reference_layer("BasicChar.xml", True)
    assert Project.load(project.root).reference_layers == ["BasicChar.xml"]  # fica salvo no projeto
    layers = [item for item in window.scene.items() if isinstance(item, ReferenceLayerItem)]
    assert [layer.name for layer in layers] == ["BasicChar.xml"]
    assert layers[0].zValue() < 0  # por baixo do arquivo em edição
    assert not layers[0].acceptedMouseButtons()  # não rouba cliques

    window.set_reference_layer("BasicChar.xml", False)
    assert not [item for item in window.scene.items() if isinstance(item, ReferenceLayerItem)]
    window.set_game_resolution(None)
    window.close()


def test_default_hud_checks_the_always_visible_windows_and_lists_them_first(tmp_path: Path) -> None:
    from gf_ui_editor.project import Project

    application = QApplication.instance() or QApplication([])
    source = tmp_path / "source"
    source.mkdir()
    for name in ("Menu.xml", "Radar.xml", "Channel.xml", "Bank.xml"):
        (source / name).write_bytes(
            f'<?xml version="1.0" ?>\r\n<Root_Node UI_File_Name="{name}">\r\n'
            '\t<BaseWndProperty WindowID="1" WindowHeight="100" WindowWidth="40" />\r\n</Root_Node>\r\n'.encode("big5")
        )
    project = Project.create("Hud", source, None, projects_root=tmp_path / "projects")
    window = EditorWindow()
    window.open_project(project.root)
    window.build_default_hud()
    application.processEvents()
    assert sorted(window.project.reference_layers) == ["Channel.xml", "Menu.xml", "Radar.xml"]  # Bank não é HUD
    first_group = window.files_tree.topLevelItem(0)
    assert first_group.text(0).startswith("CAMADAS") or first_group.text(0).startswith("LAYERS")
    assert first_group.childCount() == 3
    window.set_reference_layers([])
    application.processEvents()
    assert window.project.reference_layers == []
    window.close()


def test_textures_already_cached_by_layers_still_reach_the_open_file(tmp_path: Path) -> None:
    from gf_ui_editor.project import Project

    application = QApplication.instance() or QApplication([])
    source = tmp_path / "source"
    source.mkdir()
    Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(source / "main.dds")
    for name in ("Menu.xml", "Channel.xml"):
        (source / name).write_bytes(
            f'<?xml version="1.0" ?>\r\n<Root_Node UI_File_Name="{name}">\r\n'
            '\t<BaseWndProperty WindowID="1" WindowHeight="8" WindowWidth="8">\r\n'
            '\t\t<BackGroundMap BGmap="main.dds">\r\n'
            '\t\t\t<NorUV NorUVLeft="0" NorUVTop="0" NorUVWidth="8" NorUVHeight="8" />\r\n'
            '\t\t</BackGroundMap>\r\n\t</BaseWndProperty>\r\n</Root_Node>\r\n'.encode("big5")
        )
    project = Project.create("Cache", source, None, projects_root=tmp_path / "projects")
    project.reference_layers = ["Menu.xml"]
    project.save_manifest()
    window = EditorWindow()
    window.open_project(project.root)
    window.set_game_resolution((800, 600))
    window.open_document(project.ui_dir / "Channel.xml")  # a camada Menu já leu o main.dds
    application.processEvents()
    texture = window.items[0].texture_item
    assert texture is not None and not texture.pixmap().isNull()
    window.set_game_resolution(None)
    window.close()


def test_state_icons_in_the_element_list_hide_lock_and_isolate(tmp_path: Path) -> None:
    application = QApplication.instance() or QApplication([])
    path = tmp_path / "Teste.xml"
    path.write_bytes(
        b'<?xml version="1.0" ?>\r\n<Root_Node UI_File_Name="Teste.xml">\r\n'
        b'<BaseWndProperty WindowID="1" WindowHeight="100" WindowWidth="80">'
        b'<Container_Node Child_Cnt="1"><Style ParentNode="1" CtrlType="1" />'
        b'<BaseWndProperty WindowID="5" WindowLeft="4" WindowTop="4" WindowHeight="20" WindowWidth="10" />'
        b'</Container_Node></BaseWndProperty>\r\n</Root_Node>\r\n'
    )
    window = EditorWindow()
    window.open_document(path)
    window.show()
    application.processEvents()
    tree_item = window.tree_items[1]
    window.tree.scrollToItem(tree_item)
    rect = window.tree.visualRect(window.tree.indexFromItem(tree_item, 3))

    def click(slot: int) -> None:
        point = QPoint(rect.left() + 4 + slot * 20 + 10, rect.center().y())
        QTest.mouseClick(window.tree.viewport(), Qt.MouseButton.LeftButton, pos=point)
        application.processEvents()

    click(0)
    assert 1 in window.hidden_indexes and not window.items[1].isVisible()
    assert window.selected_index is None  # o clique no ícone não seleciona a linha
    click(0)
    click(1)
    assert 1 in window.locked_indexes
    click(2)
    assert window.isolated_index == 1 and not window.isolation_button.isHidden()
    assert not window.items[0].isVisible()
    window.isolation_button.click()
    assert window.isolated_index is None and window.isolation_button.isHidden()
    window.close()


def test_moving_many_elements_refreshes_the_window_once(tmp_path: Path, monkeypatch) -> None:
    application = QApplication.instance() or QApplication([])
    children = "".join(
        f'<Style ParentNode="1" CtrlType="1" /><BaseWndProperty WindowID="{100 + n}" WindowLeft="{n}" WindowTop="0" WindowHeight="5" WindowWidth="5" />'
        for n in range(60)
    )
    path = tmp_path / "Muitos.xml"
    path.write_bytes(
        ('<?xml version="1.0" ?>\r\n<Root_Node UI_File_Name="Muitos.xml">\r\n'
         '<BaseWndProperty WindowID="1" WindowHeight="300" WindowWidth="100">'
         f'<Container_Node Child_Cnt="60">{children}</Container_Node></BaseWndProperty>\r\n</Root_Node>\r\n').encode("big5")
    )
    window = EditorWindow()
    window.open_document(path)
    calls = []
    monkeypatch.setattr(window, "_update_title", lambda: calls.append(1))
    changes = {
        element.index: (element.geometry, (element.x + 3, element.y, element.width, element.height))
        for element in window.document.elements[1:]
    }
    window.elements_dragged(changes)
    assert len(calls) == 1  # antes: uma vez por elemento (segundos ao soltar 150 elementos)
    assert all(window.document.elements[index].x == new[0] for index, (_old, new) in changes.items())
    window.undo_stack.undo()
    assert len(calls) == 2
    window.close()


def test_guild_tabs_open_where_the_guild_window_is_and_layers_button_lights_up(tmp_path: Path) -> None:
    from gf_ui_editor.game_layout import placement, root_screen_position, saved_section_for
    from gf_ui_editor.project import Project

    rect = (0, 0, 676, 416)
    main = root_screen_position("Fellowship_family.xml", (1920, 1080), rect)
    for tab in ("Fellowship_FamilyAffairs.xml", "FamilyAchievement.xml", "FamilyTreeWnd.xml"):
        assert root_screen_position(tab, (1920, 1080), rect) == main
        assert placement(tab) == placement("Fellowship_family.xml")
    assert saved_section_for("ShortcutBar.xml") == "SHORTCUT01"

    application = QApplication.instance() or QApplication([])
    source = tmp_path / "source"
    source.mkdir()
    (source / "Menu.xml").write_bytes(b'<?xml version="1.0" ?>\r\n<Root_Node><BaseWndProperty WindowID="1" /></Root_Node>\r\n')
    project = Project.create("Botao", source, None, projects_root=tmp_path / "projects")
    window = EditorWindow()
    window.open_project(project.root)
    assert not window.layers_button.isChecked()
    window.set_reference_layers(["Menu.xml"])
    assert window.layers_button.isChecked()
    window.set_reference_layers([])
    assert not window.layers_button.isChecked()
    window.close()


def test_isolating_a_panel_keeps_its_children_visible(tmp_path: Path) -> None:
    application = QApplication.instance() or QApplication([])
    path = tmp_path / "Grupo.xml"
    path.write_bytes(
        b'<?xml version="1.0" ?>\r\n<Root_Node UI_File_Name="Grupo.xml">\r\n'
        b'<BaseWndProperty WindowID="1" WindowHeight="100" WindowWidth="100"><Container_Node Child_Cnt="3">'
        b'<Style ParentNode="1" CtrlType="1" /><BaseWndProperty WindowID="10" WindowHeight="50" WindowWidth="50" />'
        b'<Style ParentNode="10" CtrlType="1" /><BaseWndProperty WindowID="11" WindowHeight="5" WindowWidth="5" />'
        b'<Style ParentNode="1" CtrlType="1" /><BaseWndProperty WindowID="20" WindowHeight="5" WindowWidth="5" />'
        b'</Container_Node></BaseWndProperty>\r\n</Root_Node>\r\n'
    )
    window = EditorWindow()
    window.open_document(path)
    panel, child, other = (
        next(element.index for element in window.document.elements if element.window_id == window_id)
        for window_id in ("10", "11", "20")
    )
    window.toggle_isolation_of(panel)
    assert window.items[panel].isVisible() and window.items[child].isVisible()  # o filho fica junto
    assert not window.items[other].isVisible() and not window.items[0].isVisible()
    window.close()



def test_texture_preview_shows_the_image_and_reloads_when_saved(tmp_path: Path) -> None:
    from gf_ui_editor.atlas_dialog import TexturePreviewDialog

    application = QApplication.instance() or QApplication([])
    texture = tmp_path / "main.dds"
    Image.new("RGBA", (40, 20), (255, 0, 0, 255)).save(texture)
    dialog = TexturePreviewDialog(texture, users=3)
    assert dialog.size_label.text() == "40 × 20 px"
    assert not dialog.view.editable  # só olhar: sem recorte nem alças
    Image.new("RGBA", (64, 32), (0, 0, 255, 255)).save(texture)
    dialog.reload()
    assert dialog.size_label.text() == "64 × 32 px"
    dialog.close()


def test_element_list_hides_parentnode_by_default_and_remembers_column_choice() -> None:
    application = QApplication.instance() or QApplication([])
    window = EditorWindow()
    assert window.tree.isColumnHidden(2) and not window.tree.isColumnHidden(0)
    window._set_tree_column_shown(0, False)
    window._set_tree_column_shown(2, True)
    window.close()
    reopened = EditorWindow()
    assert reopened.tree.isColumnHidden(0) and not reopened.tree.isColumnHidden(2)
    assert reopened.tree.treePosition() == 1
    reopened.close()
