from pathlib import Path

from gf_ui_editor import text_data
from gf_ui_editor.text_data import TextEdit, TextFile

ITEMS = "538|Pacote Imortal|Abre um pacote.\r\n\r\n$7$'Quando a sorte vem.'|\r\n539|Runa|Uma runa.|\r\n"


def _game(tmp_path: Path, name: str, content: bytes) -> Path:
    folder = tmp_path / "game" / "data" / "Translate"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(content)
    return tmp_path / "game"


def test_records_keep_multiline_fields_and_search_finds_them(tmp_path: Path) -> None:
    game = _game(tmp_path, "T_Item.ini", ITEMS.encode("cp1252"))
    text_file = TextFile.load(game / "data" / "Translate" / "T_Item.ini")
    assert text_file.encoding == "cp1252"  # a página de código do jogo, mesmo num arquivo só ASCII
    assert text_file.by_id["538"].fields == ["Pacote Imortal", "Abre um pacote.\r\n\r\n$7$'Quando a sorte vem.'"]
    assert [record.record_id for record in text_file.find("SORTE")] == ["538"]
    assert text_file.find("539") == []  # o ID não conta como texto
    content, missing = text_data.apply_edits(text_file, {})
    assert content == ITEMS.encode("cp1252") and missing == []


def test_edits_change_only_their_record_and_are_reapplied_on_publish(tmp_path: Path) -> None:
    game = _game(tmp_path, "T_Item.ini", ITEMS.encode("cp1252"))
    project = tmp_path / "project"
    edits = {"T_Item.ini": {"539": TextEdit(["Runa Ação", "Uma runa nova."], ["Runa", "Uma runa."]), "999": TextEdit(["x"], [])}}
    text_data.save_edits(project, edits)
    loaded = text_data.load_edits(project)
    assert loaded["T_Item.ini"]["539"].fields == ["Runa Ação", "Uma runa nova."]

    changed, warnings = text_data.publish_edits(game, loaded, tmp_path / "backup")
    path = game / "data" / "Translate" / "T_Item.ini"
    assert changed == 1 and warnings == ["T_Item.ini #999"]
    assert path.read_bytes() == ITEMS.replace("539|Runa|Uma runa.|", "539|Runa Ação|Uma runa nova.|").encode("cp1252")
    assert (tmp_path / "backup" / "T_Item.ini").read_bytes() == ITEMS.encode("cp1252")
    # O launcher baixou o original de novo: enviar reaplica a edição.
    path.write_bytes(ITEMS.encode("cp1252"))
    assert text_data.publish_edits(game, loaded)[0] == 1
    assert "Runa Ação" in path.read_bytes().decode("cp1252")


def test_only_files_in_use_are_listed(tmp_path: Path) -> None:
    game = _game(tmp_path, "T_Item.ini", b"1|a|\r\n")
    _game(tmp_path, "T_Item.before-algo.ini", b"1|b|\r\n")
    assert [path.name for path in text_data.translate_files(game)] == ["T_Item.ini"]


def test_texts_tab_searches_and_saves_edits_in_the_project(tmp_path: Path, monkeypatch) -> None:
    from PySide6.QtWidgets import QApplication, QDialog

    from gf_ui_editor import texts_panel

    application = QApplication.instance() or QApplication([])
    game = _game(tmp_path, "T_Item.ini", ITEMS.encode("cp1252"))
    project = tmp_path / "project"
    panel = texts_panel.TextsPanel()
    panel.set_context(game, project)
    panel.search_edit.setText("runa")
    panel.refresh_results()
    assert panel.results.topLevelItemCount() == 1
    item = panel.results.topLevelItem(0)
    assert (item.text(1), item.text(2)) == ("T_Item.ini", "539")

    def fake_exec(dialog):
        dialog.editors[0].setPlainText("Runa Brilhante")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(texts_panel.TextEditDialog, "exec", fake_exec)
    panel._open_item(item)
    assert text_data.load_edits(project)["T_Item.ini"]["539"].fields == ["Runa Brilhante", "Uma runa."]
    assert panel.results.topLevelItem(0).text(0).startswith("●")  # marcado como editado
    assert (game / "data" / "Translate" / "T_Item.ini").read_bytes() == ITEMS.encode("cp1252")  # jogo só muda ao enviar
    panel.close()


def test_canvas_labels_show_project_edits_before_they_are_sent(tmp_path: Path) -> None:
    from PySide6.QtWidgets import QApplication

    from gf_ui_editor.app import EditorWindow
    from gf_ui_editor.project import Project

    application = QApplication.instance() or QApplication([])
    game = _game(tmp_path, "T_TextIndex.ini", b"935|message slots remaining.|\r\n")
    source = tmp_path / "source"
    source.mkdir()
    (source / "Fellowship_FamilyAffairs.xml").write_bytes(
        b'<?xml version="1.0" ?>\r\n<Root_Node UI_File_Name="Fellowship_FamilyAffairs.xml">\r\n'
        b'<BaseWndProperty WindowID="1" WindowHeight="300" WindowWidth="200">'
        b'<Container_Node Child_Cnt="1"><Style ParentNode="1" CtrlType="2" />'
        b'<BaseWndProperty WindowID="29" WindowLeft="4" WindowTop="4" WindowHeight="120" WindowWidth="12">'
        b'<BaseCtrlProperty FontColor="16777215" FontStyle="0" /><TextNode TextAlign="0" /></BaseWndProperty>'
        b'</Container_Node></BaseWndProperty>\r\n</Root_Node>\r\n'
    )
    project = Project.create("Textos", source, game, projects_root=tmp_path / "projects")
    window = EditorWindow()
    window.open_project(project.root)
    window.open_document(project.ui_dir / "Fellowship_FamilyAffairs.xml")
    window.set_text_mode("game")
    label = window.items[1].text_item
    assert label.text == "message slots remaining."

    text_data.save_edits(project.root, {"T_TextIndex.ini": {"935": TextEdit(["slots remaining."], ["message slots remaining."])}})
    window.texts_panel.edits_changed.emit()
    assert window.items[1].text_item.text == "slots remaining."  # sem enviar para o jogo
    window.close()
