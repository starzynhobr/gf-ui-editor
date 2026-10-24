"""Isola o QSettings dos testes: nada lê nem grava as preferências reais do usuário."""
import tempfile

from PySide6.QtCore import QSettings

_SETTINGS_DIR = tempfile.mkdtemp(prefix="gf-ui-editor-tests-")
QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, _SETTINGS_DIR)

import pytest


@pytest.fixture(autouse=True)
def _fresh_settings():
    """Cada teste parte das mesmas preferências, sem a moldura do jogo (quem precisa liga)."""
    settings = QSettings("Local", "GF UI Editor")
    settings.clear()
    settings.setValue("game_resolution", "off")
    settings.sync()
    yield


@pytest.fixture(autouse=True)
def _no_real_game_folder(monkeypatch, tmp_path_factory):
    """XML avulso cai na pasta do jogo instalada; nos testes ela não pode existir."""
    import gf_ui_editor.app as app

    import gf_ui_editor.project as project

    missing = tmp_path_factory.mktemp("no-game")
    monkeypatch.setattr(app, "DEFAULT_UI_DIRECTORY", missing / "missing" / "UI")
    monkeypatch.setattr(project, "PROJECTS_ROOT", missing / "projects")
