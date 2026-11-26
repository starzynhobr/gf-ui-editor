"""Ferramentas do projeto na interface web (MaintenanceApi): versões, puxar, limpar, UI oficial,
erro do jogo, exportar textos e as cópias do F5. Chamadas direto, sem janela."""
from __future__ import annotations

import time
import zipfile
import zlib
from pathlib import Path

import pytest

from gf_ui_editor import project as project_module, text_data
from gf_ui_editor.preferences import MemoryStore, Preferences
from gf_ui_editor.project import Project
from gf_ui_editor.web_api.maintenance import MaintenanceApi
from gf_ui_editor.web_api.projects import ProjectsApi

ROOT = '<?xml version="1.0" ?>\r\n<Root_Node UI_File_Name="{name}">\r\n  <BaseWndProperty WindowID="1" WindowHeight="300" WindowWidth="120">\r\n'
CHILD = (
    '    <Container_Node Child_Cnt="1">\r\n      <Style ParentNode="1" CtrlType="2" />\r\n'
    '      <BaseWndProperty WindowID="2000" WindowLeft="10" WindowTop="20" WindowHeight="80" WindowWidth="16">\r\n'
    '        <BackGroundMap BGmap="main.dds" />\r\n      </BaseWndProperty>\r\n    </Container_Node>\r\n'
)
END = "  </BaseWndProperty>\r\n</Root_Node>\r\n"


def _xml(name: str, child: bool) -> bytes:
    return (ROOT.format(name=name) + (CHILD if child else "") + END).encode("big5")


class Api(ProjectsApi, MaintenanceApi):
    def __init__(self, answers=None):
        self.events: list = []
        self.answers = list(answers or [])
        self.prefs = Preferences(MemoryStore())
        self._setup_projects(self.prefs, Path("missing/UI"), None, lambda *args: self.answers.pop(0) if self.answers else None)

    def _emit(self, event, payload=None):
        self.events.append((event, payload))


