from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from gf_ui_editor.preferences import MemoryStore, Preferences
from gf_ui_editor.ui_session import (
    Restart, WebStartup, allow_web_retry, migrate_ui_default, recover_web_start, restart_command,
    should_show_web_banner,
)
from gf_ui_editor.webview_runtime import resolve_ui


@pytest.mark.parametrize(
    ("values", "version", "requested", "available", "expected", "saved", "migrated"),
    [
        ({}, "0.8.0", None, True, ("web", False), "web", True),
        ({"ui_mode": "classic"}, "0.8.0", None, True, ("classic", False), "classic", True),
        ({"ui_mode": "web"}, "0.8.0", None, True, ("web", False), "web", True),
        ({"ui_default_migrated": True}, "0.8.1", None, True, ("classic", False), None, True),
        ({}, "0.8.0-beta.4", None, True, ("classic", False), None, False),
        ({}, "0.8.0", "classic", True, ("classic", False), "web", True),
        ({"ui_mode": "classic"}, "0.8.0", "web", True, ("web", False), "classic", True),
        ({}, "0.8.0", None, False, ("classic", True), "web", True),
    ],
)
def test_first_launch_ui(values, version, requested, available, expected, saved, migrated):
    prefs = Preferences(MemoryStore(values))
    migrate_ui_default(prefs, version)
    assert resolve_ui(requested, prefs.ui_mode, lambda: available) == expected
    assert prefs.get("ui_mode", None) == saved
    assert prefs.get("ui_default_migrated") is migrated


def test_user_choice_after_migration_is_kept():
    prefs = Preferences(MemoryStore())
    migrate_ui_default(prefs, "0.8.0")
    prefs.ui_mode = "classic"
    migrate_ui_default(prefs, "0.8.1")
    assert prefs.ui_mode == "classic"


@pytest.mark.parametrize(
    ("dismissed", "available", "fallback", "expected"),
    [
        ("", True, False, True),
        ("0.7.0", True, False, True),
        ("0.8.0", True, False, False),
        ("", True, True, False),
        ("", False, False, False),
    ],
)
def test_classic_banner_visibility(dismissed, available, fallback, expected):
    prefs = Preferences(MemoryStore({"web_banner_dismissed_version": dismissed}))
    assert should_show_web_banner(prefs, "0.8.0", web_available=available, fallback=fallback) is expected


def test_selecting_classic_persists_an_explicit_choice_without_restart(monkeypatch):
    from gf_ui_editor import app

    self = SimpleNamespace()
    monkeypatch.setattr(app, "prefs", Preferences(MemoryStore()))
    assert app.prefs.get("ui_mode", None) is None
    app.EditorWindow.set_ui_mode(self, "classic")
    migrate_ui_default(app.prefs, "0.8.0")
    assert app.prefs.ui_mode == "classic"


def test_classic_banner_buttons(monkeypatch):
    from PySide6.QtWidgets import QApplication, QPushButton

    from gf_ui_editor import app

    application = QApplication.instance() or QApplication([])
    calls = []
    window = app.EditorWindow(offer_web_banner=True)
    monkeypatch.setattr(window, "set_ui_mode", calls.append)
    buttons = {button.text(): button for button in window.home_page.findChildren(QPushButton)}
    buttons["Experimentar"].click()
    assert calls == ["web"]
    buttons["Agora não"].click()
    assert buttons["Agora não"].parentWidget().isHidden()
    assert app.prefs.get("web_banner_dismissed_version") == app.__version__
    window.deleteLater()
    application.processEvents()


@pytest.mark.parametrize("frozen", [False, True])
@pytest.mark.parametrize("dev", [False, True])
@pytest.mark.parametrize("has_path", [False, True])
def test_restart_command(tmp_path, frozen, dev, has_path):
    executable = "C:/Program Files/Editor.exe" if frozen else "C:/Python/python.exe"
    path = tmp_path / "UI teste" / "Bag.xml" if has_path else None
    command = restart_command(executable, frozen=frozen, dev=dev, path=path)
    expected = [executable] if frozen else [executable, "-m", "gf_ui_editor"]
    if dev:
        expected.append("--dev")
    if path is not None:
        expected.extend(("--", str(path.resolve())))
    assert command == expected


