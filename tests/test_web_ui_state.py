from pathlib import Path

from gf_ui_editor import desktop
from gf_ui_editor.preferences import MemoryStore, Preferences
from gf_ui_editor.web_api.ui_state import AboutApi, ReleaseHistoryApi, TextureFileApi, UiStateApi


def test_layout_and_theme_are_saved_in_preferences() -> None:
    api = UiStateApi()
    api._prefs = Preferences(MemoryStore())
    assert api.ui_state() == {"layout": {}, "theme": "dark", "font": "system"}
    api.ui_set_layout({"left": 420, "bad": [1], "right": 300})
    api.ui_set_theme("light")
    api.ui_set_theme("neon")  # tema desconhecido: ignorado
    api.ui_set_font("geist")
    api.ui_set_font("comic-sans")  # fonte desconhecida: ignorada
    assert api.ui_state() == {"layout": {"left": 420, "right": 300}, "theme": "light", "font": "geist"}
    assert api._prefs.get("web_font") == "geist"


def test_unknown_saved_font_falls_back_to_system() -> None:
    api = UiStateApi()
    api._prefs = Preferences(MemoryStore())
    api._prefs.set("web_font", "papyrus")
    assert api.ui_state()["font"] == "system"


def test_release_history_lists_bundled_versions_newest_first() -> None:
    api = ReleaseHistoryApi()
    api._language = "en_US"
    history = api.release_history()
    versions = [release["version"] for release in history["releases"]]
    assert versions and versions[0] == history["version"]
    assert all("-" not in version for version in versions[1:]) or "-" in history["version"]  # estável: sem betas
    assert all(set(release["sections"]) == {"new", "improved", "fixed"} for release in history["releases"])


def test_about_info_lists_contributors_with_links() -> None:
    api = AboutApi()
    api._language = "en_US"
    info = api.about_info()
    assert info["discord"].startswith("https://discord.com/") and info["site"] == "https://stzlabs.com"
    assert info["contributors"] and all(person["name"] and person["items"] for person in info["contributors"])
    assert info["how_to_url"].endswith("/en/projects/gf-ui-editor")  # vídeo do "Como usar" (F1)
    api._language = "pt_BR"
    assert api.about_info()["how_to_url"].endswith("/pt/projects/gf-ui-editor")


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
