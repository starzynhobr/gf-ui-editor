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
    assert window.tree_items[1].text(1) == "Texto · message slots remaining." or window.tree_items[1].text(1).endswith("· message slots remaining.")

    text_data.save_edits(project.root, {"T_TextIndex.ini": {"935": TextEdit(["slots remaining."], ["message slots remaining."])}})
    window.texts_panel.edits_changed.emit()
    assert window.items[1].text_item.text == "slots remaining."  # sem enviar para o jogo
    assert window.tree_items[1].text(1).endswith("· slots remaining.")  # a lista também
    window.close()


def test_restore_brings_back_the_original_even_after_it_was_sent(tmp_path: Path, monkeypatch) -> None:
    from PySide6.QtWidgets import QApplication, QDialog

    from gf_ui_editor import texts_panel

    application = QApplication.instance() or QApplication([])
    # O jogo já recebeu a edição; o original só existe no backup do envio.
    game = _game(tmp_path, "T_TextIndex.ini", b"935|slots remaining.|\r\n")
    project = tmp_path / "project"
    backup = project / ".history" / "data" / "20261026-111316"
    backup.mkdir(parents=True)
    (backup / "T_TextIndex.ini").write_bytes(b"935|message slots remaining.|\r\n")
    panel = texts_panel.TextsPanel()
    panel.set_context(game, project)
    panel.search_edit.setText("slots")
    panel.refresh_results()

    def restore(dialog):
        dialog._restore()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(texts_panel.TextEditDialog, "exec", restore)
    panel._open_item(panel.results.topLevelItem(0))
    edits = text_data.load_edits(project)["T_TextIndex.ini"]
    assert edits["935"].fields == ["message slots remaining."]  # fica guardado para o próximo envio
    changed, _warnings = text_data.publish_edits(game, {"T_TextIndex.ini": edits})
    assert changed == 1
    assert (game / "data" / "Translate" / "T_TextIndex.ini").read_bytes() == b"935|message slots remaining.|\r\n"
    panel.close()


def test_empty_search_lists_texts_changed_in_the_project_including_already_sent(tmp_path: Path) -> None:
    from PySide6.QtWidgets import QApplication

    from gf_ui_editor import texts_panel

    application = QApplication.instance() or QApplication([])
    game = _game(tmp_path, "T_TextIndex.ini", b"934|There are|\r\n935|slots remaining.|\r\n")
    project = tmp_path / "project"
    backup = project / ".history" / "data" / "20261026-111316"
    backup.mkdir(parents=True)
    (backup / "T_TextIndex.ini").write_bytes(b"934|There are|\r\n935|message slots remaining.|\r\n")
    panel = texts_panel.TextsPanel()
    panel.set_context(game, project)  # sem busca, sem edição guardada
    assert panel.results.topLevelItemCount() == 1
    item = panel.results.topLevelItem(0)
    assert item.text(2) == "935" and item.text(0).startswith("◐")
    panel.close()


def test_text_mode_is_remembered_and_lights_up_the_bar_button() -> None:
    from PySide6.QtWidgets import QApplication

    from gf_ui_editor.app import EditorWindow

    application = QApplication.instance() or QApplication([])
    window = EditorWindow()
    assert window.text_mode == "off" and not window.text_mode_button.isChecked()
    window.set_text_mode("game")
    assert window.text_mode_button.isChecked()
    window.close()
    reopened = EditorWindow()
    assert reopened.text_mode == "game" and reopened.text_mode_button.isChecked()
    assert [action.data() for action in reopened.text_mode_actions.actions() if action.isChecked()] == ["game"]
    reopened.close()


