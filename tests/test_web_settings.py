"""Bloco 4 da interface web: Configurações, atualizador, manifesto remoto e instância única.

Os serviços (app_settings, app_updates, single_instance) e a ponte (SettingsApi, UpdatesApi)
são chamados direto, sem janela e sem rede (o updater e o manifesto são trocados por falsos).
"""
from __future__ import annotations

import threading
import time
from datetime import date
from pathlib import Path

import pytest

from gf_ui_editor import app_settings, app_updates, remote_manifest, single_instance, updater
from gf_ui_editor.preferences import MemoryStore, Preferences
from gf_ui_editor.release_notes import ReleaseNotes
from gf_ui_editor.web_api.projects import ProjectsApi
from gf_ui_editor.web_api.settings import SettingsApi
from gf_ui_editor.web_api.updates import UpdatesApi


def _prefs(**values) -> Preferences:
    prefs = Preferences(MemoryStore())
    for name, value in values.items():
        prefs.set(name, value)
    return prefs


def _notes(version: str, history: tuple[ReleaseNotes, ...] = ()) -> ReleaseNotes:
    return ReleaseNotes(
        version, "2026-11-20",
        {"pt_BR": {"new": [("Novo.", f"Chegou na {version}.")]}, "en_US": {"fixed": [("Fixed.", f"In {version}.")]}},
        history,
    )


def _info(version: str = "9.0.0", notes: ReleaseNotes | None = None, sha: str | None = "ab" * 32) -> updater.UpdateInfo:
    return updater.UpdateInfo(
        version=version, notes="texto da página", page_url=f"https://github.com/{updater.REPOSITORY}/releases/tag/v{version}",
        asset_name=f"GF-UI-Editor-Setup-{version}.exe",
        asset_url=f"https://github.com/{updater.REPOSITORY}/releases/download/v{version}/GF-UI-Editor-Setup-{version}.exe",
        sha256=sha, structured_notes=notes,
    )


# ---- app_settings ---------------------------------------------------------------------------

def test_snapshot_reads_the_shared_preferences(tmp_path: Path) -> None:
    (tmp_path / "client.ini").write_text("")
    prefs = _prefs(language="es_ES", ui_mode="web", navigation_style="photoshop", publish_on_save=True,
                   game_dir=str(tmp_path), game_resolution="1366x768", web_theme="light")
    state = app_settings.snapshot(prefs, tmp_path)
    values = state["values"]
    assert values["language"] == "es_ES" and values["ui_mode"] == "web" and values["web_theme"] == "light"
    assert values["navigation_style"] == "photoshop" and values["publish_on_save"] is True
    assert values["game_resolution"] == "1366x768" and values["background_mode"] == "builtin"
    assert state["game_dir_valid"] is True and state["game_dir_default"] == str(tmp_path)
    assert "1920x1080" in state["resolutions"]
    assert values["offer_project_on_open"] is True and values["auto_update_check"] is True


def test_snapshot_falls_back_on_unknown_values() -> None:
    prefs = _prefs(language="xx", ui_mode="??", navigation_style="vim", game_resolution="lixo", web_theme="neon", web_font="papyrus")
    values = app_settings.snapshot(prefs)["values"]
    assert (values["language"], values["ui_mode"], values["navigation_style"]) == ("pt_BR", "classic", "corel")
    assert values["game_resolution"] == "game" and values["web_theme"] == "dark" and values["web_font"] == "system"


def test_font_choice_is_validated() -> None:
    prefs = _prefs()
    assert app_settings.apply(prefs, "web_font", "plex") == "plex" and prefs.get("web_font") == "plex"
    try:
        app_settings.apply(prefs, "web_font", "papyrus")
    except ValueError:
        pass
    else:
        raise AssertionError("fonte desconhecida deveria ser recusada")


def test_beta_follows_the_installed_version_until_chosen(monkeypatch) -> None:
    monkeypatch.setattr(app_settings, "__version__", "1.0.0-beta.2")
    prefs = _prefs()
    assert app_settings.beta_enabled(prefs) is True
    app_settings.apply(prefs, "beta_updates", False)
    assert app_settings.beta_enabled(prefs) is False


