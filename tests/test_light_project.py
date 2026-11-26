from pathlib import Path
from zipfile import ZipFile
import zlib

import pytest

from gf_ui_editor import desktop, file_list, game_sync, textures, versions
from gf_ui_editor.document_session import DocumentSession
from gf_ui_editor.project import Project, convert_to_light, create_from_source
from gf_ui_editor.texture_cache import TextureCache
from gf_ui_editor.web_shell import WebApi


XML = (
    b'<Root_Node><BaseWndProperty WindowID="1" WindowLeft="10" WindowTop="20" WindowHeight="100" WindowWidth="80">'
    b'<BackGroundMap BGmap="Main.dds"><NorUV NorUVLeft="1" NorUVTop="2" NorUVWidth="8" NorUVHeight="9"/>'
    b'</BackGroundMap></BaseWndProperty></Root_Node>'
)
FILES = {"Window.xml": XML, "Other.xml": XML, "Main.dds": b"DDS base", "skin/Map.tga": b"TGA base"}


def write_official(game, files):
    rows = [f"UI/{name}|{len(data)}|{zlib.crc32(data):08X}|0|0|" for name, data in files.items()]
    (game / "GameDataFileList.txt").write_text("\n".join(rows), encoding="ascii")


@pytest.fixture
def game(tmp_path):
    game = tmp_path / "game"
    for name, data in FILES.items():
        path = game / "UI" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (game / "Launcher.ini").write_text("[Config]\nUI=padrao\n", encoding="ascii")
    write_official(game, FILES)
    return game


def test_light_projects_share_and_pin_the_base(tmp_path, game):
    root = tmp_path / "projects"
    light = create_from_source("Light", game / "UI", game, projects_root=root, light=True)
    full = Project.create("Full", game / "UI", game, root)
    assert light.light and not full.light
    assert list(light.ui_dir.iterdir()) == []
    assert [name.as_posix() for name in light.files()] == sorted(FILES, key=str.lower)
    original = light.resolve("Window.xml")
    assert original == light.resolve("OTHER.XML")  # Same CRC stored once.
    api = WebApi("pt_BR", False)
    api._project = full
    converted = api.convert_project_to_light()
    assert converted["state"]["project"]["light"] is True
    assert Path(converted["backup"]).is_file() and full.resolve("Window.xml") == original
    assert convert_to_light(full) is None
    assert TextureCache(light.ui_dir, light).path_for("main.DDS") == full.resolve("Main.dds")
    new_xml = XML.replace(b'WindowLeft="10"', b'WindowLeft="42"')
    (game / "UI" / "Window.xml").write_bytes(new_xml)
    write_official(game, {**FILES, "Window.xml": new_xml})
    reopened = Project.load(light.root)
    assert reopened.resolve("Window.xml").read_bytes() == XML
    assert reopened.modified_files() == set()
    assert reopened.base_bytes("Window.xml") == XML


def test_web_document_and_external_edit_materialize_private_files(tmp_path, game, monkeypatch):
    project = Project.create("Light", game / "UI", game, tmp_path / "projects", light=True)
    api = WebApi("pt_BR", False)
    api._project = project
    xml = project.ui_dir / "Window.xml"
    scene = api.doc_open(str(xml))
    assert scene["elements"] and not xml.exists()
    assert api.doc_external_change() is None
    before = scene["elements"][0]["geometry"]
    api.doc_edit([{"field": "geometry", "index": 0, "before": before, "after": [42, *before[1:]]}])
    assert project.resolve("Window.xml") != xml and '-<Root_Node>' in api.doc_diff()
    api.doc_save()
    assert project.modified_files() == {"Window.xml"}
    assert project.base_bytes("Window.xml") == XML
    assert project.history(xml)[0].read_bytes() == XML
    assert b'WindowLeft="42"' in xml.read_bytes()
    assert project.resolve("Other.xml").read_bytes() == XML

    opened = []
    monkeypatch.setattr(desktop, "open_in_text_editor", lambda path: opened.append(path))
    monkeypatch.setattr(desktop, "open_path", lambda path: opened.append(path))
    other = project.ui_dir / "Other.xml"
    dds = project.ui_dir / "Main.dds"
    api.doc_open(str(other))
    api.open_in_text_editor(str(other))
    assert api.open_texture_file(str(other), "main.dds") == "ok"
    assert opened == [other, dds]
    assert api.doc_external_change() is None
    other.write_bytes(xml.read_bytes())
    assert api.doc_external_change()
    assert api.doc_revert()["elements"][0]["geometry"][0] == 42
    dds.write_bytes(b"external edit")
    assert project.base_path(project.base_files["Main.dds"]).read_bytes() == FILES["Main.dds"]


