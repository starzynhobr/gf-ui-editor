"""Preferências tipadas sobre um armazenamento qualquer: sem Qt."""
import os
from pathlib import Path
import subprocess
import sys

import pytest

from gf_ui_editor import preferences
from gf_ui_editor.preferences import KEYS, PREFIXES, MemoryStore, Preferences


def _prefs(**values: object) -> tuple[Preferences, MemoryStore]:
    store = MemoryStore({key.replace("__", "/"): value for key, value in values.items()})
    return Preferences(store), store


def test_every_key_reads_its_default_when_missing() -> None:
    prefs, _store = _prefs()
    for name, key in KEYS.items():
        assert prefs.get(name) == key.default, name
    assert prefs.language == "pt_BR" and prefs.navigation_style == "corel" and prefs.text_mode == "off"
    assert prefs.game_resolution == "game" and prefs.background_mode == "builtin"
    assert prefs.auto_update_check is True and prefs.offer_project_on_open is True
    assert prefs.publish_on_save is False and prefs.publish_confirmed is False and prefs.beta_updates is False
    assert prefs.brand_seen is False and prefs.last_update_check == 0.0
    assert prefs.tree_hidden_columns == ["2"] and prefs.manifest_seen == set()
    assert prefs.last_file("UI-Hero") == "" and prefs.root_mode("BasicChar.xml") == "auto"


def test_context_default_replaces_the_declared_one() -> None:
    prefs, _store = _prefs()
    assert prefs.get("background_mode", "custom") == "custom"
    assert prefs.get("beta_updates", True) is True
    prefs.background_mode = "none"
    prefs.beta_updates = False
    assert prefs.get("background_mode", "custom") == "none"
    assert prefs.get("beta_updates", True) is False


def test_flags_are_written_as_true_false_text() -> None:
    prefs, store = _prefs()
    for name in ("publish_on_save", "publish_confirmed", "offer_project_on_open", "auto_update_check", "beta_updates"):
        setattr(prefs, name, True)
        assert store.values[name] == "true" and getattr(prefs, name) is True
        setattr(prefs, name, False)
        assert store.values[name] == "false" and getattr(prefs, name) is False
    prefs.set("publish_on_save", 1)  # o toggled do Qt pode mandar qualquer verdadeiro
    assert store.values["publish_on_save"] == "true"


def test_bool_is_written_as_bool_and_read_like_qsettings() -> None:
    prefs, store = _prefs()
    prefs.brand_seen = True
    assert store.values["brand_seen"] is True and prefs.brand_seen is True
    for raw, expected in (("true", True), ("false", False), ("0", False), ("", False), ("1", True), (0, False), (2, True)):
        store.values["brand_seen"] = raw
        assert prefs.brand_seen is expected, raw


def test_float_json_and_text_round_trip() -> None:
    prefs, store = _prefs()
    prefs.last_update_check = 1764000000.5
    assert store.values["last_update_check"] == 1764000000.5
    store.values["last_update_check"] = "1764000000.5"  # o Registro devolve texto
    assert prefs.last_update_check == 1764000000.5
    prefs.manifest_seen = {"b", "a"}
    assert store.values["manifest_seen"] == '["a", "b"]' and prefs.manifest_seen == {"a", "b"}
    prefs.tree_hidden_columns = ["0", "2"]
    assert store.values["tree_hidden_columns"] == "0,2" and prefs.tree_hidden_columns == ["0", "2"]
    prefs.tree_hidden_columns = []
    assert store.values["tree_hidden_columns"] == "" and prefs.tree_hidden_columns == [""]
    prefs.game_resolution = "1920x1080"
    prefs.files_section_order = "all,layers,changed"
    prefs.files_section_heights = '{"layers": 150}'
    prefs.game_dir = r"C:\Jogo"
    assert prefs.game_resolution == "1920x1080" and prefs.files_section_order == "all,layers,changed"
    assert prefs.files_section_heights == '{"layers": 150}' and prefs.game_dir == r"C:\Jogo"
    assert store.values["game_dir"] == r"C:\Jogo"


def test_corrupt_or_wrong_type_values_fall_back_to_the_default() -> None:
    prefs, _store = _prefs(
        publish_on_save="sim", auto_update_check="yes", offer_project_on_open=3,
        last_update_check="ontem", manifest_seen="{not json", brand_seen=[1],
    )
    assert prefs.publish_on_save is False
    assert prefs.auto_update_check is True
    assert prefs.offer_project_on_open is True
    assert prefs.last_update_check == 0.0
    assert prefs.manifest_seen == set()
    assert prefs.brand_seen is False
    prefs.store.values["manifest_seen"] = '{"a": 1}'  # JSON válido, tipo errado
    assert prefs.manifest_seen == set()
    prefs.store.values["manifest_seen"] = '["a", 1, ["x"]]'  # só os IDs em texto contam
    assert prefs.manifest_seen == {"a"}
    prefs.store.values["last_update_check"] = None
    assert prefs.last_update_check == 0.0


def test_text_values_of_other_types_are_read_as_text() -> None:
    # Igual ao str(settings.value(...)) de antes.
    prefs, _store = _prefs(language=5, last_project=Path("C:/p"))
    assert prefs.language == "5" and prefs.last_project == str(Path("C:/p"))


def test_suffixed_keys() -> None:
    prefs, store = _prefs(last_file__Old="BasicChar.xml")
    assert prefs.last_file("Old") == "BasicChar.xml"
    prefs.set_last_file("New", "skin/Target.xml")
    prefs.remove_last_file("Old")
    assert store.values == {"last_file/New": "skin/Target.xml"}
    prefs.set_root_mode("basicchar.xml", "placed")
    assert store.values["root_mode/basicchar.xml"] == "placed"
    assert prefs.root_mode("basicchar.xml") == "placed" and prefs.root_mode("target.xml") == "auto"
    assert prefs.get("last_file/New") == "skin/Target.xml"
    assert set(PREFIXES) == {"last_file", "root_mode"}


def test_remove_and_unknown_keys() -> None:
    prefs, store = _prefs(last_project="C:/p")
    prefs.remove("last_project")
    assert "last_project" not in store.values and prefs.last_project == ""
    prefs.remove("last_project")  # remover o que não existe não falha
    with pytest.raises(KeyError):
        prefs.get("nao_existe")
    with pytest.raises(KeyError):
        prefs.set("outra/coisa", "x")


def test_preferences_do_not_import_qt() -> None:
    code = "import sys, gf_ui_editor.preferences; print(any(name.startswith('PySide6') for name in sys.modules))"
    env = {**os.environ, "PYTHONPATH": str(Path(preferences.__file__).parents[1])}
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, check=True)
    assert result.stdout.strip() == "False"
