from pathlib import Path

import pytest

from gf_ui_editor import project
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
    assert api.doc_external_change() is None


def test_external_conflict_keeps_pending_edits_and_revert_refreshes(api, tmp_path):
    path = write_xml(tmp_path / "Plain.xml")
    scene = api.doc_open(str(path))
    before = scene["elements"][1]["geometry"]
    api.doc_edit([geometry(1, before, (42, 31, 15, 12))])
    external = XML.replace(b'WindowLeft="20"', b'WindowLeft="200"')
    path.write_bytes(external)
    assert api.doc_external_change()
    with pytest.raises(ExternalModificationError):
        api.doc_save()
    assert '"42"' in api.doc_diff()
    assert path.read_bytes() == external
    assert api.doc_revert()["elements"][1]["geometry"][0] == 200
    assert api.doc_external_change() is None
    api.doc_open(None)
    assert api.doc_external_change() is None


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
