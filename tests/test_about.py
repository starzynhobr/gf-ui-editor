"""Testes das funções de apoio extraídas do app, sem dependência de Qt."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from gf_ui_editor import about


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1366X768", (1366, 768)),
        ("1920 × 1080", (1920, 1080)),
        (" 800  600 ", (800, 600)),
        ("100x10000", (100, 10000)),
        ("99x600", None),
        ("800x10001", None),
        ("800x600x32", None),
        ("800xaltura", None),
        ("", None),
    ],
)
def test_parse_resolution(text, expected) -> None:
    assert about.parse_resolution(text) == expected


def test_game_resolutions_keep_menu_order() -> None:
    assert about.GAME_RESOLUTIONS == (
        (800, 600),
        (1024, 768),
        (1280, 720),
        (1280, 1024),
        (1366, 768),
        (1600, 900),
        (1920, 1080),
        (2560, 1440),
    )


def test_text_editor_command_checks_both_program_files_locations(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    first_root = tmp_path / "Program Files"
    second_root = tmp_path / "Program Files (x86)"
    monkeypatch.setenv("ProgramFiles", str(first_root))
    monkeypatch.setenv("ProgramFiles(x86)", str(second_root))

    assert about.text_editor_command() == ("notepad.exe", "Bloco de Notas")

    second = second_root / "Notepad++" / "notepad++.exe"
    second.parent.mkdir(parents=True)
    second.touch()
    assert about.text_editor_command() == (str(second), "Notepad++")

    first = first_root / "Notepad++" / "notepad++.exe"
    first.parent.mkdir(parents=True)
    first.touch()
    assert about.text_editor_command() == (str(first), "Notepad++")


def test_load_contributors_preserves_json_and_handles_read_errors(tmp_path, monkeypatch) -> None:
    path = tmp_path / "contributors.json"
    monkeypatch.setattr(about, "CONTRIBUTORS_PATH", path)
    assert about.load_contributors() == []

    path.write_text("{", encoding="utf-8")
    assert about.load_contributors() == []

    contributors = [{"name": "João", "text": {"pt_BR": ["Revisão"]}}]
    path.write_text(json.dumps(contributors, ensure_ascii=False), encoding="utf-8")
    assert about.load_contributors() == contributors


def test_contributor_items_sorts_versions_and_keeps_order_within_a_version() -> None:
    person = {
        "items": [
            {"text": {"pt_BR": "Antiga"}, "version": "0.9"},
            {"text": {"en_US": "First", "pt_BR": "Primeira"}, "version": "0.10"},
            {"text": {"pt_BR": "Segunda"}, "version": "0.10"},
            {"text": {"fr_FR": "Autre"}},
            {"text": ""},
        ],
        "text": {"pt_BR": ["Legado"]},
    }

    assert about.contributor_items(person, "en_US") == [
        ("First", "0.10"),
        ("Segunda", "0.10"),
        ("Antiga", "0.9"),
        ("Autre", None),
    ]


def test_contributor_items_uses_legacy_text_when_no_current_items_are_valid() -> None:
    person = {"items": [None, {"text": ""}], "text": {"pt_BR": ["Um", "", 1, "Dois"]}}

    assert about.contributor_items(person, "en_US") == [("Um", None), ("Dois", None)]
    assert about.contributor_items({"text": "Único"}, "en_US") == [("Único", None)]


def test_about_imports_without_qt() -> None:
    code = (
        "import sys; import gf_ui_editor.about; "
        "assert not any(name == 'PySide6' or name.startswith('PySide6.') for name in sys.modules)"
    )
    src = Path(__file__).resolve().parents[1] / "src"
    result = subprocess.run(
        [sys.executable, "-S", "-c", code],
        env={**os.environ, "PYTHONPATH": str(src)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
