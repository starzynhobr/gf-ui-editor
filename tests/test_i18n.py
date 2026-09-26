from __future__ import annotations

import os
from pathlib import Path
from string import Formatter
import xml.etree.ElementTree as ET

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from gf_ui_editor.app import EditorWindow
from gf_ui_editor.i18n import LANGUAGE_NAMES, LANGUAGES, document_error_text, install_language, kind_label
from gf_ui_editor.xml_document import DocumentError, UIDocument


def test_english_catalog_localizes_ui_without_changing_xml_model(tmp_path: Path) -> None:
    application = QApplication.instance() or QApplication([])
    translator = install_language(application, "en_US")
    try:
        window = EditorWindow(language="en_US")
        assert [action.text() for action in window.menuBar().actions()] == [
            "File", "Edit", "View", "Help"
        ]
        assert window.language_button.text() == "Language"
        assert window.menuBar().cornerWidget() is window.language_button
        language_menu = window.language_button.menu()
        assert [action.text() for action in language_menu.actions() if action.isChecked()] == ["English"]
        assert [action.text() for action in language_menu.actions()] == [
            label for _code, label in LANGUAGE_NAMES
        ]
        assert [action.text() for action in window.menuBar().actions()[-1].menu().actions()] == [
            "About GF UI Editor…"
        ]
        assert window.open_action.text() == "Open XML…"
        assert window.properties.selection_title.text() == "No element selected"

        path = tmp_path / "Example.xml"
        path.write_bytes(
            b'<Root_Node><BaseWndProperty WindowID="1" WindowHeight="8" '
            b'WindowWidth="8"><PictureNode /></BaseWndProperty></Root_Node>'
        )
        document = UIDocument.load(path)
        assert document.elements[0].kind == "image"
        assert kind_label(document.elements[0].kind) == "Image"
        window.open_document(path)
        assert window.tree.headerItem().text(1) == "Type"
        assert window.tree.topLevelItem(0).text(1) == "Image"
        window.select_element(0)
        assert window.properties.kind_value.text() == "Image"
        window.search_edit.setText("image")
        assert not window.tree.topLevelItem(0).isHidden()
        assert path.read_bytes() == document.raw

        error = DocumentError("XML inválido", code="invalid_xml", details={"error": "bad tag"})
        assert document_error_text(error) == "Invalid XML: bad tag"
        window.deleteLater()
    finally:
        application.removeTranslator(translator)


@pytest.mark.parametrize(
    ("language", "file_label", "button_label", "image_label"),
    [
        ("es_ES", "Archivo", "Idioma", "Imagen"),
        ("fr_FR", "Fichier", "Langue", "Image"),
    ],
)
def test_additional_languages_translate_interface(
    language: str, file_label: str, button_label: str, image_label: str
) -> None:
    application = QApplication.instance() or QApplication([])
    translator = install_language(application, language)
    try:
        window = EditorWindow(language=language)
        assert window.menuBar().actions()[0].text() == file_label
        assert window.language_button.text() == button_label
        assert [action.text() for action in window.language_button.menu().actions() if action.isChecked()] == [
            dict(LANGUAGE_NAMES)[language]
        ]
        assert kind_label("image") == image_label
        window.close()
    finally:
        application.removeTranslator(translator)


def test_all_translation_catalogs_are_complete_and_preserve_format_parameters() -> None:
    catalog_dir = Path(__file__).resolve().parents[1] / "src/gf_ui_editor/translations"
    reference = ET.parse(catalog_dir / "gf_ui_editor_en_US.ts").getroot()
    reference_messages = {
        (context.findtext("name"), message.findtext("source"))
        for context in reference.findall("context")
        for message in context.findall("message")
    }
    fields = Formatter()
    for language in LANGUAGES:
        if language == "pt_BR":
            continue
        root = ET.parse(catalog_dir / f"gf_ui_editor_{language}.ts").getroot()
        assert root.attrib["language"] == language
        messages = {
            (context.findtext("name"), message.findtext("source"))
            for context in root.findall("context")
            for message in context.findall("message")
        }
        assert messages == reference_messages, language
        for message in root.iter("message"):
            source = message.findtext("source") or ""
            translation_node = message.find("translation")
            assert translation_node is not None
            assert translation_node.attrib.get("type") != "unfinished", (language, source)
            translation = translation_node.text or ""
            assert translation.strip(), (language, source)
            source_fields = {name for _, name, _, _ in fields.parse(source) if name}
            translated_fields = {name for _, name, _, _ in fields.parse(translation) if name}
            assert source_fields == translated_fields, (language, source)
