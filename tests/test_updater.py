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
