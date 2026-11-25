import json

from gf_ui_editor import release_notes, updater
from gf_ui_editor import __version__


def test_bundled_notes_match_the_version_and_cover_every_language() -> None:
    from gf_ui_editor.i18n import LANGUAGES

    notes = release_notes.bundled()
    assert notes is not None and notes.version == __version__
    for language in LANGUAGES:
        sections = notes.for_language(language)
        assert sections and language in notes.notes
        # Mesma quantidade de itens em todos os idiomas.
        assert {k: len(v) for k, v in sections.items()} == {
            k: len(v) for k, v in notes.for_language("pt_BR").items()
        }


def test_language_fallback_and_invalid_input() -> None:
    notes = release_notes.parse(json.dumps({"version": "1", "notes": {"en_US": {"new": [["A.", "b"]]}}}))
    assert notes.for_language("fr_FR") == {"new": [("A.", "b")]}
    assert release_notes.parse("not json") is None
    assert release_notes.parse(json.dumps({"notes": {"en_US": {"new": "oops"}}})) is None
    assert release_notes.parse(json.dumps({"notes": []})) is None


def test_update_check_downloads_structured_notes(monkeypatch) -> None:
    base = "https://github.com/starzynhobr/gf-ui-editor/releases/download/v9.0.0/"
    release = {
        "tag_name": "v9.0.0",
        "body": "texto da página",
        "assets": [
            {"name": "GF-UI-Editor-Setup-9.0.0.exe", "browser_download_url": base + "GF-UI-Editor-Setup-9.0.0.exe"},
            {"name": "release-notes.json", "browser_download_url": base + "release-notes.json"},
        ],
    }
    payload = json.dumps({"version": "9.0.0", "notes": {"en_US": {"fixed": [["X.", "y"]]}}}).encode()

    class Response:
        def __init__(self, data):
            self.data = data

        def read(self, *_args):
            return self.data

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    responses = {updater.LATEST_RELEASE_API: json.dumps(release).encode(), base + "release-notes.json": payload}
    monkeypatch.setattr(updater, "_request", lambda url: Response(responses[url]))
    info = updater.check_for_update("0.1.0")
    assert info.structured_notes.for_language("pt_BR") == {"fixed": [("X.", "y")]}
    assert info.notes == "texto da página"

    # Sem o anexo, a atualização continua sendo oferecida, só com o texto da página.
    release["assets"].pop()
    responses[updater.LATEST_RELEASE_API] = json.dumps(release).encode()
    assert updater.check_for_update("0.1.0").structured_notes is None


def test_history_lists_every_version_newer_than_installed() -> None:
    notes = release_notes.parse(json.dumps({
        "version": "0.5.1",
        "notes": {"en_US": {"fixed": [["Fix.", "b"]]}},
        "history": [
            {"version": "0.5.0", "notes": {"en_US": {"new": [["New.", "b"]]}}},
            {"version": "0.4.1", "notes": {"en_US": {"new": [["Old.", "b"]]}}},
            "garbage",
        ],
    }))
    assert [release.version for release in notes.since("0.4.1")] == ["0.5.1", "0.5.0"]
    assert [release.version for release in notes.since("0.5.0")] == ["0.5.1"]
    bundled = release_notes.bundled()
    assert bundled.history, "a versão embutida deve trazer o histórico das anteriores"
    assert len(bundled.since("0.0.0", limit=100)) == len(bundled.history) + 1
    assert len(bundled.since("0.0.0")) <= 5  # a janela mostra no máximo 5 versões puladas


def test_history_orders_betas_before_their_stable_release() -> None:
    notes = release_notes.parse(json.dumps({
        "version": "0.7.0",
        "notes": {"en_US": {"new": [["Stable.", "b"]]}},
        "history": [
            {"version": "0.7.0-beta.2", "notes": {"en_US": {"new": [["Beta 2.", "b"]]}}},
            {"version": "0.7.0-beta.1", "notes": {"en_US": {"new": [["Beta 1.", "b"]]}}},
            {"version": "0.6.0", "notes": {"en_US": {"new": [["Old.", "b"]]}}},
        ],
    }))
    # Da estável para a estável: só a estável, que já resume as betas.
    assert [r.version for r in notes.since("0.6.0")] == ["0.7.0"]
    assert [r.version for r in notes.since("0.5.4")] == ["0.7.0", "0.6.0"]
    # Quem estava numa beta vê também as betas que pulou.
    assert [r.version for r in notes.since("0.7.0-beta.1")] == ["0.7.0", "0.7.0-beta.2"]
    # Canal beta saindo da estável para uma beta: as betas aparecem.
    beta = release_notes.parse(json.dumps({
        "version": "0.7.0-beta.2",
        "notes": {"en_US": {"new": [["Beta 2.", "b"]]}},
        "history": [{"version": "0.7.0-beta.1", "notes": {"en_US": {"new": [["Beta 1.", "b"]]}}}],
    }))
    assert [r.version for r in beta.since("0.6.0")] == ["0.7.0-beta.2", "0.7.0-beta.1"]
