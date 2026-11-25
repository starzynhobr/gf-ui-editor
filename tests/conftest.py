"""Isola o QSettings dos testes: nada lê nem grava as preferências reais do usuário."""
import tempfile

import PySide6.QtCore as QtCore

_SETTINGS_DIR = tempfile.mkdtemp(prefix="gf-ui-editor-tests-")
QtCore.QSettings.setDefaultFormat(QtCore.QSettings.Format.IniFormat)
QtCore.QSettings.setPath(QtCore.QSettings.Format.IniFormat, QtCore.QSettings.Scope.UserScope, _SETTINGS_DIR)


class _IsolatedQSettings(QtCore.QSettings):
    """QSettings("Local", "GF UI Editor") ignora o setDefaultFormat e vai direto ao Registro.

    Aqui o construtor com organização/aplicativo vira o INI da pasta temporária. Precisa
    ser trocado antes de o editor importar o QSettings (o conftest carrega primeiro).
    """

    def __init__(self, *args, **kwargs):
        # QSettings(arquivo, formato) já é explícito; só o (organização, aplicativo) é desviado.
        if args and isinstance(args[0], str) and not (len(args) > 1 and isinstance(args[1], QtCore.QSettings.Format)):
            super().__init__(QtCore.QSettings.Format.IniFormat, QtCore.QSettings.Scope.UserScope, *args, **kwargs)
        else:
            super().__init__(*args, **kwargs)


QtCore.QSettings = _IsolatedQSettings
QSettings = _IsolatedQSettings
assert not QSettings("Local", "GF UI Editor").fileName().startswith("\\HKEY"), "QSettings dos testes no Registro"

import pytest


@pytest.fixture(autouse=True)
def _fresh_settings():
    """Cada teste parte das mesmas preferências, sem a moldura do jogo (quem precisa liga)."""
    settings = QSettings("Local", "GF UI Editor")
    assert settings.fileName().startswith(_SETTINGS_DIR.replace("\\", "/")[:3]) and "HKEY" not in settings.fileName()
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


@pytest.fixture(autouse=True)
def _close_databases():
    """Fecha os SQLite abertos no teste: no Windows um banco aberto prende a pasta temporária."""
    yield
    from gf_ui_editor import storage

    storage.close_all()



def pytest_unconfigure(config):
    """Fecha as janelas e espera as threads do Qt antes de o Python sair: no CI do Windows,
    desmontar o Qt com elas ainda vivas derruba o processo depois dos testes."""
    from PySide6.QtCore import QThreadPool
    from PySide6.QtWidgets import QApplication

    application = QApplication.instance()
    if application is None:
        return
    for widget in application.topLevelWidgets():
        widget.hide()  # close() pediria "Descartar alterações?" e travaria
        widget.deleteLater()
    application.processEvents()
    QThreadPool.globalInstance().waitForDone(5000)
    application.processEvents()