@pytest.mark.parametrize(
    ("requested", "saved", "failed", "recover"),
    [
        (None, "web", False, False),
        (None, "web", True, True),
        (None, "classic", True, False),
        ("web", "web", True, False),
        ("classic", "web", True, False),
    ],
)
def test_recover_web_start(requested, saved, failed, recover):
    prefs = Preferences(MemoryStore())
    prefs.ui_mode = saved
    if failed:
        WebStartup(prefs, "0.9.0").finish()
    assert recover_web_start(requested, prefs) is recover
    assert prefs.ui_mode == saved


def test_web_start_ready_clears_marker_and_prevents_timeout():
    prefs = Preferences(MemoryStore())
    attempt = WebStartup(prefs, "0.9.0")
    marker = prefs.get("web_starting")
    assert marker["version"] == "0.9.0"
    assert datetime.fromisoformat(marker["time"]).utcoffset() is not None

    attempt.ready()
    assert not prefs.get("web_starting")
    assert not attempt.expire()
    assert not attempt.finish()


def test_web_timeout_keeps_marker_even_if_page_replies_late():
    prefs = Preferences(MemoryStore())
    prefs.ui_mode = "web"
    attempt = WebStartup(prefs, "0.9.0")
    assert attempt.expire()
    attempt.ready()
    assert attempt.finish()
    assert not attempt.expire()
    assert recover_web_start(None, prefs)
    allow_web_retry(prefs)
    assert not recover_web_start(None, prefs)
    assert prefs.get("web_starting")
    WebStartup(prefs, "0.9.0")
    assert recover_web_start(None, prefs)


def test_timeout_command_forces_classic_and_requests_warning(tmp_path):
    path = tmp_path / "my project"
    assert restart_command("editor.exe", frozen=True, dev=False, path=path, classic_fallback=True) == [
        "editor.exe", "--ui", "classic", "--web-start-failed", "--", str(path),
    ]


@pytest.mark.parametrize(
    ("restart_now", "choice", "save_works", "expected"),
    [
        (True, None, False, True),
        (True, "Save", True, True),
        (True, "Save", False, False),
        (True, "Discard", False, True),
        (True, "Cancel", False, False),
        (False, "Discard", False, False),
    ],
)
def test_classic_switch_uses_close_confirmation(monkeypatch, restart_now, choice, save_works, expected):
    from PySide6.QtWidgets import QApplication, QMessageBox

    from gf_ui_editor import app

    application = QApplication.instance() or QApplication([])
    launches = []
    window = app.EditorWindow(restart=launches.append)
    path = Path("Bag.xml")
    window.document = SimpleNamespace(path=path, is_dirty=choice is not None)
    answers = []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: next(
        button for button in self.buttons() if button.text() == ("Reiniciar agora" if restart_now else "Depois")
    ))

    def ask(*args):
        answers.append(True)
        assert choice is not None
        return getattr(QMessageBox.StandardButton, choice)

    monkeypatch.setattr(QMessageBox, "question", ask)
    monkeypatch.setattr(window, "save_document", lambda: setattr(window.document, "is_dirty", not save_works))
    window.set_ui_mode("web")

    assert app.prefs.ui_mode == "web"
    assert bool(answers) is (restart_now and choice is not None)
    assert launches == ([Restart(path)] if expected else [])
    window.hide()
    window.deleteLater()
    application.processEvents()


def test_web_restart_releases_instance_before_spawning(monkeypatch, tmp_path):
    from gf_ui_editor import app, single_instance, web_shell, webview_runtime

    events = []
    path = tmp_path / "Bag.xml"
    instance = SimpleNamespace(close=lambda: events.append("release"))
    monkeypatch.setattr(webview_runtime, "resolve_ui", lambda *args: ("web", False))
    monkeypatch.setattr(single_instance, "acquire", lambda: instance)

    def run(language, *, startup, **kwargs):
        startup.ready()
        api = web_shell.WebApi(language, False)
        api._open_path = path
        api.close_window(restart=True)
        return api._restart

    monkeypatch.setattr(web_shell, "run", run)
    monkeypatch.setattr(app.subprocess, "Popen", lambda command, **kwargs: events.append(command))
    assert app.main(["--ui", "web", "--dev"]) == 0
    assert events[0] == "release"
    assert events[1][1:] == ["-m", "gf_ui_editor", "--dev", "--", str(path)]
