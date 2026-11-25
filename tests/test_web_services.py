"""Serviços sem Qt usados pela interface web: interface escolhida, novo projeto, tela inicial."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from gf_ui_editor import desktop, file_list, home, new_project, webview_runtime
from gf_ui_editor.preferences import UI_LANGUAGES, MemoryStore, Preferences
from gf_ui_editor.project import Project


def _ui(folder: Path, *names: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    for name in names:
        (folder / name).write_bytes(b"<UI/>")
    return folder


def _game(tmp_path: Path) -> Path:
    game = tmp_path / "game"
    _ui(game / "UI", "BasicChar.xml", "Menu.xml")
    _ui(game / "UICustom" / "UI-Hero", "BasicChar.xml")
    (game / "Launcher.ini").write_text("[Launcher]\n", encoding="latin-1")
    return game


# ---- ui_mode e WebView2 --------------------------------------------------------------------
def test_ui_mode_defaults_to_classic_and_is_saved_as_text() -> None:
    store = MemoryStore()
    prefs = Preferences(store)
    assert prefs.ui_mode == "classic"
    prefs.ui_mode = "web"
    assert store.values["ui_mode"] == "web" and prefs.ui_mode == "web"


def test_move_last_file_follows_a_renamed_project() -> None:
    prefs = Preferences(MemoryStore())
    prefs.set_last_file("Antigo", "Menu.xml")
    prefs.move_last_file("Antigo", "Novo")
    assert prefs.last_file("Novo") == "Menu.xml" and prefs.last_file("Antigo") == ""
    prefs.move_last_file("Novo", "Novo")
    assert prefs.last_file("Novo") == "Menu.xml"


def test_ui_languages_match_the_translations() -> None:
    from gf_ui_editor.i18n import LANGUAGES

    assert UI_LANGUAGES == LANGUAGES


def test_resolve_ui_uses_the_saved_choice_unless_the_command_line_says_otherwise() -> None:
    def always() -> bool:
        return True

    assert webview_runtime.resolve_ui(None, "classic", always) == ("classic", False)
    assert webview_runtime.resolve_ui(None, "web", always) == ("web", False)
    assert webview_runtime.resolve_ui("classic", "web", always) == ("classic", False)
    assert webview_runtime.resolve_ui("web", "classic", always) == ("web", False)
    assert webview_runtime.resolve_ui(None, "bogus", always) == ("classic", False)


def test_resolve_ui_falls_back_to_classic_without_webview2() -> None:
    calls = []

    def missing() -> bool:
        calls.append(1)
        return False

    assert webview_runtime.resolve_ui(None, "web", missing) == ("classic", True)
    assert webview_runtime.resolve_ui("web", "classic", missing) == ("classic", True)
    assert webview_runtime.resolve_ui(None, "classic", missing) == ("classic", False)
    assert len(calls) == 2  # só consulta quando a nova foi pedida


def test_webview2_version_reads_the_edge_update_client_keys() -> None:
    seen = []

    def reader(values):
        def read(hive, path, name):
            seen.append((hive, name))
            return values.get(hive)
        return read

    assert webview_runtime.webview2_version(reader({})) is None
    assert webview_runtime.webview2_version(reader({"HKLM": "0.0.0.0"})) is None
    assert webview_runtime.webview2_version(reader({"HKCU": "131.0.2903.70"})) == "131.0.2903.70"
    assert all(name == "pv" for _hive, name in seen)


def test_web_build_ready_checks_index_html(tmp_path: Path) -> None:
    assert not webview_runtime.web_build_ready(tmp_path)
    (tmp_path / "index.html").write_text("<html></html>")
    assert webview_runtime.web_build_ready(tmp_path)


# ---- novo projeto ---------------------------------------------------------------------------
def test_new_project_sources_and_game_dir_warning(tmp_path: Path) -> None:
    game = _game(tmp_path)
    found = new_project.sources(game)
    assert [source.label for source in found] == ["UI", "UICustom/UI-Hero"]
    assert found[0].is_game_ui and not found[1].is_game_ui
    assert new_project.sources(None) == []
    assert not new_project.game_dir_warning(game)
    assert new_project.game_dir_warning(tmp_path)
    assert not new_project.game_dir_warning(None)
    assert new_project.chosen_game_dir(game / "UI") == game


def test_new_project_publish_targets_offer_the_origin_folder() -> None:
    assert new_project.publish_targets("Minha UI", "UI") == [("", "Minha-UI")]
    assert new_project.publish_targets("", "UICustom/UI-Hero") == [("", ""), ("UI-Hero", "UI-Hero")]


def test_new_project_publish_warning_for_shared_and_existing_folders(tmp_path: Path) -> None:
    game = _game(tmp_path)
    projects = tmp_path / "projects"
    assert new_project.publish_warning("", "UI-Hero", game, projects) == ("exists", {"folder": "UI-Hero"})
    assert new_project.publish_warning("UI-Hero", "Outro", game, projects) is None  # atualizar a origem é o esperado
    assert new_project.publish_warning("", "", game, projects) is None
    Project.create("Hero", game / "UICustom" / "UI-Hero", game, projects_root=projects, publish_folder="UI-Hero")
    kind, data = new_project.publish_warning("UI-Hero", "Outro", game, projects)
    assert kind == "shared" and data == {"projects": "Hero", "folder": "UI-Hero"}


def test_new_project_suggested_name_and_loose_files(tmp_path: Path) -> None:
    assert new_project.suggested_name("", "UICustom/UI-Hero") == "UI-Hero"
    assert new_project.suggested_name("Já tem", "UICustom/UI-Hero") == "Já tem"
    assert new_project.suggested_name("", picked=tmp_path / "Pacote.zip") == "Pacote"
    assert new_project.suggested_name("", picked=tmp_path / "Pasta") == "Pasta"
    assert new_project.suggested_name("", "UI") == ""
    game = _game(tmp_path)
    loose = _ui(tmp_path / "loose", "b.xml", "A.xml", "c.before-gf-ui-editor-20260101-000000.xml")
    assert [path.name for path in new_project.loose_files(loose, new_project.sources(game))] == ["A.xml", "b.xml"]
    assert new_project.loose_files(game / "UI", new_project.sources(game)) == []
    assert new_project.loose_files(None, []) == []


# ---- tela inicial -----------------------------------------------------------------------------
def test_project_rows_and_continue_summary(tmp_path: Path) -> None:
    game = _game(tmp_path)
    projects = tmp_path / "projects"
    first = Project.create("Primeiro", game / "UI", game, projects_root=projects)
    second = Project.create("Segundo", game / "UI", None, projects_root=projects)
    rows = home.project_rows([first.root, second.root], second.root)
    assert rows[0]["title"] == "Segundo" and rows[0]["current"] and rows[0]["files"] == 2
    assert rows[1]["title"] == "Primeiro" and not rows[1]["current"]
    assert rows[0]["age"][0] == "now"
    (first.ui_dir / "Menu.xml").write_bytes(b"<UI changed/>")
    summary = home.continue_summary(first, "Menu.xml")
    assert summary["name"] == "Primeiro" and summary["last_file"] == "Menu.xml"
    assert summary["modified"] == 1 and summary["custom_name"] == "Primeiro" and summary["has_game"]
    assert not home.continue_summary(second, "")["has_game"]


def test_size_cache_only_recomputes_projects_edited_since(tmp_path: Path) -> None:
    game = _game(tmp_path)
    project = Project.create("Tamanho", game / "UI", game, projects_root=tmp_path / "projects")
    cache = home.SizeCache()
    pending = cache.pending([project.root])
    assert [key for key, _edited in pending] == [str(project.root)]
    reported = []
    cache.compute(pending, lambda key, size: reported.append((key, size)))
    assert reported and reported[0][1] > 0
    assert cache.pending([project.root]) == []
    assert cache.get(project.root, pending[0][1]) == reported[0][1]
    cache.forget(project.root)
    assert cache.pending([project.root])


def test_news_titles_and_how_to_url() -> None:
    from gf_ui_editor import release_notes

    assert home.news_titles(None, "pt_BR") == []
    titles = home.news_titles(release_notes.bundled(), "pt_BR")
    assert len(titles) <= 3 and all(not title.endswith(".") for title in titles)
    assert home.how_to_url("pt_BR").endswith("/pt/projects/gf-ui-editor")
    assert home.how_to_url("fr_FR").endswith("/en/projects/gf-ui-editor")


# ---- lista de arquivos --------------------------------------------------------------------------
def test_sections_payload_lists_each_file_once_with_sections_in_the_saved_order() -> None:
    listing = file_list.FileListing(
        xml=[Path("A.xml"), Path("B.xml"), Path("C.xml")], textures=[Path("t.dds")], modified={"B.xml", "t.dds"},
        shared_publish=["Outro"],
    )
    payload = file_list.sections_payload(listing, "xml", {"C.xml"}, "all,changed,layers", '{"changed": 90}')
    assert payload["mode"] == "xml" and payload["files"] == ["A.xml", "B.xml", "C.xml"]
    assert payload["modified"] == [1] and payload["layers"] == [2]
    assert [section["kind"] for section in payload["sections"]] == ["all", "changed", "layers"]
    assert payload["sections"][0]["items"] == [0, 1, 2]
    assert payload["sections"][1]["items"] == [1] and payload["sections"][2]["items"] == [2]
    assert payload["heights"] == {"changed": 90} and payload["has_textures"] and payload["shared_publish"] == ["Outro"]
    textures = file_list.sections_payload(listing, "textures", {"C.xml"}, "", "")
    assert textures["files"] == ["t.dds"] and textures["modified"] == [0] and textures["layers"] == []
    assert [section["kind"] for section in textures["sections"]] == list(file_list.FILE_SECTIONS)
    no_textures = file_list.FileListing(xml=[Path("A.xml")])
    assert file_list.sections_payload(no_textures, "textures", set(), "", "")["mode"] == "xml"


# ---- Windows ----------------------------------------------------------------------------------
def test_move_to_trash_reports_missing_files(tmp_path: Path) -> None:
    assert desktop.move_to_trash(tmp_path / "missing") is False


def test_open_in_text_editor_launches_without_waiting(tmp_path: Path) -> None:
    launched = []
    label = desktop.open_in_text_editor(tmp_path / "a.xml", launch=launched.append)
    assert label in ("Notepad++", "Bloco de Notas")
    assert launched[0][1] == str(tmp_path / "a.xml")


def test_web_services_do_not_import_qt() -> None:
    code = (
        "import sys; import gf_ui_editor.webview_runtime, gf_ui_editor.new_project, gf_ui_editor.desktop, "
        "gf_ui_editor.home, gf_ui_editor.file_list, gf_ui_editor.web_api.projects; "
        "assert not any(name.startswith('PySide6') for name in sys.modules), "
        "sorted(n for n in sys.modules if 'PySide6' in n)"
    )
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
    subprocess.run([sys.executable, "-c", code], check=True, env=env)
