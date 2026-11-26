"""ResolutionsApi (Exportar para várias resoluções) chamada direto, sem janela."""
from __future__ import annotations

import json
from pathlib import Path
import zipfile

import pytest

from gf_ui_editor import project as project_module
from gf_ui_editor.preferences import MemoryStore, Preferences
from gf_ui_editor.web_api.projects import ProjectsApi
from gf_ui_editor.web_api.resolutions import ResolutionsApi

TEXTURE = '<BackGroundMap BGmap="main.dds"><NorUV NorUVLeft="0" NorUVTop="0" NorUVWidth="8" NorUVHeight="8"/></BackGroundMap>'


def window(root: str, children: str = "") -> bytes:
    return (
        f'<Root_Node><Style CtrlType="268435456"/><BaseWndProperty WindowID="1" {root}>'
        f'<Container_Node Child_Cnt="{children.count("<BaseWndProperty")}">{children}</Container_Node>'
        "</BaseWndProperty></Root_Node>"
    ).encode("ascii")


class Api(ProjectsApi, ResolutionsApi):
    def __init__(self, tmp_path: Path, answers: list | None = None, game: Path | None = None):
        self.events: list[tuple[str, object]] = []
        self.answers = list(answers or [])
        self.prefs = Preferences(MemoryStore())
        self._setup_projects(self.prefs, (game or tmp_path / "missing") / "UI", None, self._answer)

    def _answer(self, kind, directory, file_types, save_name):
        return self.answers.pop(0) if self.answers else None

    def _emit(self, event, payload=None):
        self.events.append((event, payload))

    def _fetch_manifest(self):
        pass


@pytest.fixture
def game(tmp_path: Path) -> Path:
    game = tmp_path / "game"
    ui = game / "UI"
    ui.mkdir(parents=True)
    # O jogo põe a raiz do ElfAttack no canto inferior direito; o conteúdo foi solto no meio.
    (ui / "ElfAttack.xml").write_bytes(window(
        'WindowLeft="695" WindowTop="243" WindowHeight="0" WindowWidth="0"',
        f'<Style CtrlType="268435456"/><BaseWndProperty WindowID="10000" WindowHeight="295" WindowWidth="46">{TEXTURE}</BaseWndProperty>',
    ))
    (ui / "Menu.xml").write_bytes(window(f'WindowHeight="740" WindowWidth="118">{TEXTURE}<X a="1"/', ""))
    (ui / "main.dds").write_bytes(b"DDS base")
    (game / "Launcher.ini").write_text("[Config]\nUI=default\n", encoding="latin-1")
    return game


