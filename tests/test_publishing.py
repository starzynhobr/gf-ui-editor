"""Enviar para o jogo (F5): UI e textos, sem Qt."""
from datetime import datetime
import os
from pathlib import Path
import subprocess
import sys

import pytest

from gf_ui_editor import publishing, text_data
from gf_ui_editor.game_updates import FileDiff
from gf_ui_editor.project import Project, PublishResult
from gf_ui_editor.text_data import TextEdit

ITEMS = "538|Pacote|Abre.|\r\n539|Runa|Uma runa.|\r\n"


def _project(tmp_path: Path) -> Project:
    game = tmp_path / "game"
    (game / "UI").mkdir(parents=True)
    (game / "UI" / "Radar.xml").write_text("<a/>", encoding="utf-8")
    (game / "Launcher.ini").write_bytes(b"[Config]\r\nUIAplicada=padrao\r\n")
    translate = game / "data" / "Translate"
    translate.mkdir(parents=True)
    (translate / "T_Item.ini").write_bytes(ITEMS.encode("cp1252"))
    return Project.create("P", game / "UI", game, projects_root=tmp_path / "projects")


def test_pending_new_controls_lists_only_files_with_new_ids_sorted() -> None:
    diffs = [FileDiff("Shop.xml", ["9"]), FileDiff("Bag.xml", [], ["1"]), FileDiff("Alpha.xml", ["3", "4"])]
    assert publishing.pending_new_controls(diffs) == ["Alpha.xml", "Shop.xml"]
    assert publishing.pending_new_controls([]) == []


def test_publish_texts_writes_the_game_keeps_a_copy_and_drops_reverted_edits(tmp_path: Path) -> None:
    project = _project(tmp_path)
    text_data.save_edits(project.root, {"T_Item.ini": {
        "539": TextEdit(["Runa Nova", "Uma runa."], ["Runa", "Uma runa."]),
        "538": TextEdit(["Pacote", "Abre."], ["Pacote", "Abre."]),  # voltou ao original
        "777": TextEdit(["x"], ["y"]),
    }})
    outcome = publishing.publish_texts(project, texts_disabled=False, now=datetime(2026, 11, 25, 10, 0, 0))
    assert outcome == publishing.TextsOutcome(1, ["T_Item.ini #777"], False)
    game_file = project.game_dir / "data" / "Translate" / "T_Item.ini"
    assert "539|Runa Nova|Uma runa.|" in game_file.read_bytes().decode("cp1252")
    assert (project.history_dir / "data" / "20261125-100000" / "T_Item.ini").read_bytes() == ITEMS.encode("cp1252")
    assert sorted(text_data.load_edits(project.root)["T_Item.ini"]) == ["539", "777"]


def test_publish_texts_without_edits_or_blocked_by_the_manifest(tmp_path: Path) -> None:
    project = _project(tmp_path)
    game_file = project.game_dir / "data" / "Translate" / "T_Item.ini"
    # Sem textos editados: nada a bloquear, mesmo com a função desligada.
    assert publishing.publish_texts(project, texts_disabled=True) == publishing.TextsOutcome()
    text_data.save_edits(project.root, {"T_Item.ini": {"539": TextEdit(["Runa Nova", "Uma runa."], ["Runa", "Uma runa."])}})
    assert publishing.publish_texts(project, texts_disabled=True) == publishing.TextsOutcome(0, [], True)
    assert game_file.read_bytes() == ITEMS.encode("cp1252")
    assert "539" in text_data.load_edits(project.root)["T_Item.ini"]  # a edição continua no projeto


def test_publish_texts_lets_disk_errors_reach_the_caller(tmp_path: Path) -> None:
    project = _project(tmp_path)
    text_data.save_edits(project.root, {"T_Item.ini": {"539": TextEdit(["Runa Nova", "Uma runa."], ["Runa", "Uma runa."])}})
    project.history_dir.mkdir(parents=True, exist_ok=True)
    (project.history_dir / "data").write_text("um arquivo no lugar da pasta", encoding="utf-8")
    with pytest.raises(OSError):
        publishing.publish_texts(project, texts_disabled=False)


def test_publish_project_sends_ui_and_texts(tmp_path: Path) -> None:
    project = _project(tmp_path)
    (project.ui_dir / "Radar.xml").write_text("<b/>", encoding="utf-8")
    text_data.save_edits(project.root, {"T_Item.ini": {"539": TextEdit(["Runa Nova", "Uma runa."], ["Runa", "Uma runa."])}})
    calls: list[tuple[int, int]] = []
    outcome = publishing.publish_project(project, texts_disabled=False, progress=lambda done, total: calls.append((done, total)))
    assert outcome.result.copied_to_ui == 1 and outcome.texts.changed == 1
    assert (project.game_dir / "UI" / "Radar.xml").read_text(encoding="utf-8") == "<b/>"
    assert calls


def test_needs_launcher_selection_only_when_running_with_another_ui(tmp_path: Path) -> None:
    def result(running: bool, previous: str) -> PublishResult:
        return PublishResult(tmp_path, 0, True, previous_selection=previous, launcher_running=running)

    assert publishing.needs_launcher_selection(result(True, "custom:Outra"), "Minha")
    assert not publishing.needs_launcher_selection(result(True, "custom:Minha"), "Minha")
    assert not publishing.needs_launcher_selection(result(False, "custom:Outra"), "Minha")


def test_text_index_overrides_keep_numeric_ids_with_text(tmp_path: Path) -> None:
    text_data.save_edits(tmp_path, {
        "T_TextIndex.ini": {"10": TextEdit(["Olá", "x"], ["Oi"]), "abc": TextEdit(["n"], []), "11": TextEdit([], ["a"])},
        "T_Item.ini": {"12": TextEdit(["Item"], [])},
    })
    assert text_data.text_index_overrides(tmp_path) == {10: "Olá"}
    assert text_data.text_index_overrides(tmp_path / "sem-projeto") == {}


def test_service_does_not_import_qt() -> None:
    code = "import sys, gf_ui_editor.publishing; print(any(name.startswith('PySide6') for name in sys.modules))"
    env = {**os.environ, "PYTHONPATH": str(Path(publishing.__file__).parents[1])}
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, check=True)
    assert result.stdout.strip() == "False"
