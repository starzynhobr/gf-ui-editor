from pathlib import Path

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from gf_ui_editor.app import EditorWindow


@pytest.mark.parametrize("preview", [True, False])
def test_distant_controls_do_not_shrink_initial_view(tmp_path: Path, preview: bool) -> None:
    application = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    # EditorWindow uses this factory; no real user preferences are changed.
    from unittest.mock import patch

    path = tmp_path / "Target.xml"
    raw = b'''<Root_Node UI_File_Name="Target.xml">
    <BaseWndProperty WindowID="1" WindowHeight="387" WindowWidth="78">
    <Container_Node Child_Cnt="2">
    <BaseWndProperty WindowID="2" WindowLeft="96" WindowTop="39" WindowHeight="278" WindowWidth="9"/>
    <BaseWndProperty WindowID="1020" WindowLeft="59954985" WindowTop="32" WindowHeight="160" WindowWidth="16"/>
    </Container_Node></BaseWndProperty></Root_Node>'''
    path.write_bytes(raw)
    with patch("gf_ui_editor.app.QSettings", return_value=settings):
        window = EditorWindow()
        window.game_resolution = (800, 600) if preview else None
        window.resize(1500, 900)
        window.show()
        application.processEvents()
        window.open_document(path)
        application.processEvents()
        try:
            assert window.view.transform().m11() > 0.25
            assert window.document is not None
            assert window.document.elements[2].x == 59954985
            assert not window.document.is_dirty
            assert path.read_bytes() == raw

            # Selecting a far-away control from the tree must still reveal it.
            zoom = window.view.transform().m11()
            window.select_element(2)
            application.processEvents()
            viewport = window.view.mapToScene(window.view.viewport().rect()).boundingRect()
            assert viewport.contains(window.items[2].sceneBoundingRect().center())
            assert window.view.transform().m11() == zoom

            # Fit returns to the normal editing area even with that selection.
            window.fit_scene()
            application.processEvents()
            viewport = window.view.mapToScene(window.view.viewport().rect()).boundingRect()
            assert viewport.contains(window.items[1].sceneBoundingRect().center())
            assert window.view.transform().m11() > 0.25
        finally:
            window.close()
            window.deleteLater()
