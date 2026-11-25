import hashlib
import io
import json
from pathlib import Path

import pytest

from gf_ui_editor import updater


RELEASE = {
    "tag_name": "v0.3.0",
    "body": "## O que mudou",
    "html_url": "https://github.com/starzynhobr/gf-ui-editor/releases/tag/v0.3.0",
    "assets": [
        {
            "name": "GF-UI-Editor-Setup.exe",
            "browser_download_url": "https://github.com/starzynhobr/gf-ui-editor/releases/download/v0.3.0/GF-UI-Editor-Setup.exe",
            "digest": "sha256:aaaa",
        },
        {
            "name": "GF-UI-Editor-Setup-0.3.0.exe",
            "browser_download_url": "https://github.com/starzynhobr/gf-ui-editor/releases/download/v0.3.0/GF-UI-Editor-Setup-0.3.0.exe",
            "digest": "sha256:" + hashlib.sha256(b"installer").hexdigest(),
        },
    ],
}


class FakeResponse(io.BytesIO):
    def __init__(self, payload: bytes):
        super().__init__(payload)
        self.headers = {"Content-Length": str(len(payload))}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_versions() -> None:
    assert updater.is_newer("0.10.0", "0.9.9")
    assert updater.is_newer("v0.2.1", "0.2.0")
    assert not updater.is_newer("0.2.0", "0.2.0")


def test_release_parsing_prefers_versioned_asset() -> None:
    info = updater.release_from_json(RELEASE)
    assert info.version == "0.3.0"
    assert info.asset_name == "GF-UI-Editor-Setup-0.3.0.exe"
    assert info.sha256 == hashlib.sha256(b"installer").hexdigest()


def test_check_and_download(monkeypatch, tmp_path: Path) -> None:
    responses = {
        updater.LATEST_RELEASE_API: json.dumps(RELEASE).encode(),
        RELEASE["assets"][1]["browser_download_url"]: b"installer",
    }
    monkeypatch.setattr(updater, "_request", lambda url: FakeResponse(responses[url]))
    info = updater.check_for_update("0.2.0")
    assert info is not None
    assert updater.check_for_update("0.3.0") is None
    path = updater.download_installer(info, tmp_path)
    assert path.read_bytes() == b"installer"


def test_download_rejects_wrong_hash(monkeypatch, tmp_path: Path) -> None:
    info = updater.release_from_json(RELEASE)
    monkeypatch.setattr(updater, "_request", lambda url: FakeResponse(b"tampered"))
    with pytest.raises(updater.UpdateError):
        updater.download_installer(info, tmp_path)
    assert not (tmp_path / info.asset_name).exists()


def test_rate_limited_api_falls_back_to_release_download(monkeypatch) -> None:
    import urllib.error

    notes = {"version": "0.3.0", "notes": {"pt_BR": {"new": [["Algo novo.", "Detalhe."]]}}}

    def fake_request(url):
        if url == updater.LATEST_RELEASE_API:
            raise urllib.error.HTTPError(url, 403, "rate limit exceeded", {}, None)
        assert url == updater.LATEST_NOTES_DOWNLOAD
        return FakeResponse(json.dumps(notes).encode())

    monkeypatch.setattr(updater, "_request", fake_request)
    info = updater.check_for_update("0.2.0")
    assert info is not None
    assert info.version == "0.3.0"
    assert info.asset_url.endswith("/releases/download/v0.3.0/GF-UI-Editor-Setup-0.3.0.exe")
    assert info.structured_notes is not None
    assert updater.check_for_update("0.3.0") is None


def test_prerelease_versions_come_before_the_final_release() -> None:
    order = ["0.5.4", "0.6.0-beta.1", "0.6.0-beta.2", "0.6.0-rc.1", "0.6.0", "0.6.1", "0.7.0-beta.1", "0.10.0"]
    assert sorted(reversed(order), key=updater.parse_version) == order
    assert updater.is_newer("0.6.0", "0.6.0-beta.3")  # quem está na beta recebe a estável
    assert not updater.is_newer("0.6.0-beta.1", "0.6.0")
    assert updater.parse_version("v0.6") == updater.parse_version("0.6.0")
    assert updater.is_prerelease("v0.7.0-beta.1") and not updater.is_prerelease("0.6.0")


