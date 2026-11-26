"""Serviço da aba Textos (texts_session) e a ponte da interface web (TextsApi), sem janela."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from gf_ui_editor import project as project_module, text_data, texts_session
from gf_ui_editor.preferences import MemoryStore, Preferences
from gf_ui_editor.project import Project
from gf_ui_editor.text_data import TextEdit
from gf_ui_editor.web_api.projects import ProjectsApi
from gf_ui_editor.web_api.texts import TextsApi

ITEMS = "538|Pedra|Uma pedra.|\r\n539|Runa|Uma runa.|\r\n"


def _game(tmp_path: Path, name: str, content: bytes) -> Path:
    game = tmp_path / "game"
    folder = game / "data" / "Translate"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(content)
    return game


@pytest.fixture(autouse=True)
def _projects_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_module, "PROJECTS_ROOT", tmp_path / "projects")


# ---- serviço ----------------------------------------------------------------------------------
def test_results_without_game_or_query() -> None:
    session = texts_session.TextsSession()
    assert session.results("x", False).summary == "no_game"


def test_search_in_memory_and_edit_then_restore(tmp_path: Path) -> None:
    game = _game(tmp_path, "T_Item.ini", ITEMS.encode("cp1252"))
    project = tmp_path / "project"
    session = texts_session.TextsSession()
    session.set_context(game, project)
    assert session.results("", False).summary == "type_to_search"
    found = session.results("runa", False)
    assert [(row.name, row.record_id, row.state) for row in found.rows] == [("T_Item.ini", "539", "")]
    assert (found.summary, found.values) == ("count", {"total": 1})

    opened = session.open_record("T_Item.ini", "539")
    assert opened.fields == ["Runa", "Uma runa."] and opened.original is None and not opened.can_restore
    assert opened.newline == "\r\n" and opened.text_file.encoding == "cp1252"
    session.save_record(opened, ["Runa Brilhante", "Uma runa."])
    assert text_data.load_edits(project)["T_Item.ini"]["539"] == TextEdit(["Runa Brilhante", "Uma runa."], ["Runa", "Uma runa."])
    found = session.results("", False)  # sem busca: o que o projeto mudou
    assert [row.state for row in found.rows] == ["edited"] and (found.summary, found.values) == ("changed", {"total": 1})
    assert session.results("brilhante", False).rows[0].fields == ["Runa Brilhante", "Uma runa."]  # a edição também casa

    reopened = session.open_record("T_Item.ini", "539")
    assert reopened.can_restore
    session.save_record(reopened, None)  # voltar ao original: jogo e original iguais, a edição sai
    assert text_data.load_edits(project) == {}
    assert session.results("", False).summary == "nothing_edited"


def test_validate_rejects_pipe_and_unsupported_characters() -> None:
    assert texts_session.validate(["ok"], "cp1252") is None
    assert texts_session.validate(["a|b"], "cp1252") == "pipe"
    assert texts_session.validate(["魔法"], "cp1252") == "encoding"


def test_states_updated_and_changed_in_game(tmp_path: Path) -> None:
    game = _game(tmp_path, "T_Item.ini", b"538|Pedra Velha|x|\r\n539|Runa Antiga|Uma runa.|\r\n540|Osso|y|\r\n")
    project = tmp_path / "project"
    backup = project / ".history" / "data" / "20261026-111316"
    backup.mkdir(parents=True)
    (backup / "T_Item.ini").write_bytes(b"538|Pedra|x|\r\n539|Runa|Uma runa.|\r\n540|Osso|y|\r\n")
    text_data.save_edits(project, {"T_Item.ini": {"539": TextEdit(["Runa Nova", "Uma runa."], ["Runa", "Uma runa."])}})
    session = texts_session.TextsSession()
    session.set_context(game, project)
    found = session.results("", False)
    states = {row.record_id: row.state for row in found.rows}
    assert states == {"539": "updated", "538": "changed"}
    updated = next(row for row in found.rows if row.record_id == "539")
    assert updated.original == ["Runa", "Uma runa."] and updated.game_fields == ["Runa Antiga", "Uma runa."]
    assert found.updates == 1
    assert session.open_record("T_Item.ini", "538").original == ["Pedra", "x"]  # do backup do envio


def test_result_limit_and_index_search(tmp_path: Path) -> None:
    content = "".join(f"{i}|texto comum {i}|\r\n" for i in range(600)).encode("cp1252")
    game = _game(tmp_path, "T_TextIndex.ini", content)
    session = texts_session.TextsSession()
    session.set_context(game, tmp_path / "project")
    found = session.results("comum", False)
    assert len(found.rows) == 500 and (found.summary, found.values) == ("limited", {"total": 600, "shown": 500})
    done = []
    session.start_indexing(done.append)
    deadline = time.time() + 20
    while not done and time.time() < deadline:
        time.sleep(0.02)
    assert done == [game] and session.index_finished(game) and session.index_ready
    session.reload()
    session.files = None
    session.index_game_dir = game
    found = session.results("comum 59", False)
    assert found.values["total"] == 11 and session.files is None  # pelo índice, sem ler os arquivos


def test_import_plan_and_apply(tmp_path: Path) -> None:
    game = _game(tmp_path, "T_Item.ini", ITEMS.encode("cp1252"))
    source = tmp_path / "old"
    source.mkdir()
    (source / "T_Item.ini").write_bytes(ITEMS.replace("539|Runa|", "539|Runa Velha|").encode("cp1252"))
    project = tmp_path / "project"
    session = texts_session.TextsSession()
    session.set_context(game, project)
    assert session.can_import
    plan = session.plan_import(source)
    assert plan.count == 1
    session.apply_import(plan)
    assert text_data.load_edits(project)["T_Item.ini"]["539"].fields == ["Runa Velha", "Uma runa."]


def test_service_does_not_import_qt() -> None:
    code = "import sys, gf_ui_editor.texts_session, gf_ui_editor.web_api.texts; assert not [m for m in sys.modules if m.startswith('PySide6')]"
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
    subprocess.run([sys.executable, "-c", code], check=True, env=env)


# ---- ponte -------------------------------------------------------------------------------------
class Api(ProjectsApi, TextsApi):
    def __init__(self, answers=None):
        self.events: list = []
        self.answers = list(answers or [])
        self.prefs = Preferences(MemoryStore())
        self._setup_projects(self.prefs, Path("missing/UI"), None, lambda *args: self.answers.pop(0) if self.answers else None)

    def _emit(self, event, payload=None):
        self.events.append((event, payload))


@pytest.fixture
def api(tmp_path: Path) -> Api:
    game = _game(tmp_path, "T_Item.ini", ITEMS.encode("cp1252"))
    (game / "UI").mkdir()
    (game / "UI" / "A.xml").write_bytes(b"<Root_Node />")
    project = Project.create("Textos", game / "UI", game, projects_root=tmp_path / "projects")
    api = Api([str(tmp_path / "old")])
    api.open_project(str(project.root))
    return api


def test_bridge_search_open_save_and_restore(api: Api, tmp_path: Path) -> None:
    assert api.texts_state()["available"] and api.texts_state()["can_import"]
    found = api.texts_search("runa", False)
    assert found["rows"][0]["id"] == "539" and found["summary"] == "count" and found["limit"] == 500
    opened = api.texts_open("T_Item.ini", "539")
    assert opened["fields"] == ["Runa", "Uma runa."] and opened["newline"] == "\r\n" and opened["original"] is None
    assert api.texts_save("T_Item.ini", "539", ["a|b", "x"]) == {"error": "pipe", "encoding": "cp1252"}
    assert api.texts_save("T_Item.ini", "539", ["魔", "x"])["error"] == "encoding"
    assert api.texts_save("T_Item.ini", "539", ["Runa\nNova", "Uma runa."]) == {"saved": True}
    root = Path(api.shell_state()["project"]["root"])
    assert text_data.load_edits(root)["T_Item.ini"]["539"].fields == ["Runa\r\nNova", "Uma runa."]  # quebra do arquivo
    assert ("text_edits_changed", {"project": str(root), "files": ["T_Item.ini"]}) in api.events
    assert api.texts_search("", False)["rows"][0]["state"] == "edited"
    assert api.texts_open("T_Item.ini", "539")["can_restore"]
    api.texts_restore("T_Item.ini", "539")
    assert text_data.load_edits(root) == {}
    assert api.texts_open("T_Item.ini", "999") is None
    with pytest.raises(ValueError):
        api.texts_save("T_Item.ini", "999", ["x"])


def test_bridge_import_with_confirmation(api: Api, tmp_path: Path) -> None:
    source = tmp_path / "old"
    source.mkdir()
    (source / "T_Item.ini").write_bytes(ITEMS.replace("539|Runa|", "539|Runa Velha|").encode("cp1252"))
    (source / "T_Extra.ini").write_bytes(b"1|x|\r\n")
    folder = api.texts_pick_import()
    assert folder == str(source)
    plan = api.texts_plan_import(folder)
    assert plan["count"] == 1 and plan["unknown_files"] == ["T_Extra.ini"] and plan["per_file"] == [["T_Item.ini", 1]]
    assert api.texts_apply_import() == 1
    assert api.texts_apply_import() == 0  # o plano foi usado
    root = Path(api.shell_state()["project"]["root"])
    assert text_data.load_edits(root)["T_Item.ini"]["539"].fields == ["Runa Velha", "Uma runa."]
    assert api.shell_state()["pending"] == 0  # textos não contam como arquivos da UI


def test_bridge_reports_the_index_and_follows_the_open_project(api: Api, tmp_path: Path) -> None:
    api.texts_state()
    deadline = time.time() + 20
    while ("texts_index_ready", None) not in api.events and time.time() < deadline:
        time.sleep(0.02)
    assert ("texts_index_ready", None) in api.events and api.texts_state()["index_ready"]
    api.go_home()
    api._project = None
    assert api.texts_state() == {"available": False, "can_import": False, "index_ready": False}
    assert api.texts_search("x", False)["summary"] == "no_game"
