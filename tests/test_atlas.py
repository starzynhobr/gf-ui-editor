from pathlib import Path

import pytest

from gf_ui_editor import game_texts, storage
from gf_ui_editor.atlas import atlas_edits, atlas_states, crop_between, move_crop, resize_crop
from gf_ui_editor.document_session import DocumentSession
from gf_ui_editor.xml_document import UIDocument, UVRect


BUTTON = """<Root_Node>
<BaseWndProperty WindowID="4004" WindowLeft="5" WindowTop="7" WindowHeight="20" WindowWidth="11">
<BackGroundMap BGmap="Atlas.dds"><NorUV NorUVLeft="1" NorUVTop="2" NorUVWidth="20" NorUVHeight="11"/></BackGroundMap>
<ButtonNode>
<FocusUV FocusUVLeft="1" FocusUVTop="13" FocusUVWidth="20" FocusUVHeight="11"/>
<DownUV DownUVLeft="1" DownUVTop="24" DownUVWidth="20" DownUVHeight="11"/>
</ButtonNode>
</BaseWndProperty>
</Root_Node>"""


def test_atlas_gestures_snap_and_clamp_to_texture_pixels():
    size = (24, 18)
    crop = UVRect(3, 4, 8, 7)
    assert crop_between((23.7, 18.9), (-5, 6.2), size) == UVRect(0, 6, 24, 12)
    assert crop_between((24, 18), (24, 18), size) == UVRect(23, 17, 1, 1)
    assert move_crop(crop, (99, -99), size) == UVRect(16, 0, 8, 7)
    assert resize_crop(crop, "left", (14, 15), size) == UVRect(11, 4, 3, 7)


def test_atlas_edits_existing_states_and_uses_visual_dimensions(tmp_path: Path):
    path = tmp_path / "Storage.xml"
    path.write_text(BUTTON, encoding="ascii")
    document = UIDocument.load(path)
    assert atlas_states(document, 0) == {
        "NorUV": UVRect(1, 2, 20, 11),
        "FocusUV": UVRect(1, 13, 20, 11),
        "DownUV": UVRect(1, 24, 20, 11),
    }
    assert atlas_edits(document, 0, {"NorUV": document.elements[0].uv}, True) == []
    with pytest.raises(ValueError, match="Recorte"):
        atlas_edits(document, 0, {"DisableUV": UVRect(1, 33, 20, 11)}, False)

    session = DocumentSession()
    scene = session.open(path)
    original = scene["elements"][0]["atlas_uvs"]
    edits = session.plan_atlas(str(path), 0, original, {"NorUV": [3, 2, 27, 9], "FocusUV": [4, 13, 20, 11]}, True)
    assert [(edit["field"], edit.get("name")) for edit in edits] == [
        ("uv", "NorUV"), ("uv", "FocusUV"), ("geometry", None),
    ]
    changed = session.edit(edits)["elements"][0]
    assert changed["geometry"] == (5, 7, 27, 9)
    assert changed["button_uvs"]["FocusUV"] == (4, 13, 20, 11)
    assert 'WindowHeight="27" WindowWidth="9"' in session.diff()
    with pytest.raises(ValueError, match="mudou"):
        session.plan_atlas(str(path), 0, original, {"NorUV": [3, 2, 28, 9]}, True)

    # A failed state edit rolls back earlier changes in the same batch.
    inverse = [{**edit, "before": edit["after"], "after": edit["before"]} for edit in reversed(edits)]
    with pytest.raises(ValueError):
        session.edit([*inverse, {**edits[1], "name": "DisableUV"}])
    assert 'WindowHeight="27" WindowWidth="9"' in session.diff()
    assert session.edit(inverse)["elements"][0]["atlas_uvs"] == original
    assert session.diff() == ""


def test_atlas_hides_unwritable_button_states(tmp_path: Path):
    path = tmp_path / "Storage.xml"
    path.write_text(BUTTON, encoding="ascii")
    document = UIDocument.load(path)
    document.button_states_editable = False
    assert atlas_states(document, 0) == {"NorUV": document.elements[0].uv}


def test_refresh_game_texts_preserves_dirty_geometry_and_preview(tmp_path: Path):
    ui = tmp_path / "project" / "ui"
    ui.mkdir(parents=True)
    game = tmp_path / "game"
    index = game / game_texts.TEXT_INDEX
    index.parent.mkdir(parents=True)
    text_id = game_texts.text_ids_for("Storage.xml")["4004"]
    index.write_text(f"{text_id}|Original|\n", encoding="ascii")
    path = ui / "Storage.xml"
    path.write_text(BUTTON, encoding="ascii")
    store = storage.ProjectStore(ui.parent)
    store.save_settings({"game_dir": str(game)}, {}, [])
    session = DocumentSession()
    scene = session.open(str(path), (1200, 900))
    assert scene["elements"][0]["texts"]["game"] == {"value": "Original"}
    moved = session.edit([
        {"index": 0, "field": "geometry", "before": [5, 7, 20, 11], "after": [15, 7, 20, 11]},
    ])
    diff = session.diff()
    store.replace_text_edits({"T_TextIndex.ini": {str(text_id): (["Edited label"], ["Original"])}})
    assert session.refresh_texts(str(tmp_path / "other")) is None
    refreshed = session.refresh_texts(str(ui.parent))
    assert refreshed["elements"][0]["texts"]["game"] == {"value": "Edited label"}
    assert refreshed["elements"][0]["geometry"] == (15, 7, 20, 11)
    assert refreshed["preview"] == moved["preview"]
    assert refreshed["dirty"] and session.diff() == diff
    assert path.read_text(encoding="ascii") == BUTTON