def _release(tag: str, *, prerelease: bool = False, draft: bool = False) -> dict:
    version = tag.lstrip("v")
    return {
        "tag_name": tag,
        "prerelease": prerelease,
        "draft": draft,
        "body": "",
        "html_url": f"https://github.com/starzynhobr/gf-ui-editor/releases/tag/{tag}",
        "assets": [{
            "name": f"GF-UI-Editor-Setup-{version}.exe",
            "browser_download_url": f"https://github.com/starzynhobr/gf-ui-editor/releases/download/{tag}/GF-UI-Editor-Setup-{version}.exe",
        }],
    }


def test_beta_channel_picks_the_newest_release_including_betas(monkeypatch) -> None:
    releases = [
        _release("v0.8.0-beta.1", draft=True),  # rascunho: nunca é oferecido
        _release("v0.7.0-beta.2", prerelease=True),
        _release("v0.7.0-beta.1", prerelease=True),
        _release("v0.6.0"),
    ]
    responses = {updater.RELEASES_API: json.dumps(releases).encode(), updater.LATEST_RELEASE_API: json.dumps(releases[3]).encode()}
    monkeypatch.setattr(updater, "_request", lambda url: FakeResponse(responses[url]))
    monkeypatch.setattr(updater, "fetch_structured_notes", lambda info: None)
    assert updater.check_for_update("0.6.0", include_prereleases=True).version == "0.7.0-beta.2"
    assert updater.check_for_update("0.6.0") is None  # canal estável ignora as betas
    assert updater.check_for_update("0.5.4").version == "0.6.0"
    # A estável chega para quem está na beta, com ou sem a opção ligada.
    releases.insert(0, _release("v0.7.0"))
    responses[updater.RELEASES_API] = json.dumps(releases).encode()
    responses[updater.LATEST_RELEASE_API] = json.dumps(releases[0]).encode()
    assert updater.check_for_update("0.7.0-beta.2", include_prereleases=True).version == "0.7.0"
    assert updater.check_for_update("0.7.0-beta.2").version == "0.7.0"


def test_automatic_check_runs_at_most_once_a_day() -> None:
    assert updater.due_for_check(0.0, 1_000_000.0)  # nunca verificou
    assert not updater.due_for_check(1_000_000.0, 1_000_000.0 + 24 * 3600 - 1)
    assert updater.due_for_check(1_000_000.0, 1_000_000.0 + 24 * 3600)
    assert updater.due_for_check(2_000_000.0, 1_000_000.0) is False  # relógio voltou: espera


def test_beta_channel_default_follows_the_installed_version() -> None:
    assert updater.beta_default("0.7.0-beta.3") is True
    assert updater.beta_default("0.7.0-rc.1") is True
    assert updater.beta_default("0.7.0") is False


def test_skipped_version_is_offered_again_only_when_checking_by_hand() -> None:
    assert not updater.should_offer("0.8.0", "0.8.0", manual=False)
    assert updater.should_offer("0.8.0", "0.8.0", manual=True)
    assert updater.should_offer("0.8.1", "0.8.0", manual=False)
    assert updater.should_offer("0.8.0", "", manual=False)


def test_updater_and_manifest_do_not_import_qt() -> None:
    import os
    import subprocess
    import sys

    code = (
        "import sys, gf_ui_editor.updater, gf_ui_editor.remote_manifest; "
        "print(any(name.startswith('PySide6') for name in sys.modules))"
    )
    env = {**os.environ, "PYTHONPATH": str(Path(updater.__file__).parents[1])}
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, check=True)
    assert result.stdout.strip() == "False"