def test_import_takes_changed_texts_by_id_and_keeps_new_game_ids(tmp_path: Path) -> None:
    # O jogo atualizou: trouxe o ID 60030, que o arquivo antigo do jogador não tem.
    game = _game(tmp_path, "T_Npc.ini", b"60020|Mysterious Man|\r\n60021|Sprite\r\nCyerfu|\r\n60030|New NPC|\r\n")
    old = tmp_path / "old" / "data" / "Translate"
    old.mkdir(parents=True)
    # Salvo pelo Bloco de Notas: LF e UTF-8; um ID que o jogo removeu; um arquivo que o jogo não tem.
    (old / "T_Npc.ini").write_bytes("60020|Homem Misterioso|\n60021|Sprite\nCyerfu|\n60099|Sumiu|\n".encode("utf-8"))
    (old / "T_Extra.ini").write_bytes(b"1|x|\r\n")
    plan = text_data.plan_text_import(tmp_path / "old", game, {})
    assert plan.count == 1 and plan.missing_ids == 1 and plan.unknown_files == ["T_Extra.ini"]
    assert plan.edits["T_Npc.ini"]["60020"].fields == ["Homem Misterioso"]
    assert plan.edits["T_Npc.ini"]["60020"].original == ["Mysterious Man"]  # quebras de linha não contam como diferença

    changed, _warnings = text_data.publish_edits(game, plan.edits)
    assert changed == 1
    content = (game / "data" / "Translate" / "T_Npc.ini").read_bytes()
    assert content == "60020|Homem Misterioso|\r\n60021|Sprite\r\nCyerfu|\r\n60030|New NPC|\r\n".encode("cp1252")


def test_import_skips_texts_the_game_already_has_and_keeps_edit_originals(tmp_path: Path) -> None:
    # T_Npc mistura CRLF entre registros e LF dentro do nome.
    game = _game(tmp_path, "T_Npc.ini", b"60021|Sprite\nCyerfu|\r\n60022|Hunter\nLeis|\r\n")
    source = tmp_path / "old"
    source.mkdir()
    (source / "T_Npc.ini").write_bytes(b"60021|Sprite\r\nCyerfu|\r\n60022|Ca\xe7ador\r\nLeis|\r\n")
    edits = {"T_Npc.ini": {"60022": TextEdit(["Ranger\nLeis"], ["Hunter\nLeis"])}}
    plan = text_data.plan_text_import(source, game, edits)
    assert plan.count == 1 and plan.replaced == 1  # 60021 já está assim no jogo
    assert plan.edits["T_Npc.ini"]["60022"] == TextEdit(["Caçador\nLeis"], ["Hunter\nLeis"])  # LF como no jogo
    # Importar de novo o que já está guardado não muda nada.
    assert text_data.plan_text_import(source, game, plan.edits).count == 0


def test_texts_tab_imports_after_confirmation(tmp_path: Path, monkeypatch) -> None:
    from PySide6.QtWidgets import QApplication, QMessageBox

    from gf_ui_editor import texts_panel

    application = QApplication.instance() or QApplication([])
    game = _game(tmp_path, "T_Item.ini", ITEMS.encode("cp1252"))
    source = tmp_path / "old"
    source.mkdir()
    (source / "T_Item.ini").write_bytes(ITEMS.replace("539|Runa|", "539|Runa Velha|").encode("cp1252"))
    project = tmp_path / "project"
    panel = texts_panel.TextsPanel()
    panel.set_context(game, project)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    panel.import_texts(source)
    assert text_data.load_edits(project)["T_Item.ini"]["539"].fields == ["Runa Velha", "Uma runa."]
    assert panel.results.topLevelItemCount() == 1 and panel.results.topLevelItem(0).text(0).startswith("●")
    panel.close()


def test_texts_changed_by_a_game_update_after_editing_are_flagged(tmp_path: Path) -> None:
    from PySide6.QtWidgets import QApplication

    from gf_ui_editor import texts_panel

    application = QApplication.instance() or QApplication([])
    # A atualização trocou o original ("Runa") por "Runa Antiga"; a edição era "Runa Nova".
    game = _game(tmp_path, "T_Item.ini", b"539|Runa Antiga|Uma runa.|\r\n540|Pedra|Uma pedra.|\r\n")
    project = tmp_path / "project"
    text_data.save_edits(project, {"T_Item.ini": {
        "539": TextEdit(["Runa Nova", "Uma runa."], ["Runa", "Uma runa."]),
        "540": TextEdit(["Pedra Nova", "Uma pedra."], ["Pedra", "Uma pedra."]),
    }})
    panel = texts_panel.TextsPanel()
    panel.set_context(game, project)
    marks = {panel.results.topLevelItem(i).text(2): panel.results.topLevelItem(i).text(0)[0] for i in range(panel.results.topLevelItemCount())}
    assert marks == {"539": "⚠", "540": "●"}
    assert "⚠ 1" in panel.summary.text()
    panel.close()
