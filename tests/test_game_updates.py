import zlib
from pathlib import Path

from gf_ui_editor.game_updates import (
    copy_official_file,
    control_info,
    error_candidates,
    insert_controls,
    missing_controls,
    parse_game_error,
    scan,
    snapshot_official_ui,
)

OFFICIAL_OLD = (
    '<?xml version="1.0" ?>\r\n<Root_Node UI_File_Name="T.xml">\r\n'
    '\t<BaseWndProperty WindowID="1">\r\n\t\t<Container_Node Child_Cnt="3">\r\n'
    '\t\t\t<Style CtrlType="1" />\r\n\t\t\t<BaseWndProperty WindowID="2" />\r\n'
    '\t\t\t<Style CtrlType="1" />\r\n\t\t\t<BaseWndProperty WindowID="4" />\r\n'
    '\t\t\t<Style CtrlType="1" />\r\n\t\t\t<BaseWndProperty WindowID="8301" />\r\n'
    '\t\t</Container_Node>\r\n\t</BaseWndProperty>\r\n</Root_Node>\r\n'
)
# A atualização trouxe o 5130.
OFFICIAL = OFFICIAL_OLD.replace('Child_Cnt="3"', 'Child_Cnt="4"').replace(
    '\t\t\t<Style CtrlType="1" />\r\n\t\t\t<BaseWndProperty WindowID="4" />',
    '\t\t\t<Style ParentNode="1" CtrlType="268435456" />\r\n\t\t\t<BaseWndProperty WindowID="5130" WindowLeft="9" WindowTop="3" WindowHeight="20" WindowWidth="8">\r\n'
    '\t\t\t\t<BackGroundMap BGmap="main.dds" />\r\n\t\t\t</BaseWndProperty>\r\n'
    '\t\t\t<Style CtrlType="1" />\r\n\t\t\t<BaseWndProperty WindowID="4" />',
)
# UI custom de antes da atualização: removeu o 8301 de propósito e mudou o 4.
CUSTOM = (
    '<?xml version="1.0" ?>\r\n<Root_Node UI_File_Name="T.xml">\r\n'
    '\t<BaseWndProperty WindowID="1">\r\n\t\t<Container_Node Child_Cnt="2">\r\n'
    '\t\t\t<Style CtrlType="1" />\r\n\t\t\t<BaseWndProperty WindowID="2" />\r\n'
    '\t\t\t<Style CtrlType="1" />\r\n\t\t\t<BaseWndProperty WindowID="4" WindowLeft="77" />\r\n'
    '\t\t</Container_Node>\r\n\t</BaseWndProperty>\r\n</Root_Node>\r\n'
)


def _write_official(game: Path, text: str, extra: bytes | None = None) -> None:
    official = text.encode("big5")
    (game / "UI").mkdir(parents=True, exist_ok=True)
    (game / "UI" / "T.xml").write_bytes(official)
    lines = ["GrandFantasia.exe|1|00000000|1|0|", f"UI\\T.xml|{len(official)}|{zlib.crc32(official):08X}|1|0|"]
    if extra is not None:
        (game / "UI" / "Novo.xml").write_bytes(extra)
        lines.append(f"UI\\Novo.xml|{len(extra)}|{zlib.crc32(extra):08X}|1|0|")
    (game / "GameDataFileList.txt").write_text("\n".join(lines) + "\n", encoding="latin-1")


def test_selected_controls_are_inserted_in_official_order_keeping_custom_edits() -> None:
    assert missing_controls(CUSTOM, OFFICIAL) == ["5130", "8301"]
    text, inserted = insert_controls(CUSTOM, OFFICIAL, {"5130"})
    assert inserted == ["5130"]
    assert 'Child_Cnt="3"' in text
    assert 'WindowID="4" WindowLeft="77"' in text  # edição da UI custom intacta
    assert 'WindowID="8301"' not in text  # não marcado, continua de fora
    assert text.index('WindowID="2"') < text.index('WindowID="5130"') < text.index('WindowID="4"')
    assert "\n" not in text.replace("\r\n", "")  # mantém as quebras CRLF do arquivo
    assert missing_controls(text, OFFICIAL) == ["8301"]


