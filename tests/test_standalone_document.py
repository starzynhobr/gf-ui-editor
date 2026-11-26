from pathlib import Path
import zlib

import pytest

from gf_ui_editor import game_updates, project as project_module, standalone_document
from gf_ui_editor.project import Project
from gf_ui_editor.standalone_document import StandaloneTextures, import_document
from gf_ui_editor.web_shell import WebApi
from gf_ui_editor.xml_document import ExternalModificationError, UIDocument


def xml(*names: str) -> bytes:
    controls = "".join(
        f'<BaseWndProperty WindowID="{number}" WindowLeft="10" WindowTop="20" WindowHeight="100" WindowWidth="80">'
        f'<BackGroundMap BGmap="{name}"><NorUV NorUVLeft="1" NorUVTop="2" NorUVWidth="8" NorUVHeight="9"/>'
        '</BackGroundMap></BaseWndProperty>' for number, name in enumerate(names, 1)
    )
    return f"<Root_Node>\n{controls}\n</Root_Node>".encode("ascii")


@pytest.fixture
def files(tmp_path, monkeypatch):
    game = tmp_path / "game"
    ui = game / "UI"
    ui.mkdir(parents=True)
    projects = tmp_path / "projects"
    monkeypatch.setattr(project_module, "PROJECTS_ROOT", projects)
    official = {"Window.xml": xml("project.dds"), "project.dds": b"project base", "Base.dds": b"official DDS"}
    for name, data in official.items():
        (ui / name).write_bytes(data)
    (ui / "game.tga").write_bytes(b"game TGA")
    (game / "GameDataFileList.txt").write_text("\n".join(
        f"UI/{name}|{len(data)}|{zlib.crc32(data):08X}|0|0|" for name, data in official.items()
    ), encoding="ascii")
    source = tmp_path / "project-source"
    source.mkdir()
    for name in ("Window.xml", "project.dds"):
        (source / name).write_bytes(official[name])
    game_updates.snapshot_official_ui(game)
    (ui / "Base.dds").write_bytes(b"modified game DDS")
    loose = tmp_path / "elsewhere"
    loose.mkdir()
    path = loose / "Window.xml"
    path.write_bytes(xml("local.dds", "PROJECT.DDS", "base.dds", "game.tga", "skin/Map.TGA"))
    (loose / "local.dds").write_bytes(b"local DDS")
    (loose / "skin").mkdir()
    (loose / "skin" / "map.tga").write_bytes(b"nested local TGA")
    return game, projects, source, path


@pytest.mark.parametrize("light", [False, True])
def test_import_conflicts_and_missing_textures(files, light):
    game, projects, source, path = files
    project = Project.create("Project", source, game, projects, light=light)
    document = UIDocument.load(path)
    document.set_geometry(0, (41, 20, 80, 100))
    original = project.resolve("Window.xml")
    if light:
        assert not (project.ui_dir / "Window.xml").exists()
        assert not (project.ui_dir / "project.dds").exists()

    # Local copies with names already supplied by the project or the official CRC cache are skipped.
    for name in ("project.dds", "base.dds", "unused.dds"):
        (path.parent / name).write_bytes(b"local shadow")
    conflict = import_document(document, project, game)
    assert conflict["conflict"] and original.read_bytes() != document.render_text().encode("big5")
    assert not (project.ui_dir / "local.dds").exists()
    copied = import_document(document, project, game, name="Another", bring_textures=False)
    assert not copied["conflict"] and not copied["textures"]
    assert (project.ui_dir / "Another.xml").read_bytes() == document.render_text().encode("big5")
    assert import_document(document, project, game, name="another.XML")["conflict"]

    replaced = import_document(document, project, game, replace=True)
    assert set(replaced["textures"]) == {"local.dds", "skin/Map.TGA"}
    assert Path(replaced["backup"]).read_bytes() == xml("project.dds")
    assert project.history(project.ui_dir / "Window.xml") == [Path(replaced["backup"])]
    assert original.read_bytes() == (xml("project.dds") if light else document.render_text().encode("big5"))
    assert project.resolve("project.dds").read_bytes() == b"project base"
    assert not (project.ui_dir / "base.dds").exists()
    assert not (project.ui_dir / "game.tga").exists()
    assert not (project.ui_dir / "unused.dds").exists()
    assert (project.ui_dir / "skin/Map.TGA").read_bytes() == b"nested local TGA"
    assert path.read_bytes() != Path(replaced["path"]).read_bytes()
    with pytest.raises(ValueError, match="apenas o nome"):
        import_document(document, project, game, name="../outside.xml")