def test_apply_validates_and_stores_in_the_classic_format(tmp_path: Path) -> None:
    store = MemoryStore()
    prefs = Preferences(store)
    app_settings.apply(prefs, "publish_on_save", True)
    assert store.values["publish_on_save"] == "true"  # flag: o mesmo texto que a clássica grava
    app_settings.apply(prefs, "navigation_style", "paintnet")
    assert prefs.navigation_style == "paintnet"
    assert app_settings.apply(prefs, "game_resolution", "1280 × 720") == "1280x720"
    app_settings.apply(prefs, "game_resolution", "off")
    for name, value in (("publish_on_save", "sim"), ("language", "de_DE"), ("navigation_style", "vim"),
                        ("game_resolution", "10x10"), ("background_mode", "custom"), ("nada", 1),
                        ("game_dir", str(tmp_path / "missing"))):
        with pytest.raises(ValueError):
            app_settings.apply(prefs, name, value)


def test_apply_game_dir_takes_the_game_root(tmp_path: Path) -> None:
    (tmp_path / "Launcher.ini").write_text("")
    (tmp_path / "UI").mkdir()
    prefs = _prefs()
    assert app_settings.apply(prefs, "game_dir", str(tmp_path / "UI")) == str(tmp_path)
    assert prefs.game_dir == str(tmp_path)
    assert app_settings.apply(prefs, "game_dir", "") == "" and prefs.game_dir == ""


def test_custom_background_needs_a_capture(tmp_path: Path) -> None:
    capture = tmp_path / "shot.png"
    capture.write_bytes(b"png")
    prefs = _prefs(game_background=str(capture))
    app_settings.apply(prefs, "background_mode", "custom")
    assert app_settings.snapshot(prefs)["has_custom_background"] is True


def test_review_and_reset() -> None:
    prefs = _prefs(skipped_update_version="9.9.9", web_layout={"left": 400}, files_section_order="all,layers,changed")
    prefs.manifest_seen = {"a", "b"}
    assert app_settings.review(prefs) == {"skipped_update": "9.9.9", "manifest_seen": 2, "layout": True}
    app_settings.reset(prefs, "skipped_update")
    app_settings.reset(prefs, "manifest_seen")
    assert app_settings.reset(prefs, "layout") == {"skipped_update": "", "manifest_seen": 0, "layout": False}
    assert prefs.get("web_layout") == {} and prefs.files_section_order == ""
    with pytest.raises(ValueError):
        app_settings.reset(prefs, "tudo")


# ---- app_updates: atualizador ---------------------------------------------------------------

def test_notes_payload_groups_skipped_versions() -> None:
    notes = _notes("0.9.0", (_notes("0.8.5"), _notes("0.8.0")))
    payload = app_updates.notes_payload(notes, "pt_BR", "0.8.0")
    assert payload["grouped"] is True
    assert [row["version"] for row in payload["releases"]] == ["0.9.0", "0.8.5"]
    assert payload["releases"][0]["sections"]["new"] == [["Novo.", "Chegou na 0.9.0."]]
    english = app_updates.notes_payload(notes, "fr_FR", None)  # sem francês: inglês
    assert english["grouped"] is False and english["releases"][0]["sections"]["fixed"] == [["Fixed.", "In 0.9.0."]]
    assert app_updates.notes_payload(None, "pt_BR", "0.8.0") == {"grouped": False, "releases": []}


def test_offer_payload(monkeypatch) -> None:
    monkeypatch.setattr(updater, "is_installed_build", lambda: True)
    payload = app_updates.offer_payload(_info(notes=_notes("9.0.0")), "pt_BR", "0.8.0")
    assert payload["version"] == "9.0.0" and payload["current"] == "0.8.0"
    assert payload["verified"] is True and payload["can_install"] is True
    assert payload["fallback_text"] == "texto da página" and payload["releases"][0]["version"] == "9.0.0"


