"""O adaptador do QSettings grava no mesmo formato de até a 0.7.0 e lê o que ela gravou."""
from PySide6.QtCore import QSettings

from gf_ui_editor.app import QtPreferenceStore, prefs
from gf_ui_editor.preferences import Preferences


def _settings() -> QSettings:
    return QSettings("Local", "GF UI Editor")


def test_values_written_through_the_adapter_match_the_old_format() -> None:
    prefs.publish_on_save = True
    prefs.auto_update_check = False
    prefs.brand_seen = True
    prefs.last_update_check = 1764000000.5
    prefs.manifest_seen = {"b", "a"}
    prefs.tree_hidden_columns = ["0", "2"]
    prefs.set_last_file("UI-Hero", "skin/Target.xml")
    prefs.set_root_mode("basicchar.xml", "placed")
    settings = _settings()
    assert settings.value("publish_on_save") == "true"
    assert settings.value("auto_update_check") == "false"
    assert settings.value("brand_seen", False, type=bool) is True
    assert float(settings.value("last_update_check")) == 1764000000.5
    assert settings.value("manifest_seen") == '["a", "b"]'
    assert settings.value("tree_hidden_columns") == "0,2"
    assert settings.value("last_file/UI-Hero") == "skin/Target.xml"
    assert settings.value("root_mode/basicchar.xml") == "placed"
    prefs.remove_last_file("UI-Hero")
    assert not _settings().contains("last_file/UI-Hero")


def test_values_written_by_the_old_code_are_read_the_same() -> None:
    settings = _settings()
    settings.setValue("publish_confirmed", "true")
    settings.setValue("offer_project_on_open", "false")
    settings.setValue("brand_seen", True)
    settings.setValue("last_update_check", 1764000000.25)
    settings.setValue("manifest_seen", '["x"]')
    settings.setValue("game_resolution", "1366x768")
    settings.setValue("root_mode/radar.xml", "centered")
    settings.sync()
    fresh = Preferences(QtPreferenceStore())
    assert fresh.publish_confirmed is True and fresh.offer_project_on_open is False
    assert fresh.brand_seen is True and fresh.last_update_check == 1764000000.25
    assert fresh.manifest_seen == {"x"} and fresh.game_resolution == "1366x768"
    assert fresh.root_mode("radar.xml") == "centered"
    assert fresh.language == "pt_BR"  # ausente: padrão