def test_bridge_routes_drop_and_single_instance_preserves_project(files, monkeypatch):
    game, projects, source, path = files
    project = Project.create("Project", source, game, projects, light=True)
    api = WebApi("pt_BR", False, default_ui_directory=game / "UI")
    api.open_project(str(project.root))
    api.open_xml(str(project.ui_dir / "Window.xml"))
    other = path.with_name("Second.xml")
    other.write_bytes('<?xml version="1.0" encoding="UTF-8"?><doc>Olá 😀</doc>'.encode())
    invalid = path.with_name("broken.xml")
    invalid.write_text("<broken>", encoding="ascii")
    events = []
    monkeypatch.setattr(api, "_emit", lambda event, value: events.append((event, value)))
    api._on_xml_drop({"dataTransfer": {"files": [
        {"pywebviewFullPath": str(path)}, {"pywebviewFullPath": str(other)},
        {"pywebviewFullPath": str(invalid)}, {"name": "no-path.xml"},
        {"pywebviewFullPath": str(path.parent / "local.dds")},
    ]}})
    assert events == [("drop_xml", [str(path), str(other), str(invalid)])]
    result = api.open_dropped_xmls(events[0][1])
    state = result["state"]
    assert state["project"]["root"] == str(project.root)
    assert state["open_path"] == str(other) and state["standalone_paths"] == [str(path), str(other)]
    assert [error["path"] for error in result["errors"]] == [str(invalid)]
    assert api.doc_open(str(other))["elements"] == []
    assert "Olá 😀" in api.doc_source()["text"]
    api.open_xml(str(project.ui_dir / "Window.xml"))
    assert api.doc_open(str(project.ui_dir / "Window.xml"))["elements"][0]["texture"] == "project.dds"
    api._on_instance_message({"open": str(path)})
    assert events[-1] == ("open_external", {"path": str(path)})
    state = api.open_dropped_xmls([events[-1][1]["path"]])["state"]
    assert state["project"]["root"] == str(project.root) and state["open_path"] == str(path)
    assert len(state["standalone_paths"]) == 2

    scene = api.doc_open(str(path))
    assert scene["elements"][0]["texture"] == "local.dds"
    assert isinstance(api._standalone_textures(path), StandaloneTextures)
    textures = api._standalone_textures(path)
    assert textures.resolve("local.dds").read_bytes() == b"local DDS"
    assert textures.resolve("PROJECT.DDS").read_bytes() == b"project base"
    assert textures.resolve("BASE.dds").read_bytes() == b"official DDS"
    assert textures.resolve("game.tga").read_bytes() == b"game TGA"
    assert textures.resolve("../game/UI/game.tga") is None
    (path.parent / "project.dds").write_bytes(b"local precedence")
    assert textures.resolve("PROJECT.DDS").read_bytes() == b"local precedence"
    assert "--- Projeto/Window.xml" in api.standalone_compare(str(path), "project")
    assert "--- Oficial/Window.xml" in api.standalone_compare(str(path), "official")

    before = path.read_bytes()
    geometry = scene["elements"][0]["geometry"]
    api.doc_edit([{"field": "geometry", "index": 0, "before": geometry, "after": [22, *geometry[1:]]}])
    assert 'WindowLeft="22"' in api.doc_diff()
    api.doc_save()
    backup, = path.parent.glob("Window.before-gf-ui-editor-*.xml")
    assert backup.read_bytes() == before and b'WindowLeft="22"' in path.read_bytes()
    api.doc_edit([{"field": "geometry", "index": 0, "before": [22, *geometry[1:]], "after": [33, *geometry[1:]]}])
    external = path.read_bytes() + b"\n"
    path.write_bytes(external)
    with pytest.raises(ExternalModificationError, match="outro programa"):
        api.doc_save()
    assert api.doc_external_change() and path.read_bytes() == external
    assert list(path.parent.glob("Window.before-gf-ui-editor-*.xml")) == [backup]

    imported = api.standalone_import(str(path), "Imported", False, True)
    assert imported["state"]["standalone_paths"] == [str(other)]
    assert imported["state"]["open_path"] == str(project.ui_dir / "Imported.xml")
    assert imported["doc"]["elements"][0]["geometry"][0] == 33
    assert b'WindowLeft="33"' in Path(imported["path"]).read_bytes() and path.read_bytes() == external


def test_import_can_adopt_a_project_from_standalone_workspace(files):
    game, projects, source, path = files
    project = Project.create("Project", source, game, projects)
    api = WebApi("pt_BR", False, default_ui_directory=game / "UI")
    path = path.with_name("Unicode.xml")
    raw = '<?xml version="1.0" encoding="UTF-16"?><doc>Olá 😀</doc>'.encode("utf-16")
    path.write_bytes(raw)
    assert api.open_dropped_xmls([str(path)])["state"]["project"] is None
    api.doc_open(str(path))
    assert "Olá 😀" in api.doc_source()["text"]
    result = api.standalone_import(str(path), None, False, True, str(project.root))
    assert result["state"]["project"]["root"] == str(project.root)
    assert Path(result["path"]).read_bytes() == raw
    api.doc_open(result["path"])
    assert "Olá 😀" in api.doc_source()["text"]


def test_import_rolls_back_new_textures_if_xml_install_fails(files, monkeypatch):
    game, projects, source, path = files
    project = Project.create("Project", source, game, projects)
    install = standalone_document._install_new_file

    def fail_on_xml(staged, target):
        if target.suffix.lower() == ".xml":
            raise PermissionError(target)
        install(staged, target)

    monkeypatch.setattr(standalone_document, "_install_new_file", fail_on_xml)
    with pytest.raises(PermissionError):
        import_document(UIDocument.load(path), project, game, name="Import")
    assert not (project.ui_dir / "Import.xml").exists()
    assert not (project.ui_dir / "local.dds").exists()
    assert not (project.ui_dir / "skin/Map.TGA").exists()