def test_check_offers_and_respects_the_skipped_version() -> None:
    calls = []

    def check(include_prereleases):
        calls.append(include_prereleases)
        return _info("9.0.0")

    prefs = _prefs(beta_updates=True)
    session = app_updates.UpdateSession(prefs, check=check)
    assert session.check(manual=False).status == "offer" and session.offered.version == "9.0.0"
    assert calls == [True]
    session.skip("9.0.0")
    assert prefs.skipped_update_version == "9.0.0"
    assert session.check(manual=False).status == "skipped"  # a pulada só volta na manual
    assert session.check(manual=True).status == "offer"


def test_check_reports_latest_and_errors() -> None:
    def failing(include_prereleases):
        raise updater.UpdateError("sem rede")

    assert app_updates.UpdateSession(_prefs(), check=lambda include_prereleases: None).check(True).status == "latest"
    result = app_updates.UpdateSession(_prefs(), check=failing).check(True)
    assert (result.status, result.error) == ("error", "sem rede")


def test_automatic_check_once_a_day_and_only_when_enabled() -> None:
    calls = []
    now = [1_000_000.0]

    def check(include_prereleases):
        calls.append(now[0])
        return None

    prefs = _prefs()
    session = app_updates.UpdateSession(prefs, check=check, clock=lambda: now[0])
    assert session.automatic().status == "latest" and prefs.last_update_check == now[0]
    now[0] += 3600
    assert session.automatic().status == "not_due"
    now[0] += updater.CHECK_INTERVAL
    assert session.automatic().status == "latest"
    prefs.auto_update_check = False
    now[0] += updater.CHECK_INTERVAL * 2
    assert session.automatic().status == "not_due"
    assert len(calls) == 2


def test_install_downloads_and_launches_only_the_offered_version(monkeypatch, tmp_path: Path) -> None:
    launched = []
    monkeypatch.setattr(updater, "download_installer", lambda info, progress=None: (progress(5, 10), tmp_path / info.asset_name)[1])
    monkeypatch.setattr(updater, "launch_installer", launched.append)
    session = app_updates.UpdateSession(_prefs(), check=lambda include_prereleases: _info("9.0.0"))
    with pytest.raises(updater.UpdateError):
        session.install("9.0.0")
    session.check(True)
    seen = []
    session.install("9.0.0", lambda done, total: seen.append((done, total)))
    assert launched == [tmp_path / "GF-UI-Editor-Setup-9.0.0.exe"] and seen == [(5, 10)]


# ---- app_updates: manifesto -----------------------------------------------------------------

def _manifest(**extra) -> remote_manifest.Manifest:
    messages = tuple(
        remote_manifest.Message(id=f"m{index}", texts={"pt_BR": f"Aviso {index}", "en_US": f"Notice {index}"},
                                level="warning" if index == 0 else "info",
                                url="https://stzlabs.com/x" if index == 0 else None)
        for index in range(5)
    )
    return remote_manifest.Manifest(messages=messages, **extra)


def test_startup_notices_limit_language_and_seen() -> None:
    prefs = _prefs()
    prefs.manifest_seen = {"m1"}
    notices = app_updates.startup_notices(_manifest(min_version="9.0.0", disabled_features=frozenset({"export_texts"})),
                                          prefs, "en_US", "0.8.0")
    assert notices["needs_update"] is True and notices["min_version"] == "9.0.0"
    assert [item["id"] for item in notices["messages"]] == ["m0", "m2", "m3"]
    assert notices["messages"][0] == {"id": "m0", "level": "warning", "text": "Notice 0", "url": "https://stzlabs.com/x"}
    assert notices["disabled"] == ["export_texts"]
    app_updates.mark_message_seen(_manifest(), prefs, "m0")
    app_updates.mark_message_seen(_manifest(), prefs, "desconhecido")
    assert prefs.manifest_seen == {"m0", "m1"}


# ---- ponte ----------------------------------------------------------------------------------

