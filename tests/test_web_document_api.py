from pathlib import Path
from struct import pack

import pytest

from gf_ui_editor import game_layout, project, xml_watch
from gf_ui_editor.preferences import Preferences
from gf_ui_editor.web_shell import WebApi
from gf_ui_editor.xml_document import ExternalModificationError, UIDocument


XML = b'''<Root_Node>
  <BaseWndProperty WindowID="1" WindowLeft="10" WindowTop="20" WindowHeight="100" WindowWidth="80">
    <Container_Node Child_Cnt="1">
      <BaseWndProperty WindowID="2" WindowLeft="20" WindowTop="30" WindowHeight="15" WindowWidth="12">
        <BackGroundMap BGmap="A.dds"><NorUV NorUVLeft="1" NorUVTop="2" NorUVWidth="8" NorUVHeight="9"/></BackGroundMap>
        <BaseCtrlProperty FontColor="11"/>
      </BaseWndProperty>
    </Container_Node>
  </BaseWndProperty>
</Root_Node>
'''


@pytest.fixture
def api():
    return WebApi("pt_BR", False)


def write_xml(path: Path):
    path.write_bytes(XML)
    return path


def geometry(index, before, after):
    return {"index": index, "field": "geometry", "before": list(before), "after": list(after)}


def test_canvas_preview_preferences_keep_the_dirty_document(api, tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    (game / "client.ini").write_text("[Option]\nScreenWidth=1280\nScreenHeight=720\n", encoding="ascii")
    position = "".join(chr(65 + digit) for byte in pack("<4i", 200, 240, 100, 80) for digit in (byte & 15, byte >> 4))
    (game / "User.ini").write_text(f"[INVENTORY]\nPosition={position}\n", encoding="ascii")
    source = tmp_path / "source"
    source.mkdir()
    write_xml(source / "Inventory.xml")
    active = project.create_from_source("Web", source, game, projects_root=tmp_path / "projects")
    path = str(active.ui_dir / "Inventory.xml")
    scene = api.doc_open(path)
    assert scene["preview"]["screen"][2:] == (1280, 720)
    assert scene["preview"]["root_on_screen"] == (200, 240)
    api.doc_edit([geometry(1, scene["elements"][1]["geometry"], (43, 30, 15, 12))])
    diff = api.doc_diff()

    changed = api.canvas_set_preference(path, "resolution", "1367 × 769")
    assert changed["doc"]["preview"]["screen"][2:] == (1367, 769)
    assert changed["preferences"]["resolution"] == "1367x769"
    changed = api.canvas_set_preference(path, "savedPositions", False)
    assert changed["doc"]["preview"]["root_on_screen"] == game_layout.root_screen_position(
        "Inventory.xml", (1367, 769), scene["elements"][0]["geometry"],
    )
    assert not changed["doc"]["preview"]["saved_positions"]
    assert changed["doc"]["dirty"] and api.doc_diff() == diff
    with pytest.raises(ValueError, match="largura x altura"):
        api.canvas_set_preference(path, "resolution", "x")
    assert api.canvas_preferences()["resolution"] == "1367x769"
    assert Path(path).read_bytes() == XML

    api.canvas_set_preference(path, "outlines", False)
    api.canvas_set_preference(path, "ids", True)
    reopened_api = WebApi("pt_BR", False, Preferences(api._prefs.store))
    assert not reopened_api.canvas_preferences()["outlines"]
    assert reopened_api.canvas_preferences()["ids"]
    assert reopened_api.canvas_preferences()["navigation"] == "corel"
    reopened_api._prefs.navigation_style = "paintnet"
    assert reopened_api.canvas_preferences()["navigation"] == "paintnet"
    reopened = reopened_api.doc_open(path)
    assert reopened["preview"]["screen"][2:] == (1367, 769)
    assert not reopened["preview"]["saved_positions"]


def test_canvas_reference_layers_share_the_project_file_list(api, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    for name in ("Plain.xml", "BasicChar.xml", "Radar.xml"):
        write_xml(source / name)
    active = project.create_from_source("Web", source, None, projects_root=tmp_path / "projects")
    api._project = active
    api.asset_base = lambda _path: "https://assets.test/"
    path = str(active.ui_dir / "BasicChar.xml")
    api.canvas_change_layers(path, "default")
    api.canvas_change_layers(path, "add", "Plain.xml")
    layers = api.canvas_layers(path, [1024, 768])
    assert layers["names"] == ["BasicChar.xml", "Radar.xml", "Plain.xml"]
    assert [layer["name"] for layer in layers["scenes"]] == ["Radar.xml", "Plain.xml"]
    assert layers["scenes"][0]["scene"]["preview"]["root_on_screen"] == (924, 0)
    files = api.file_list()
    section = next(section for section in files["sections"] if section["kind"] == "layers")
    assert {files["files"][index] for index in section["items"]} == set(layers["names"])
    assert api.canvas_layers(path)["scenes"] == []
    api.canvas_change_layers(path, "clear")
    assert api.canvas_layers(path)["names"] == []


def test_edit_is_atomic_and_in_memory(api, tmp_path):
    path = write_xml(tmp_path / "Plain.xml")
    scene = api.doc_open(str(path))
    assert scene == api.open_document(str(path))
    before = scene["elements"][1]["geometry"]
    move = geometry(1, before, (27, 33, 15, 12))
    with pytest.raises(ValueError, match="mudou"):
        api.doc_edit([move, move])
    assert api.doc_diff() == ""
    changes = [
        move,
        {"index": 1, "field": "uv", "before": [1, 2, 8, 9], "after": [2, 4, 9, 10]},
        {"index": 1, "field": "texture", "before": "A.dds", "after": "B.dds"},
        {"index": 1, "field": "font", "name": "FontColor", "before": "11", "after": "22"},
    ]
    changed = api.doc_edit(changes)
    assert changed["dirty"]
    element = changed["elements"][1]
    assert element["geometry"] == (27, 33, 15, 12)
    assert element["uv"] == (2, 4, 9, 10)
    assert element["texture"] == "B.dds"
    assert element["text_props"]["FontColor"] == "22"
    assert "B.dds" in api.doc_diff()
    assert path.read_bytes() == XML
    inverses = [{**edit, "after": edit["before"], "before": edit["after"]} for edit in reversed(changes)]
    assert api.doc_edit(inverses) == scene
    assert api.doc_diff() == ""


def test_save_uses_project_history_and_refreshes_changed_files(api, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    write_xml(source / "Plain.xml")
    active = project.create_from_source("Web", source, None, projects_root=tmp_path / "projects")
    api._project = active
    path = active.ui_dir / "Plain.xml"
    scene = api.doc_open(str(path))
    before = scene["elements"][1]["geometry"]
    active.changes_ttl = 60
    assert not active.modified_files()
    api.doc_edit([geometry(1, before, (36, 31, 15, 12))])
    assert not api.doc_save()["dirty"]
    assert api.doc_diff() == ""
    assert [item.read_bytes() for item in active.history(path)] == [XML]
    assert UIDocument.load(path).elements[1].geometry == (36, 31, 15, 12)
    assert active.modified_files() == {"Plain.xml"}
    assert api.doc_watch(str(path)) is None


def test_external_conflict_keeps_pending_edits_and_revert_refreshes(api, tmp_path):
    path = write_xml(tmp_path / "Plain.xml")
    scene = api.doc_open(str(path))
    before = scene["elements"][1]["geometry"]
    api.doc_edit([geometry(1, before, (42, 31, 15, 12))])
    external = XML.replace(b'WindowLeft="20"', b'WindowLeft="200"')
    path.write_bytes(external)
    assert api.doc_save_checked(str(path))["conflict"]
    with pytest.raises(ExternalModificationError):
        api.doc_save()
    assert '"42"' in api.doc_diff()
    assert path.read_bytes() == external
    assert api.doc_revert()["elements"][1]["geometry"][0] == 200
    assert api.doc_watch(str(path)) is None
    api.doc_open(None)
    assert api.doc_watch(str(path)) is None


@pytest.fixture
def settle_xml(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(xml_watch, "monotonic", lambda: clock[0])

    def settle():
        clock[0] += 1

    return settle


def test_watch_debounces_atomic_replace_and_two_step_write(api, tmp_path, settle_xml):
    path = write_xml(tmp_path / "Plain.xml")
    original = api.doc_open(str(path))
    assert api.doc_watch(str(path)) is None
    settle_xml()
    assert api.doc_watch(str(path)) is None
    expected = XML.replace(b'WindowLeft="20"', b'WindowLeft="30"')
    path.write_bytes(expected[:100])
    assert api.doc_watch(str(path)) is None
    staged = path.with_suffix(".tmp")
    staged.write_bytes(expected)
    staged.replace(path)
    assert api.doc_watch(str(path)) is None
    settle_xml()
    change = api.doc_watch(str(path))
    assert change["error"] is None
    assert api.doc_source()["text"] == XML.decode()
    reloaded = api.doc_reload_external(str(path), change["token"])
    assert not reloaded["dirty"]
    assert reloaded["preview"] == original["preview"]
    assert reloaded["elements"][1]["geometry"][0] == 30
    assert api.doc_watch(str(path)) is None
    settle_xml()
    assert api.doc_watch(str(path)) is None
    assert api.doc_reload_external(str(path), change["token"]) is None


def test_watch_preserves_dirty_xml_and_checks_the_confirmed_save_revision(api, tmp_path, settle_xml):
    path = write_xml(tmp_path / "Plain.xml")
    scene = api.doc_open(str(path))
    api.doc_edit([geometry(1, scene["elements"][1]["geometry"], (42, 31, 15, 12))])
    path.write_bytes(b"<unfinished>")
    assert api.doc_watch(str(path)) is None
    settle_xml()
    invalid = api.doc_watch(str(path))
    assert "XML inválido" in invalid["error"]
    assert api.doc_reload_external(str(path), invalid["token"]) is None
    assert 'WindowLeft="42"' in api.doc_diff()
    outside = XML.replace(b'WindowLeft="20"', b'WindowLeft="200"')
    path.write_bytes(outside)
    assert api.doc_watch(str(path)) == invalid
    settle_xml()
    current = api.doc_watch(str(path))
    diff = api.doc_compare_external(str(path), current["token"])
    assert 'WindowLeft="200"' in diff and 'WindowLeft="42"' in diff
    assert api.doc_save_checked(str(path)) == {"conflict": current["token"]}
    later = XML.replace(b'WindowLeft="20"', b'WindowLeft="300"')
    path.write_bytes(later)
    assert api.doc_compare_external(str(path), current["token"]) is None
    latest = api.doc_save_checked(str(path), current["token"])
    assert latest["conflict"] != current["token"] and path.read_bytes() == later
    assert not api.doc_save_checked(str(path), latest["conflict"])["doc"]["dirty"]
    backup, = tmp_path.glob("Plain.before-gf-ui-editor-*.xml")
    assert backup.read_bytes() == later
    assert api.doc_watch(str(path)) is None
    settle_xml()
    assert api.doc_watch(str(path)) is None


def test_checked_save_rechecks_disk_after_staging_xml(api, tmp_path, monkeypatch):
    path = tmp_path / "Window.xml"
    path.write_bytes(XML)
    scene = api.doc_open(str(path))
    before = scene["elements"][0]["geometry"]
    api.doc_edit([{"index": 0, "field": "geometry", "before": before, "after": [42, *before[1:]]}])
    external = XML + b"\n"

    with monkeypatch.context() as patch:
        patch.setattr("gf_ui_editor.xml_document.os.fsync", lambda _: path.write_bytes(external))
        result = api.doc_save_checked(str(path))
    assert result["conflict"]
    assert path.read_bytes() == external
    assert not list(tmp_path.glob("*.gf-ui-editor.tmp"))

    saved = api.doc_save_checked(str(path), result["conflict"])
    assert not saved["doc"]["dirty"]
    assert b'WindowLeft="42"' in path.read_bytes()
    backup, = tmp_path.glob("Window.before-gf-ui-editor-*.xml")
    assert backup.read_bytes() == external


def test_watch_ignores_publish_and_detects_later_external_write(api, tmp_path, settle_xml):
    game = tmp_path / "game"
    (game / "UI").mkdir(parents=True)
    installed = write_xml(game / "UI" / "Plain.xml")
    active = project.create_from_source("Web", game / "UI", game, projects_root=tmp_path / "projects")
    local = active.ui_dir / installed.name
    local.write_bytes(XML.replace(b'WindowLeft="20"', b'WindowLeft="30"'))
    api._project = active
    api.open_dropped_xmls([str(installed)])
    api.doc_open(str(installed))
    api.publish()
    assert installed.read_bytes() == local.read_bytes()
    assert api.doc_watch(str(installed)) is None
    settle_xml()
    assert api.doc_watch(str(installed)) is None
    assert api.doc_source()["text"] == XML.decode()
    installed.write_bytes(XML.replace(b'WindowLeft="20"', b'WindowLeft="76"'))
    assert api.doc_watch(str(installed)) is None
    settle_xml()
    assert api.doc_watch(str(installed))["error"] is None


def test_watch_reference_layers_keeps_last_good_scene(api, tmp_path, settle_xml):
    source = tmp_path / "source"
    source.mkdir()
    write_xml(source / "BasicChar.xml")
    write_xml(source / "Radar.xml")
    active = project.create_from_source("Web", source, None, projects_root=tmp_path / "projects")
    api._project = active
    api.asset_base = lambda _path: "https://assets.test/"
    path = str(active.ui_dir / "BasicChar.xml")
    radar = active.ui_dir / "Radar.xml"
    api.canvas_change_layers(path, "add", radar.name)
    size = [1024, 768]
    original = api.canvas_layers(path, size)
    radar.write_bytes(b"<unfinished>")
    assert not api.canvas_watch_layers(path, size, True)["errors"]
    settle_xml()
    invalid = api.canvas_watch_layers(path, size, True)
    assert not invalid["scenes"] and "XML inválido" in invalid["errors"][0]
    assert api.canvas_layers(path, size) == original
    radar.write_bytes(XML.replace(b'WindowLeft="20"', b'WindowLeft="405"'))
    assert not api.canvas_watch_layers(path, size, True)["scenes"]
    settle_xml()
    changed, = api.canvas_watch_layers(path, size, True)["scenes"]
    assert changed["scene"]["elements"][1]["geometry"][0] == 405
    assert not api.canvas_watch_layers(path, size, True)["scenes"]


def test_insert_official_controls_preserves_edits_and_is_undoable(api, tmp_path, monkeypatch):
    path = write_xml(tmp_path / "Plain.xml")
    official = XML.replace(b'Child_Cnt="1"', b'Child_Cnt="2"').replace(
        b'</Container_Node>', b'<BaseWndProperty WindowID="3" WindowLeft="25" /></Container_Node>',
    )
    monkeypatch.setattr(api, "_official_game_dir", lambda: tmp_path)
    monkeypatch.setattr("gf_ui_editor.web_api.document.official_text_for",
                        lambda _game, name: official.decode() if name == "plain.xml" else None)
    scene = api.doc_open(str(path))
    edited = api.doc_edit([geometry(1, scene["elements"][1]["geometry"], (42, 31, 15, 12))])
    result = api.doc_insert_controls(str(path), ["3"])
    assert result["changed"]
    assert [item["id"] for item in result["doc"]["elements"]] == ["1", "2", "3"]
    assert result["doc"]["elements"][1] == edited["elements"][1]
    assert 'Child_Cnt="2"' in api.doc_diff()
    assert api.doc_insert_controls(str(path), ["3"]) == {"changed": False}
    assert api.doc_source_history(False) == edited
    assert api.doc_source_history(True) == result["doc"]
    assert path.read_bytes() == XML


def test_canvas_translates_normal_root_and_skips_locked_children(api, tmp_path):
    path = write_xml(tmp_path / "Plain.xml")
    scene = api.doc_open(str(path))
    drag = geometry(0, scene["elements"][0]["geometry"], (25, 30, 100, 80))
    changed = api.doc_canvas_edit([drag], [1], False, False)
    assert len(changed["edits"]) == 1
    assert changed["doc"]["elements"][1]["geometry"] == (20, 30, 15, 12)
    api.doc_revert()
    moved = api.doc_canvas_edit([drag], [], False, False)
    assert len(moved["edits"]) == 2
    assert moved["doc"]["elements"][1]["geometry"] == (35, 40, 15, 12)


def test_canvas_anchored_root_resize_and_ghost_area(api, tmp_path):
    path = write_xml(tmp_path / "Menu.xml")
    scene = api.doc_open(str(path), [800, 600])
    root, child = [row["geometry"] for row in scene["elements"]]
    resized = api.doc_canvas_edit([geometry(0, root, (10, 20, 140, 100))], [], True, False)
    assert resized["doc"]["elements"][0]["geometry"] == (-10, 0, 140, 100)
    assert resized["doc"]["preview"]["screen"] == scene["preview"]["screen"]
    assert resized["doc"]["elements"][1]["geometry"] == child
    api.doc_revert()
    drag = geometry(0, root, (210, 20, 100, 80))
    collapsed = api.doc_canvas_edit([drag], [], True, False)
    assert collapsed["doc"]["elements"][0]["geometry"][2:] == (1, 1)
    assert collapsed["doc"]["elements"][1]["geometry"] == child
    api.doc_revert()
    textured = api.doc_canvas_edit([drag], [], True, True)
    assert textured["doc"]["elements"][0]["geometry"] == (-190, 20, 100, 80)
