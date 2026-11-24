import io
import json
from datetime import date
from pathlib import Path

from gf_ui_editor import remote_manifest
from gf_ui_editor.remote_manifest import Manifest, parse


def _payload(**data) -> bytes:
    return json.dumps({"schema": 1, **data}).encode()


def test_messages_are_filtered_by_version_channel_date_and_seen() -> None:
    manifest = parse(_payload(messages=[
        {"id": "todos", "text": {"pt_BR": "Olá", "en_US": "Hi"}},
        {"id": "antigos", "text": "Atualize", "max_version": "0.5.9"},
        {"id": "novos", "text": "Novidade", "min_version": "0.6.0"},
        {"id": "beta", "text": "Teste a beta", "channel": "beta"},
        {"id": "estavel", "text": "Só estável", "channel": "stable"},
        {"id": "vencido", "text": "Passou", "until": "2026-11-01"},
        {"id": "sem-texto", "text": {}},
        {"text": "sem id"},
    ]))
    today = date(2026, 11, 24)
    ids = lambda **kw: [m.id for m in manifest.messages_for(today=today, **kw)]
    assert ids(version="0.6.0") == ["todos", "novos", "estavel"]
    assert ids(version="0.5.4") == ["todos", "antigos", "estavel"]
    assert ids(version="0.7.0-beta.1", beta=True) == ["todos", "novos", "beta"]
    assert ids(version="0.6.0", seen={"todos", "novos"}) == ["estavel"]
    hello = manifest.messages[0]
    assert hello.text("en_US") == "Hi" and hello.text("fr_FR") == "Olá"  # sem francês: português


def test_min_version_and_disabled_features() -> None:
    manifest = parse(_payload(min_version="0.6.0", disabled_features=["export_texts", 3]))
    assert manifest.needs_update("0.5.4") and manifest.needs_update("0.6.0-beta.2")
    assert not manifest.needs_update("0.6.0")
    assert manifest.is_disabled(remote_manifest.EXPORT_TEXTS)
    assert not manifest.is_disabled(remote_manifest.PUBLISH_TEXTS)
    assert not Manifest().needs_update("0.0.1")


def test_invalid_or_newer_manifests_are_ignored() -> None:
    assert parse(b"not json") is None
    assert parse(b"[]") is None
    assert parse(json.dumps({"schema": 2, "min_version": "9.0"}).encode()) is None  # formato mais novo
    manifest = parse(_payload(messages=[
        {"id": "link", "text": "x", "url": "http://inseguro"},
        {"id": "data", "text": "x", "until": "amanhã"},
        {"id": "nivel", "text": "x", "level": "explodir", "channel": "?"},
    ], extra_field_from_the_future=True))
    assert [m.id for m in manifest.messages] == ["link", "nivel"]
    assert manifest.messages[0].url is None  # só https
    assert manifest.messages[1].level == "info" and manifest.messages[1].channel == "all"


def test_fetch_returns_none_on_any_failure(monkeypatch) -> None:
    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(remote_manifest.urllib.request, "urlopen", lambda *a, **k: Response(_payload(min_version="0.6.0")))
    assert remote_manifest.fetch().min_version == "0.6.0"
    monkeypatch.setattr(remote_manifest.urllib.request, "urlopen", lambda *a, **k: Response(b"x" * (remote_manifest.SIZE_LIMIT + 1)))
    assert remote_manifest.fetch() is None

    def offline(*a, **k):
        raise OSError("sem internet")

    monkeypatch.setattr(remote_manifest.urllib.request, "urlopen", offline)
    assert remote_manifest.fetch() is None


def test_repository_manifest_is_valid() -> None:
    path = Path(__file__).resolve().parents[1] / "app-manifest.json"
    assert parse(path.read_bytes()) is not None


def test_message_links_only_open_official_channels() -> None:
    allowed = remote_manifest.allowed_link
    for url in (
        "https://stzlabs.com/pt/projects/gf-ui-editor",
        "https://www.stzlabs.com",
        "https://github.com/starzynhobr/gf-ui-editor/releases",
        "https://discord.com/invite/cTsJhtMzSe",
        "https://discord.gg/cTsJhtMzSe",
    ):
        assert allowed(url) == url
    for url in (
        "http://stzlabs.com",  # sem https
        "https://stzlabs.com.golpe.net/",  # domínio parecido
        "https://golpe.net/stzlabs.com",
        "https://github.com/outra-pessoa/repo",
        "https://discord.com/channels/123",
        "https://stzlabs.com@golpe.net/",  # usuário na URL
        "https://stzlabs.com:8443/",
        "javascript:alert(1)",
        None,
    ):
        assert allowed(url) is None