class Api(ProjectsApi, SettingsApi, UpdatesApi):
    def __init__(self, prefs: Preferences | None = None):
        self.events: list = []
        self._language = "pt_BR"
        self.prefs = prefs or Preferences(MemoryStore())
        self._setup_projects(self.prefs, Path("missing/UI"), None, lambda *args: None)

    def _emit(self, event, payload=None):
        self.events.append((event, payload))


def test_bridge_settings_roundtrip() -> None:
    api = Api()
    state = api.settings_state()
    assert state["values"]["language"] == "pt_BR"
    state = api.settings_set("language", "fr_FR")
    assert state["values"]["language"] == "fr_FR" and api.prefs.language == "fr_FR" and api._language == "fr_FR"
    assert api.settings_set("offer_project_on_open", False)["values"]["offer_project_on_open"] is False
    api.prefs.skipped_update_version = "1.2.3"
    assert api.settings_reset("skipped_update")["review"]["skipped_update"] == ""
    with pytest.raises(ValueError):
        api.settings_set("ui_mode", "terminal")


def test_bridge_update_flow(monkeypatch) -> None:
    monkeypatch.setattr(updater, "check_for_update", lambda current=None, include_prereleases=False: _info("9.0.0", _notes("9.0.0")))
    monkeypatch.setattr(updater, "is_installed_build", lambda: False)
    opened = []
    from gf_ui_editor import desktop

    monkeypatch.setattr(desktop, "open_url", opened.append)
    api = Api()
    result = api.update_check(True)
    assert result["status"] == "offer" and result["offer"]["version"] == "9.0.0"
    assert result["offer"]["releases"][0]["sections"]["new"] == [["Novo.", "Chegou na 9.0.0."]]
    assert api.update_install("9.0.0") == {"opened_page": True}  # pelo código: abre a página
    assert opened == [_info("9.0.0").page_url]
    with pytest.raises(ValueError):
        api.update_install("8.0.0")
    api.update_skip("9.0.0")
    assert api.prefs.skipped_update_version == "9.0.0"
    assert api.update_auto_check()["status"] == "skipped"  # passou um dia (0), mas foi pulada


