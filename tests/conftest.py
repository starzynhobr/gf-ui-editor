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
