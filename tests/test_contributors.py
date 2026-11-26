import json

from gf_ui_editor import about, contributors, remote_manifest


class FakePrefs:
    def __init__(self):
        self.data = {"contributors_cache": "", "contributors_rev": ""}

    def get(self, key):
        return self.data[key]

    def set(self, key, value):
        self.data[key] = value


def test_manifest_reads_contributors_rev() -> None:
    assert remote_manifest.parse(b'{"schema": 1, "contributors_rev": 3}').contributors_rev == 3
    for bad in ('"3"', "true", "-1", "null"):
        assert remote_manifest.parse(f'{{"schema": 1, "contributors_rev": {bad}}}'.encode()).contributors_rev is None


def test_validate_cleans_and_limits() -> None:
    people = contributors.validate([
        {"name": "Ana", "color": "red", "tags": ["ideas", "hack"], "items": [{"version": "0.8.0", "text": {"pt_BR": "x" * 500}}]},
        {"name": "", "items": []},
        "lixo",
    ])
    assert people == [{"name": "Ana", "color": contributors.NEUTRAL_COLOR, "tags": ["ideas"],
                       "items": [{"text": {"pt_BR": "x" * contributors.MAX_TEXT}, "version": "0.8.0"}]}]
    assert contributors.validate({"name": "x"}) is None
    assert contributors.validate([{"bad": 1}]) is None


def test_anonymous_keeps_contributions_without_the_name() -> None:
    [person] = contributors.validate([{"name": "Bia", "color": "#112233", "anonymous": True, "tags": ["qa"],
                                       "items": [{"version": "0.7.0", "text": {"pt_BR": "Testes"}}]}])
    assert person["name"] == "" and person["anonymous"] is True
    assert person["color"] == contributors.NEUTRAL_COLOR and person["tags"] == ["qa"]
    assert about.contributor_items(person, "pt_BR") == [("Testes", "0.7.0")]


def test_refresh_only_downloads_when_the_rev_changes() -> None:
    prefs = FakePrefs()
    calls = []

    def fetcher():
        calls.append(1)
        return [{"name": "Caio", "color": "#000000", "tags": []}]

    assert contributors.refresh(prefs, None, fetcher) is False
    assert contributors.refresh(prefs, 2, fetcher) is True
    assert contributors.refresh(prefs, 2, fetcher) is False
    assert len(calls) == 1
    assert about.load_contributors(prefs)[0]["name"] == "Caio"
    assert contributors.refresh(prefs, 3, lambda: None) is False  # falhou: mantém a lista guardada
    assert prefs.get("contributors_rev") == "2"


def test_bad_cache_falls_back_to_the_bundled_list() -> None:
    prefs = FakePrefs()
    prefs.set("contributors_cache", "{nao e json")
    assert about.load_contributors(prefs) == about.load_contributors()


def test_repository_copy_is_valid() -> None:
    """O contributors.json da raiz é o que o editor baixa: um push quebrado não pode passar."""
    root = contributors.BUNDLED_PATH.parents[3]
    repo = json.loads((root / "contributors.json").read_text(encoding="utf-8"))
    assert contributors.validate(repo)