def test_only_ids_added_between_official_versions_count_as_new(tmp_path: Path) -> None:
    game = tmp_path / "game"
    ui = tmp_path / "project" / "ui"
    ui.mkdir(parents=True)
    (ui / "T.xml").write_bytes(CUSTOM.encode("big5"))

    _write_official(game, OFFICIAL_OLD)
    assert snapshot_official_ui(game) == (1, 1)  # editor viu a versão antiga
    _write_official(game, OFFICIAL, extra=b"<Root_Node />")  # o jogo atualizou
    snapshot_official_ui(game)
    (game / "UI" / "T.xml").write_bytes(CUSTOM.encode("big5"))  # launcher aplicou a UI custom

    diffs, unavailable = scan(game, ui)
    assert unavailable == 0
    assert diffs["t.xml"].new_ids == ["5130"]
    assert diffs["t.xml"].other_ids == ["8301"]  # removido de propósito: não é "novo"
    assert diffs["novo.xml"].missing_file

    info = control_info(OFFICIAL, ["5130"])["5130"]
    assert (info.kind, info.texture, info.position) == ("panel", "main.dds", (9, 3))

    copy_official_file(game, ui, "Novo.xml")
    assert (ui / "Novo.xml").read_bytes() == b"<Root_Node />"


def test_without_history_nothing_is_marked_new_unless_the_project_started_from_official(tmp_path: Path) -> None:
    game = tmp_path / "game"
    ui = tmp_path / "ui"
    ui.mkdir()
    _write_official(game, OFFICIAL)
    (ui / "T.xml").write_bytes(CUSTOM.encode("big5"))

    diffs, _ = scan(game, ui)
    assert diffs["t.xml"].new_ids == [] and diffs["t.xml"].other_ids == ["5130", "8301"]

    # O projeto partiu da UI oficial antiga, já guardada no cache.
    old = OFFICIAL_OLD.encode("big5")
    (tmp_path / "old").mkdir()
    old_game = tmp_path / "old"
    _write_official(old_game, OFFICIAL_OLD)
    snapshot_official_ui(old_game)
    diffs, _ = scan(game, ui, base_bytes=lambda relative: old)
    assert diffs["t.xml"].new_ids == ["5130"]


def test_game_error_points_to_the_xml_that_has_the_id(tmp_path: Path) -> None:
    assert parse_game_error("FILE: ..\\FrameWnd.cpp (663)\n..\\MiniInfo.cpp ERROR: ID=8301 Child control can not found!") == (
        "MiniInfo.cpp",
        "8301",
    )
    assert parse_game_error("nada aqui") is None
    game = tmp_path / "game"
    official = OFFICIAL.replace("T.xml", "BasicChar.xml").encode("big5")
    (game / "UI").mkdir(parents=True)
    (game / "UI" / "BasicChar.xml").write_bytes(official)
    (game / "GameDataFileList.txt").write_text(
        f"UI\\BasicChar.xml|{len(official)}|{zlib.crc32(official):08X}|1|0|\n", encoding="latin-1"
    )
    assert error_candidates(game, "miniinfo.cpp", "8301") == ["BasicChar.xml"]
    # Radar.xml e Target.xml (também do MiniInfo.cpp) não têm cópia oficial aqui: ficam como opção.
    assert error_candidates(game, "MiniInfo.cpp", "99999") == ["Radar.xml", "Target.xml"]


def test_reference_is_ready_once_most_official_files_are_cached(tmp_path: Path) -> None:
    from gf_ui_editor.game_updates import cached_count, reference_ready

    game = tmp_path / "game"
    _write_official(game, OFFICIAL)
    (game / "UI" / "T.xml").write_bytes(CUSTOM.encode("big5"))  # pasta UI com a UI custom
    snapshot_official_ui(game)
    assert cached_count(game) == (0, 1) and not reference_ready(game)
    _write_official(game, OFFICIAL)  # launcher restaurou a UI Padrão
    snapshot_official_ui(game)
    assert cached_count(game) == (1, 1) and reference_ready(game)


def test_known_update_ids_are_new_and_unknown_cpp_errors_search_by_id(tmp_path: Path) -> None:
    from gf_ui_editor.game_updates import files_missing_id

    game = tmp_path / "game"
    official = OFFICIAL.replace("T.xml", "BasicChar.xml").encode("big5")
    (game / "UI").mkdir(parents=True)
    (game / "UI" / "BasicChar.xml").write_bytes(official)
    (game / "GameDataFileList.txt").write_text(
        f"UI\\BasicChar.xml|{len(official)}|{zlib.crc32(official):08X}|1|0|\n", encoding="latin-1"
    )
    ui = tmp_path / "ui"
    ui.mkdir()
    (ui / "BasicChar.xml").write_bytes(CUSTOM.encode("big5"))
    diffs, _ = scan(game, ui)
    assert diffs["basicchar.xml"].new_ids == ["5130"]  # conhecido da atualização de 24/10/2026
    assert diffs["basicchar.xml"].other_ids == ["8301"]
    assert files_missing_id(game, ui, "5130") == ["BasicChar.xml"]
    assert files_missing_id(game, ui, "2") == []
