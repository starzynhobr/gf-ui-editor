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