def test_delete_rename_pull_import_and_restore(tmp_path, game):
    project = Project.create("Light", game / "UI", game, tmp_path / "projects", light=True)
    texture = project.ui_dir / "Main.dds"
    renamed, _ = project.rename_file(texture, "New.dds")
    assert renamed.read_bytes() == FILES["Main.dds"]
    assert not Project.load(project.root).resolve("Main.dds").exists()
    assert "Main.dds" in project.modified_files()
    assert TextureCache(project.ui_dir, project).path_for("Main.dds") is None
    users = file_list.xml_using_texture(project, "Main.dds")
    file_list.retarget_texture(project, users, "Main.dds", "New.dds")
    assert all(b'BGmap="New.dds"' in path.read_bytes() for path in users)

    layered = project.ui_dir / "skin" / "Map.tga"
    backup = project.delete_file(layered)
    assert backup.read_bytes() == FILES["skin/Map.tga"]
    assert Path("skin/Map.tga") not in Project.load(project.root).files()
    assert project.restore(layered, backup) is None
    assert "skin/map.tga" not in Project.load(project.root).deleted
    assert layered.read_bytes() == FILES["skin/Map.tga"]

    loose = tmp_path / "Main.dds"
    loose.write_bytes(b"import")
    assert project.import_file(loose)[0] == texture
    replacement = tmp_path / "Map.tga"
    replacement.write_bytes(b"pull")
    assert game_sync.pull(project, [("skin/Map.tga", replacement)]) == 1
    assert project.history(layered)[0].read_bytes() == FILES["skin/Map.tga"]
    assert textures.copy_for_edit(project.ui_dir, "Main.dds", "Copy", project).read_bytes() == b"import"


def test_conversion_round_trip_and_unchanged_archive_members(tmp_path, game):
    project = Project.create("Full", game / "UI", game, tmp_path / "projects")
    path = project.ui_dir / "Window.xml"
    document = project.load_document(path)
    document.set_geometry(0, (40, *document.elements[0].geometry[1:]))
    document.save(project.history_path_for(path))
    expected = {name.as_posix(): project.resolve(name).read_bytes() for name in project.files()}
    full_zip = project.export_zip(tmp_path / "full.zip")
    backup = convert_to_light(project)
    assert backup is not None and project.light
    assert sorted(path.name for path in project.ui_dir.iterdir() if path.is_file()) == ["Window.xml"]
    light_zip = project.export_zip(tmp_path / "light.zip")
    with ZipFile(full_zip) as a, ZipFile(light_zip) as b:
        assert a.namelist() == b.namelist()
        assert all(a.read(name) == b.read(name) for name in a.namelist())

    project.delete_file(project.ui_dir / "Other.xml")
    deleted = versions.save_version(project, "deleted")
    # Restoring the conversion checkpoint uses its pinned CRCs even if the installed UI changed.
    (game / "UI" / "Other.xml").write_bytes(b"<changed/>")
    write_official(game, {**FILES, "Other.xml": b"<changed/>"})
    assert not versions.restore_version(project, backup).unresolved
    assert not Project.load(project.root).light
    assert {name: (project.ui_dir / name).read_bytes() for name in expected} == expected
    assert not versions.restore_version(project, deleted).unresolved
    assert Project.load(project.root).light and not project.resolve("Other.xml").exists()
    assert not (project.ui_dir / "Main.dds").exists()


def test_session_reloads_base_after_revert(tmp_path, game):
    project = Project.create("Light", game / "UI", game, tmp_path / "projects", light=True)
    session = DocumentSession()
    xml = project.ui_dir / "Window.xml"
    assert session.open(xml, project=project) == session.revert()
    assert not xml.exists()