@pytest.fixture
def projects(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "projects"
    monkeypatch.setattr(project_module, "PROJECTS_ROOT", root)
    return root


def open_project(api: Api, game: Path) -> Path:
    form = {"name": "Red", "source": str(game / "UI"), "game_dir": str(game), "include_assets": False, "publish_folder": ""}
    return Path(api.create_project(form)["state"]["project"]["root"])


def test_info_uses_the_preview_resolution_and_the_common_four(tmp_path, game, projects):
    api = Api(tmp_path, game=game)
    open_project(api, game)
    api.prefs.game_resolution = "1600x900"
    info = api.resolutions_info()
    assert info["base"] == [1600, 900] and info["project"] == "Red"
    assert info["targets"] == [[1366, 768], [1600, 900], [1920, 1080], [2560, 1440]]
    assert "Menu.xml" in info["hud"]
    api.resolutions_set_choice([1366, 768], ["1920x1080", [2560, 1440]])
    info = api.resolutions_info()
    assert info["base"] == [1366, 768] and info["targets"] == [[1920, 1080], [2560, 1440]]


def test_plan_adjust_and_export(tmp_path, game, projects):
    out = tmp_path / "out"
    api = Api(tmp_path, [str(out)], game=game)
    root = open_project(api, game)
    plan = api.resolutions_plan([1366, 768], [[1366, 768], [1920, 1080]])
    same, big = plan["targets"]
    assert same["files"] == [] and big["files"] == ["ElfAttack.xml"]
    elf = next(item for item in big["windows"] if item["file"] == "ElfAttack.xml")
    assert elf["moves"] and elf["kind"] == "game"
    piece = elf["pieces"][0]
    assert piece["rule"] == ["middle", "middle"] and not piece["adjusted"]
    menu = next(item for item in big["windows"] if item["file"] == "Menu.xml")
    assert menu["hud"] and not menu["moves"] and menu["pieces"][0]["rule"] == ["game", "game"]

    scenes = api.resolutions_scenes([1366, 768], [1920, 1080], ["ElfAttack.xml", "Menu.xml"])
    assert sorted(scene["name"] for scene in scenes) == ["ElfAttack.xml", "Menu.xml"]
    elf_scene = next(scene for scene in scenes if scene["name"] == "ElfAttack.xml")["scene"]
    screen = elf_scene["preview"]["screen"]
    content = elf_scene["elements"][1]["geometry"]
    assert (content[0] - screen[0], content[1] - screen[1]) == tuple(piece["rect"][:2])

    # Arrastar na prévia grava só naquela resolução.
    api.resolutions_adjust("elfattack.xml", piece["key"], [1920, 1080], [1064, 811])
    stored = json.loads((root / "resolutions.json").read_text(encoding="utf-8"))
    assert stored["adjustments"] == {"ElfAttack.xml": {"1920x1080": {"id:10000": [1064, 811]}}}
    big = api.resolutions_plan([1366, 768], [[1920, 1080]])["targets"][0]
    elf = next(item for item in big["windows"] if item["file"] == "ElfAttack.xml")
    assert elf["pieces"][0]["adjusted"] and elf["pieces"][0]["rect"][:2] == [1064, 811]
    with pytest.raises(ValueError):
        api.resolutions_adjust("Fora.xml", "id:1", [1920, 1080], [0, 0])

    assert api.resolutions_pick_folder() == str(out)
    result = api.resolutions_export(str(out), [1366, 768], [[1366, 768], [1920, 1080]], False, True)
    zips = {item["key"]: item for item in result["zips"]}
    assert zips["1366x768"]["count"] == 0 and not Path(zips["1366x768"]["path"]).exists()
    assert Path(zips["1920x1080"]["path"]).name == "Red 1920x1080.zip"
    with zipfile.ZipFile(zips["1920x1080"]["path"]) as archive:
        text = archive.read("Red 1920x1080/ElfAttack.xml").decode("big5")
    # A raiz anda ao contrário: o jogo a põe em (1880, 1010) e o conteúdo tem de ir para (1064, 811).
    assert 'WindowLeft="816" WindowTop="199"' in text
    assert Path(zips["all"]["path"]).name == "Red All Resolution.zip"
    assert any(event == "progress" and payload["label"] == "export" for event, payload in api.events)

    api.resolutions_reset([1920, 1080])
    assert json.loads((root / "resolutions.json").read_text(encoding="utf-8"))["adjustments"] == {}


def test_art_variants_per_resolution(tmp_path, game, projects):
    art = tmp_path / "desenho" / "main.dds"
    art.parent.mkdir()
    art.write_bytes(b"DDS 2560")
    api = Api(tmp_path, [str(art)], game=game)
    root = open_project(api, game)
    assert api.resolutions_add_variant([2560, 1440]) == ["main.dds"]
    assert (root / "resolutions" / "2560x1440" / "main.dds").read_bytes() == b"DDS 2560"
    plan = api.resolutions_plan([1366, 768], [[2560, 1440]])["targets"][0]
    assert plan["variants"] == ["main.dds"] and "main.dds" in plan["files"]
    assert api.resolutions_add_variant([2560, 1440]) is None  # cancelou
    assert api.resolutions_remove_variant([2560, 1440], "main.dds") == []
