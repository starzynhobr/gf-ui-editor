from pathlib import Path

from gf_ui_editor import desktop
from gf_ui_editor.preferences import MemoryStore, Preferences
from gf_ui_editor.web_api.ui_state import AboutApi, TextureFileApi, UiStateApi


def test_layout_and_theme_are_saved_in_preferences() -> None:
    api = UiStateApi()
    api._prefs = Preferences(MemoryStore())
    assert api.ui_state() == {"layout": {}, "theme": "dark"}
    api.ui_set_layout({"left": 420, "bad": [1], "right": 300})
    api.ui_set_theme("light")
    api.ui_set_theme("neon")  # tema desconhecido: ignorado
    assert api.ui_state() == {"layout": {"left": 420, "right": 300}, "theme": "light"}


def test_about_info_lists_contributors_with_links() -> None:
    api = AboutApi()
    api._language = "en_US"
    info = api.about_info()
    assert info["discord"].startswith("https://discord.com/") and info["site"] == "https://stzlabs.com"
    assert info["contributors"] and all(person["name"] and person["items"] for person in info["contributors"])


def test_open_texture_file_opens_existing_dds_only(tmp_path: Path, monkeypatch) -> None:
    opened = []
    monkeypatch.setattr(desktop, "open_path", lambda path: opened.append(path))
    (tmp_path / "main.dds").write_bytes(b"DDS ")
    xml = tmp_path / "BasicChar.xml"
    api = TextureFileApi()
    assert api.open_texture_file(str(xml), "main.dds") == "ok" and opened == [(tmp_path / "main.dds").resolve()]
    assert api.open_texture_file(str(xml), "falta.dds") == "missing"
    assert api.open_texture_file(str(xml), "BasicChar.xml") == "missing"  # só texturas

    def fail(_path):
        raise OSError("sem programa")

    monkeypatch.setattr(desktop, "open_path", fail)
    assert api.open_texture_file(str(xml), "main.dds") == "failed"
