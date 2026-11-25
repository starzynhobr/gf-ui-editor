import json
from pathlib import Path
import sqlite3

from gf_ui_editor import game_texts, storage
from gf_ui_editor.canvas_document import describe_document


def test_canvas_uses_classic_geometry_and_preserves_inspector_metadata(tmp_path: Path):
    path = tmp_path / "Menu.xml"
    path.write_text(
        """<Root_Node UI_File_Name="Menu.xml">
        <BaseWndProperty WindowID="2000" WindowLeft="10" WindowTop="20" WindowHeight="100" WindowWidth="50">
        <Container_Node Child_Cnt="4">
        <Style CtrlType="Slot" ParentNode="2000"/>
        <BaseWndProperty WindowID="2013" WindowLeft="11" WindowTop="70" WindowHeight="25" WindowWidth="12"
                         Visible="0" WindowText="Label">
        <BackGroundMap BGmap="Test.dds"><NorUV NorUVLeft="1" NorUVTop="2" NorUVWidth="8" NorUVHeight="9"/></BackGroundMap>
        <ButtonNode><FocusUV FocusUVLeft="7" FocusUVTop="8" FocusUVWidth="9" FocusUVHeight="10"/></ButtonNode>
        </BaseWndProperty>
        <BaseWndProperty WindowID="2014" WindowHeight="5" WindowWidth="5"><TextNode TextAlign="2"/></BaseWndProperty>
        <BaseWndProperty WindowID="2015" WindowLeft="90000" WindowHeight="20" WindowWidth="20"/>
        <BaseWndProperty WindowID="2016" WindowLeft="5" WindowTop="74" WindowHeight="4" WindowWidth="4"><SlotNode/></BaseWndProperty>
        </Container_Node>
        </BaseWndProperty>
        </Root_Node>""",
        encoding="ascii",
    )
    scene = json.loads(json.dumps(describe_document(path, (800, 600))))
    root, button, text, _, slot = scene["elements"]
    assert root["geometry"] == [10, 20, 100, 50]
    assert button["geometry"] == [11, 70, 25, 12]
    assert button["texture"] == "Test.dds"
    assert button["uv"] == [1, 2, 8, 9]
    assert button["button_uvs"] == {"FocusUV": [7, 8, 9, 10]}
    assert not button["visible"]
    assert button["texts"] == {
        "off": {"value": ""}, "game": {"value": "Label"}, "xml": {"value": "Label"},
        "short": {"value": "Label"}, "long": {"value": "Label"},
    }
    assert text["texts"]["short"] == {"sample": "short"}
    assert text["texts"]["long"] == {"sample": "long"}
    assert text["text_props"]["TextAlign"] == "2"
    assert scene["bounds"] == [0, 0, 110, 82]
    preview = scene["preview"]
    assert preview["screen"] == [-340, -530, 800, 600]
    assert preview["frame"] == root["geometry"]
    assert preview["content"] == [0, 0, 90020, 82]
    assert button["parent"] == "2000"
    assert preview["offsets"][1] == [0, 0]
    assert preview["offsets"][slot["index"]] == [0, -33]


def test_project_preview_reads_game_and_overrides_without_opening_a_writer(tmp_path: Path):
    ui = tmp_path / "project" / "ui"
    ui.mkdir(parents=True)
    game = tmp_path / "game"
    game.mkdir()
    (game / "client.ini").write_text("[Option]\nScreenWidth=1280\nScreenHeight=720\n", encoding="ascii")
    window_id, text_id = next(iter(game_texts.text_ids_for("Storage.xml").items()))
    path = ui / "Storage.xml"
    path.write_text(
        f'<Root_Node><BaseWndProperty WindowID="{window_id}" WindowHeight="100" WindowWidth="80"/></Root_Node>',
        encoding="ascii",
    )
    db = ui.parent / storage.PROJECT_DB
    connection = sqlite3.connect(db)
    with connection:
        connection.executescript(storage.PROJECT_MIGRATIONS[0])
        connection.execute("INSERT INTO settings VALUES ('game_dir', ?)", (json.dumps(str(game)),))
        connection.execute("INSERT INTO root_modes VALUES ('Storage.xml', 'xml')")
        connection.execute(
            "INSERT INTO text_edits (file, record_id, fields, original) VALUES ('T_TextIndex.ini', ?, ?, '[]')",
            (str(text_id), '["Project label"]'),
        )
    connection.close()
    before = db.read_bytes()
    scene = describe_document(path)
    assert scene["elements"][0]["texts"]["game"] == {"value": "Project label"}
    assert scene["preview"]["screen"] == (0, 0, 1280, 720)
    assert db.read_bytes() == before
    assert not db.with_name(db.name + "-wal").exists()


def test_empty_document_has_a_screen_and_no_controls(tmp_path: Path):
    path = tmp_path / "Empty.xml"
    path.write_text("<Root_Node/>", encoding="ascii")
    scene = describe_document(path, (800, 600))
    assert scene["elements"] == []
    assert scene["bounds"] == (0, 0, 800, 600)
    assert scene["preview"]["screen"] == scene["bounds"]
