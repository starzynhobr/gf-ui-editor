from pathlib import Path

from gf_ui_editor import game_texts


def test_labels_come_from_the_exe_table_and_the_game_text_index(tmp_path: Path) -> None:
    index = tmp_path / "data" / "Translate" / "T_TextIndex.ini"
    index.parent.mkdir(parents=True)
    index.write_bytes("854|Lista de Membros|\n420|Nome|\n423|Localização|\ncontinuação sem ID\n".encode("cp1252"))

    labels = game_texts.labels_for("Fellowship_family.xml", tmp_path)
    assert labels["13"] == "Lista de Membros"  # FamilyWnd.cpp: WindowID 13 -> TextID 854
    assert labels["4000"] == "Nome"
    assert labels["4600"] == "Localização"
    assert "4100" not in labels  # TextID 421 não está neste T_TextIndex
    assert game_texts.labels_for("Fellowship_family.xml", None) == {}
    assert game_texts.labels_for("NaoExiste.xml", tmp_path) == {}


def test_cpp_files_found_by_window_ids_also_label_their_xml(tmp_path: Path) -> None:
    # FamilyAffairWnd.cpp não carrega o XML pelo nome; o gerador o ligou pelos WindowIDs.
    ids = game_texts.text_ids_for("Fellowship_FamilyAffairs.xml")
    assert ids["4"] == 444  # "Ranques da Guilda"
    assert ids["5"] == 445  # "Poderes - Guilda"


def test_buttons_labelled_through_window_members_keep_the_direct_label_first() -> None:
    ids = game_texts.text_ids_for("Fellowship_family.xml")
    assert ids["5600"] == 9896  # Imposto: SetText no membro ligado ao WindowID 5600
    assert ids["104"] == 441  # aba Social
    assert ids["4600"] == 423  # "Localização" vence o "Tempo offline" que o jogo põe depois