@pytest.fixture
def game(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setattr(project_module, "PROJECTS_ROOT", tmp_path / "projects")
    game = tmp_path / "game"
    ui = game / "UI"
    (ui / "map").mkdir(parents=True)
    (ui / "Panel.xml").write_bytes(_xml("Panel.xml", child=True))
    (ui / "Menu.xml").write_bytes(b"<menu/>")
    (ui / "map" / "m1.dds").write_bytes(b"map")
    lines = []
    for path in sorted(ui.rglob("*")):
        if path.is_file():
            data = path.read_bytes()
            relative = path.relative_to(game).as_posix().replace("/", "\\")
            lines.append(f"{relative}|{len(data)}|{zlib.crc32(data) & 0xFFFFFFFF:08X}|1|0|")
    (game / "GameDataFileList.txt").write_text("\r\n".join(lines) + "\r\n", encoding="latin-1")
    (game / "Launcher.ini").write_text("[Config]\r\nUI=padrao\r\n", encoding="latin-1")
    (game / "data" / "Translate").mkdir(parents=True)
    (game / "data" / "Translate" / "T_TextIndex.ini").write_bytes(b"10|Fechar|\r\n")
    return game


@pytest.fixture
def api(game: Path, tmp_path: Path) -> Api:
    api = Api()
    result = api.create_project({"name": "Tools", "source": str(game / "UI"), "game_dir": str(game), "include_assets": True})
    assert result["count"] == 3
    return api


def _root(api: Api) -> str:
    return api.shell_state()["project"]["root"]


def test_versions_save_restore_branch_and_delete(api: Api) -> None:
    root = _root(api)
    menu = Path(root) / "ui" / "Menu.xml"
    menu.write_bytes(b"<menu editado/>")
    saved = api.version_save(root, "boa")
    assert saved["size"].endswith("KB")
    [version] = api.versions_list(root)
    assert version["label"] == "boa" and version["files"] == 1 and "boa" in version["title"]
    menu.write_bytes(b"<menu pior/>")
    result = api.version_restore(root, version["path"])
    assert result["written"] == 1 and menu.read_bytes() == b"<menu editado/>"
    assert [item["label"] for item in api.versions_list(root)] == ["antes de restaurar", "boa"]
    assert api.version_branch(root, version["path"], "Ramo") == {"name": "Ramo"}
    assert api.version_branch(root, version["path"], "Ramo") == {"error": "taken", "name": "Ramo"}
    assert (project_module.PROJECTS_ROOT / "Ramo" / "ui" / "Menu.xml").read_bytes() == b"<menu editado/>"
    api.version_delete(version["path"])
    assert [item["label"] for item in api.versions_list(root)] == ["antes de restaurar"]
    assert Path(api.versions_folder(root)).is_dir()


def test_pull_lists_origins_and_brings_files(api: Api, game: Path) -> None:
    root = _root(api)
    assert [source["label"] for source in api.pull_sources(root)] == ["UI"]
    (game / "UI" / "Menu.xml").write_bytes(b"<menu de fora/>")
    (game / "UI" / "Novo.xml").write_bytes(b"<novo/>")
    candidates = api.pull_compare(root, str(game / "UI"))
    by_name = {item["relative"]: item for item in candidates}
    assert by_name["Menu.xml"]["origin"] == "edited" and not by_name["Menu.xml"]["new"]
    assert by_name["Novo.xml"]["new"]
    api.open_xml(str(Path(root) / "ui" / "Menu.xml"))
    result = api.pull_apply(root, [["Menu.xml", by_name["Menu.xml"]["source"]]])
    assert result == {"count": 1, "open_affected": True}
    assert (Path(root) / "ui" / "Menu.xml").read_bytes() == b"<menu de fora/>"


def test_cleanup_scan_and_apply_maps(api: Api) -> None:
    root = _root(api)
    plan = api.cleanup_scan(root)
    assert plan["name"] == "Tools" and plan["maps"]["count"] == 1 and plan["days"] == 30
    assert plan["history_all"]["count"] == 0 and plan["total"].endswith("KB")
    result = api.cleanup_apply(root, None, False, True, False)
    assert result["removed"] == 1 and not (Path(root) / "ui" / "map" / "m1.dds").exists()
    assert api.human_size(2048) == "2 KB"


def test_official_status_snapshot_controls_and_scan(api: Api, game: Path) -> None:
    root = _root(api)
    status = api.official_status()
    assert status["has_list"] and status["total"] == 2  # só os XMLs and status["launcher_ui"] == "UI Padrão"
    assert api.official_snapshot()["ready"]
    panel = Path(root) / "ui" / "Panel.xml"
    assert api.official_controls(str(panel)) == {"complete": True, "file": "Panel.xml"}
    panel.write_bytes(_xml("Panel.xml", child=False))
    controls = api.official_controls(str(panel))
    assert controls["other_ids"] == ["2000"] and controls["new_ids"] == []
    assert controls["infos"]["2000"]["texture"] == "main.dds" and controls["infos"]["2000"]["position"] == [10, 20]
    api.official_scan()
    deadline = time.time() + 10
    while not any(event == "official_scan" for event, _ in api.events) and time.time() < deadline:
        time.sleep(0.02)
    [(event, payload)] = [item for item in api.events if item[0] == "official_scan"]
    assert payload["root"] == root and payload["diffs"]["panel.xml"]["other_ids"] == ["2000"]
    assert api.publish_info()["new_controls"] == []  # só os novos da atualização avisam no F5
    api._official_diffs["panel.xml"].new_ids.append("2000")
    assert api.publish_info()["new_controls"] == ["Panel.xml"]


def test_locate_game_error_points_to_the_xml(api: Api, game: Path) -> None:
    root = _root(api)
    api.official_snapshot()
    assert api.locate_game_error("nada") == {"error": "invalid"}
    (Path(root) / "ui" / "Panel.xml").write_bytes(_xml("Panel.xml", child=False))
    found = api.locate_game_error("..\\Desconhecido.cpp ERROR: ID=2000 Child control can not found!")
    assert found["cpp"] == "Desconhecido.cpp" and found["id"] == "2000" and found["candidates"] == ["Panel.xml"]
    assert found["exists"] == {"Panel.xml": True} and found["paths"]["Panel.xml"] == str(Path(root) / "ui" / "Panel.xml")


def test_export_texts_and_game_text_id(api: Api, game: Path, tmp_path: Path) -> None:
    root = _root(api)
    assert api.texts_export_info() == {"available": True, "has_edits": False, "disabled": False}
    text_data.save_edits(Path(root), {"T_TextIndex.ini": {"10": text_data.TextEdit(["Sair"], ["Fechar"])}})
    assert api.texts_export_info()["has_edits"]
    api.answers = [str(tmp_path / "out" / "textos")]
    target = api.texts_pick_export()
    assert target.endswith("textos.zip")
    result = api.texts_export(target)
    assert result["names"] == ["T_TextIndex.ini"]
    with zipfile.ZipFile(target) as archive:
        assert archive.read("data/Translate/T_TextIndex.ini") == b"10|Sair|\r\n"
    assert api.game_text_id("C:/x/Fellowship_FamilyAffairs.xml", "29") == 935
    assert api.game_text_id("C:/x/Nada.xml", "1") is None


def test_game_backups_after_publish(api: Api, game: Path) -> None:
    root = _root(api)
    api.confirm_publish()
    (game / "UI" / "Menu.xml").write_bytes(b"<editado fora/>")  # alguém mexeu na pasta do jogo
    (Path(root) / "ui" / "Menu.xml").write_bytes(b"<menu do projeto/>")
    result = api.publish()
    assert result["game_backups"] == 1
    [backup] = api.game_backups()
    assert backup["relative"] == "Menu.xml" and backup["origin"] == "edited"
    assert Path(backup["source"]).read_bytes() == b"<editado fora/>"
