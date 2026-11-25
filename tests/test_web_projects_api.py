"""ProjectsApi (ponte da interface web) chamada direto, sem janela."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from gf_ui_editor import project as project_module
from gf_ui_editor.preferences import MemoryStore, Preferences
from gf_ui_editor.project import Project
from gf_ui_editor.web_api.projects import ProjectsApi


class Api(ProjectsApi):
    def __init__(self, tmp_path: Path, answers: list | None = None, game: Path | None = None):
        self.events: list[tuple[str, object]] = []
        self.answers = list(answers or [])
        self.prefs = Preferences(MemoryStore())
        self._setup_projects(self.prefs, (game or tmp_path / "missing") / "UI", None, self._answer)

    def _answer(self, kind, directory, file_types, save_name):
        return self.answers.pop(0) if self.answers else None

    def _emit(self, event, payload=None):
        self.events.append((event, payload))

    def _fetch_manifest(self):  # sem rede nos testes
        pass


@pytest.fixture
def game(tmp_path: Path) -> Path:
    game = tmp_path / "game"
    for folder, names in (("UI", ("BasicChar.xml", "Menu.xml", "icon.dds")), ("UICustom/UI-Hero", ("BasicChar.xml",))):
        (game / folder).mkdir(parents=True)
        for name in names:
            (game / folder / name).write_bytes(b"<UI/>")
    (game / "Launcher.ini").write_text("[Config]\nUI=default\n", encoding="latin-1")
    return game


@pytest.fixture
def projects(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "projects"
    monkeypatch.setattr(project_module, "PROJECTS_ROOT", root)
    return root


def _create(api: Api, game: Path, name: str = "Teste", **extra) -> dict:
    form = {"name": name, "source": str(game / "UI"), "game_dir": str(game), "include_assets": False, "publish_folder": "", **extra}
    return api.create_project(form)


def test_startup_shows_home_without_a_last_project(tmp_path: Path, projects: Path) -> None:
    api = Api(tmp_path)
    state = api.startup()
    assert state["view"] == "home" and state["project"] is None and state["open_path"] is None
    assert state["language"] == "pt_BR" and state["ui_mode"] == "classic"


def test_create_project_opens_it_and_reports_progress(tmp_path: Path, game: Path, projects: Path) -> None:
    api = Api(tmp_path, game=game)
    form = api.new_project_form()
    assert form["game_dir"] == str(game) and not form["game_dir_warning"]
    assert [source["label"] for source in form["sources"]] == ["UI", "UICustom/UI-Hero"]
    result = _create(api, game)
    assert result["count"] == 3
    state = result["state"]
    assert state["project"]["name"] == "Teste" and state["project"]["publish_dir"].endswith("UICustom\\Teste")
    assert api.prefs.last_project == state["project"]["root"] and api.prefs.game_dir == str(game)
    assert any(event == "progress" and payload["label"] == "create" for event, payload in api.events)
    assert _create(api, game) == {"error": "exists", "path": str(projects / "Teste")}


def test_new_project_targets_warn_about_existing_folders(tmp_path: Path, game: Path, projects: Path) -> None:
    api = Api(tmp_path, game=game)
    targets = api.new_project_targets("UI-Hero", "UICustom/UI-Hero", str(game))
    assert [target["value"] for target in targets] == ["", "UI-Hero"]
    assert targets[0]["warning"] == ["exists", {"folder": "UI-Hero"}] and targets[1]["warning"] is None


def test_home_data_lists_projects_and_computes_sizes_in_background(tmp_path: Path, game: Path, projects: Path) -> None:
    api = Api(tmp_path, game=game)
    _create(api, game, "Primeiro")
    _create(api, game, "Segundo")
    data = api.home_data()
    assert [row["title"] for row in data["projects"]] == ["Segundo", "Primeiro"]
    assert data["projects"][0]["current"] and data["continue"]["name"] == "Segundo"
    assert data["news"] is not None and data["how_to_url"].startswith("https://")
    import time

    deadline = time.time() + 5
    while time.time() < deadline and sum(event == "project_size" for event, _ in api.events) < 2:
        time.sleep(0.02)
    sizes = [payload for event, payload in api.events if event == "project_size"]
    assert {Path(item["root"]).name for item in sizes} == {"Primeiro", "Segundo"}
    assert all(item["size"].endswith("KB") for item in sizes)
    assert all(row["size"] is not None for row in api.home_data()["projects"])  # já calculados


def test_open_xml_remembers_the_last_file_and_startup_reopens_it(tmp_path: Path, game: Path, projects: Path) -> None:
    api = Api(tmp_path, game=game)
    root = _create(api, game)["state"]["project"]["root"]
    menu = Path(root) / "ui" / "Menu.xml"
    assert api.open_xml(str(menu))["open_path"] == str(menu)
    assert api.prefs.last_file("Teste") == "Menu.xml"
    assert api.go_home()["open_path"] is None
    again = Api(tmp_path, game=game)
    again.prefs = api.prefs
    again._prefs = api.prefs
    state = again.startup()
    assert state["view"] == "workspace" and state["open_path"] == str(menu)
    with pytest.raises(FileNotFoundError):
        api.open_xml(str(Path(root) / "ui" / "Missing.xml"))


def test_file_list_sections_and_saved_order(tmp_path: Path, game: Path, projects: Path) -> None:
    api = Api(tmp_path, game=game)
    root = Path(_create(api, game)["state"]["project"]["root"])
    (root / "ui" / "Menu.xml").write_bytes(b"<UI changed/>")
    api._project.invalidate_changes()
    listing = api.file_list("xml")
    assert listing["files"] == ["BasicChar.xml", "Menu.xml"] and listing["modified"] == [1]
    assert [section["kind"] for section in listing["sections"]] == ["layers", "changed", "all"]
    assert listing["in_project"] and listing["has_textures"]
    assert api.file_list("textures")["files"] == ["icon.dds"]
    assert api.move_section("all", -1, ["changed", "all"]) == ["layers", "all", "changed"]
    assert [section["kind"] for section in api.file_list("xml")["sections"]] == ["layers", "all", "changed"]
    with pytest.raises(ValueError):
        api.set_section_order(["all"])
    api.set_section_heights({"changed": 120, "bogus": 3})
    assert json.loads(api.prefs.files_section_heights) == {"changed": 120}
    assert api.file_list("xml")["heights"] == {"changed": 120}


def test_publish_sends_to_the_game_copy_and_counts_pending(tmp_path: Path, game: Path, projects: Path) -> None:
    api = Api(tmp_path, game=game)
    root = Path(_create(api, game)["state"]["project"]["root"])
    (root / "ui" / "Menu.xml").write_bytes(b"<UI changed/>")
    api._project.invalidate_changes()
    api._project.changes_ttl = 0
    assert api.shell_state()["pending"] == 1
    info = api.publish_info()
    assert not info["confirmed"] and info["custom_dir"] == str(game / "UICustom" / "Teste")
    api.confirm_publish()
    assert api.publish_info()["confirmed"]
    result = api.publish()
    assert result["copied"] == 1 and result["pending"] == 0 and result["custom_name"] == "Teste"
    assert (game / "UI" / "Menu.xml").read_bytes() == b"<UI changed/>"
    assert (game / "UICustom" / "Teste" / "Menu.xml").read_bytes() == b"<UI changed/>"
    assert "custom:Teste" in (game / "Launcher.ini").read_text(encoding="latin-1")
    assert any(event == "progress" and payload["label"] == "publish" for event, payload in api.events)


def test_export_zip_asks_where_and_reports_empty_projects(tmp_path: Path, game: Path, projects: Path) -> None:
    target = tmp_path / "out" / "ui"
    api = Api(tmp_path, [str(target)], game=game)
    root = Path(_create(api, game)["state"]["project"]["root"])
    (root / "ui" / "Menu.xml").write_bytes(b"<UI changed/>")
    chosen = api.pick_export_target()
    assert chosen == str(target.with_suffix(".zip"))
    result = api.export_zip(chosen)
    assert result["path"] == chosen and result["count"] == 3 and Path(chosen).is_file()
    assert api.pick_export_target() is None  # cancelou


def test_duplicate_rename_and_delete_projects(tmp_path: Path, game: Path, projects: Path) -> None:
    api = Api(tmp_path, game=game)
    root = _create(api, game)["state"]["project"]["root"]
    api.open_xml(str(Path(root) / "ui" / "Menu.xml"))
    assert api.duplicate_project(root, "Cópia") == {"name": "Cópia"}
    assert api.duplicate_project(root, "Cópia") == {"error": "taken", "name": "Cópia"}
    renamed = api.rename_project(root, "Novo nome")
    assert renamed["state"]["project"]["name"] == "Novo nome"
    assert api.prefs.last_file("Novo-nome") == "Menu.xml" and api.prefs.last_file("Teste") == ""
    assert api.rename_project(renamed["state"]["project"]["root"], "Cópia")["error"] == "taken"
    info = api.delete_info([str(projects / "Cópia")])
    assert info["projects"][0]["name"] == "Cópia" and info["owned"] == []
    trashed = []

    def fake_trash(path: Path) -> bool:
        trashed.append(path.name)
        import shutil

        shutil.rmtree(path)
        return True

    from gf_ui_editor import desktop

    original = desktop.move_to_trash
    desktop.move_to_trash = fake_trash
    try:
        result = api.delete_projects([str(projects / "Cópia"), str(projects / "Novo-nome")], remove_custom=False)
    finally:
        desktop.move_to_trash = original
    assert result["failed"] == [] and trashed == ["Cópia", "Novo-nome"]
    assert result["state"]["project"] is None and api.prefs.last_project == ""


def test_open_project_rejects_folders_that_are_not_projects(tmp_path: Path, projects: Path) -> None:
    api = Api(tmp_path, [str(tmp_path)])
    with pytest.raises(ValueError):
        api.open_project(str(tmp_path))
    assert api.browse_project() == {"error": "not_a_project"}
    assert api.browse_project() is None


def test_loose_xml_lists_the_folder_and_offers_a_project(tmp_path: Path, projects: Path) -> None:
    loose = tmp_path / "loose"
    loose.mkdir()
    (loose / "A.xml").write_bytes(b"<UI/>")
    (loose / "B.xml").write_bytes(b"<UI/>")
    api = Api(tmp_path, [str(loose / "A.xml")])
    picked = api.pick_xml()
    assert picked == {"path": str(loose / "A.xml"), "offer_project": True}
    api.set_offer_project(False)
    assert not api.prefs.offer_project_on_open
    state = api.open_loose(picked["path"])
    assert state["project"] is None and state["loose_dir"] == str(loose)
    listing = api.file_list("xml")
    assert listing["files"] == ["A.xml", "B.xml"] and not listing["in_project"]


def test_new_project_from_loose_files_brings_them_and_opens_the_focus(tmp_path: Path, game: Path, projects: Path) -> None:
    loose = tmp_path / "loose"
    loose.mkdir()
    (loose / "Menu.xml").write_bytes(b"<UI loose/>")
    api = Api(tmp_path, game=game)
    form = api.new_project_form(loose_dir=str(loose))
    assert form["loose_files"] == ["Menu.xml"]
    result = _create(api, game, loose_dir=str(loose), focus=str(loose / "Menu.xml"))
    root = Path(result["state"]["project"]["root"])
    assert (root / "ui" / "Menu.xml").read_bytes() == b"<UI loose/>"
    assert result["state"]["open_path"] == str(root / "ui" / "Menu.xml")


def test_settings_language_and_ui_mode(tmp_path: Path) -> None:
    api = Api(tmp_path)
    assert api.set_language("fr_FR")["language"] == "fr_FR"
    with pytest.raises(ValueError):
        api.set_language("xx")
    assert api.set_ui_mode("web") == "web" and api.prefs.ui_mode == "web"
    with pytest.raises(ValueError):
        api.set_ui_mode("other")
    with pytest.raises(ValueError):
        api.open_url("file:///c:/windows")