def test_bridge_install_reports_progress_and_closes(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(updater, "check_for_update", lambda current=None, include_prereleases=False: _info("9.0.0"))
    monkeypatch.setattr(updater, "is_installed_build", lambda: True)
    monkeypatch.setattr(updater, "download_installer", lambda info, progress=None: (progress(10, 10), tmp_path / "setup.exe")[1])
    monkeypatch.setattr(updater, "launch_installer", lambda path: None)
    closed = threading.Event()

    class Window:
        def destroy(self):
            closed.set()

    api = Api()
    api._window = Window()
    api.update_check(True)
    assert api.update_install("9.0.0") == {"installing": True}
    assert ("progress", {"label": "update", "done": 10, "total": 10}) in api.events
    assert closed.wait(3) and api._force_close is True


def test_bridge_manifest_notices(monkeypatch) -> None:
    monkeypatch.setattr(remote_manifest, "fetch", lambda *args, **kwargs: _manifest())
    api = Api()
    api.startup()
    notices = api.manifest_notices()
    assert [item["text"] for item in notices["messages"]] == ["Aviso 0", "Aviso 1", "Aviso 2"]
    api.manifest_mark_seen("m0")
    assert [item["id"] for item in api.manifest_notices()["messages"]] == ["m1", "m2", "m3"]


def test_manifest_is_not_fetched_when_checks_are_off(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(remote_manifest, "fetch", lambda *args, **kwargs: calls.append(1) or _manifest())
    api = Api(_prefs(auto_update_check=False))
    api.startup()
    assert api.manifest_notices()["messages"] == [] and calls == []


def test_disabled_features_reach_the_web_tools(monkeypatch) -> None:
    from gf_ui_editor.web_api.maintenance import MaintenanceApi

    class Tools(Api, MaintenanceApi):
        pass

    monkeypatch.setattr(remote_manifest, "fetch", lambda *args, **kwargs: remote_manifest.Manifest(
        disabled_features=frozenset({remote_manifest.EXPORT_TEXTS, remote_manifest.PUBLISH_TEXTS})))
    api = Tools()
    api.startup()
    api.manifest_notices()  # espera o manifesto
    assert api._manifest.is_disabled(remote_manifest.PUBLISH_TEXTS)
    project = type("P", (), {"game_dir": Path("."), "root": Path("missing-root")})()
    api._project = project
    monkeypatch.setattr("gf_ui_editor.text_data.load_edits", lambda root: {})
    assert api.texts_export_info()["disabled"] is True


def test_instance_message_opens_the_file_and_raises_the_window() -> None:
    api = Api()
    api._on_instance_message({"open": r"C:\jogo\UI\Bag.xml"})
    api._on_instance_message({"open": None})
    assert api.events == [("open_external", {"path": r"C:\jogo\UI\Bag.xml"})]


# ---- instância única ------------------------------------------------------------------------

def test_single_instance_hands_the_file_to_the_first_window(tmp_path: Path) -> None:
    address = single_instance.default_address() + f"-test-{time.monotonic_ns()}"
    if not single_instance.sys.platform == "win32":
        address = str(tmp_path / "gf.sock")
    first = single_instance.acquire(address)
    assert first is not None
    try:
        assert single_instance.acquire(address) is None  # já há uma janela
        received: list[dict] = []
        arrived = threading.Event()
        assert single_instance.send_open(tmp_path / "Bag.xml", address)  # chega antes de ligar: fica na fila
        first.on_message(lambda message: (received.append(message), arrived.set()))
        assert arrived.wait(3)
        assert received[0]["open"] == str((tmp_path / "Bag.xml").resolve())
    finally:
        first.close()
    again = single_instance.acquire(address)  # fechou: o próximo vira a janela principal
    assert again is not None
    again.close()
    assert single_instance.send_open(None, address) is False


def test_main_sends_to_the_open_window(monkeypatch, tmp_path: Path) -> None:
    from gf_ui_editor import app, web_shell, webview_runtime

    sent, ran = [], []
    monkeypatch.setattr(webview_runtime, "resolve_ui", lambda requested, saved, available: ("web", False))
    monkeypatch.setattr(single_instance, "acquire", lambda: None)
    monkeypatch.setattr(single_instance, "send_open", lambda path: sent.append(path) or True)
    monkeypatch.setattr(web_shell, "run", lambda *args, **kwargs: ran.append(kwargs) or 0)
    assert app.main([str(tmp_path / "Bag.xml"), "--ui", "web"]) == 0
    assert sent == [(tmp_path / "Bag.xml").resolve()] and ran == []


def test_main_opens_the_xml_and_serves_the_next_ones(monkeypatch, tmp_path: Path) -> None:
    from gf_ui_editor import app, web_shell, webview_runtime

    class Instance:
        closed = False

        def close(self):
            Instance.closed = True

    ran = []
    monkeypatch.setattr(webview_runtime, "resolve_ui", lambda requested, saved, available: ("web", False))
    monkeypatch.setattr(single_instance, "acquire", lambda: Instance())
    monkeypatch.setattr(web_shell, "run", lambda *args, **kwargs: ran.append(kwargs) or 0)
    assert app.main([str(tmp_path / "Bag.xml")]) == 0
    assert ran[0]["xml"] == (tmp_path / "Bag.xml").resolve() and isinstance(ran[0]["instance"], Instance)
    assert Instance.closed


def test_manifest_dates_still_filter(monkeypatch) -> None:
    """Sanidade: o filtro de data do manifesto continua valendo pela ponte nova."""
    old = remote_manifest.Message(id="old", texts={"pt_BR": "x"}, until=date(2000, 1, 1))
    manifest = remote_manifest.Manifest(messages=(old,))
    assert app_updates.startup_notices(manifest, _prefs(), "pt_BR")["messages"] == []
