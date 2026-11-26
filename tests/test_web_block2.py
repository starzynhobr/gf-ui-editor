"""Bloco 2 da interface web (casca): árvore de elementos, troca de textura, arquivos, fechar."""
from __future__ import annotations

from pathlib import Path

import pytest

from gf_ui_editor import element_tree, project as project_module, textures
from gf_ui_editor.preferences import MemoryStore, Preferences
from gf_ui_editor.project import Project
from gf_ui_editor.web_api.projects import ProjectsApi

XML = """<?xml version="1.0" ?>\r
<Root_Node UI_File_Name="Panel.xml">\r
  <Style Style="65536" />\r
  <BaseWndProperty WindowID="1" WindowHeight="300" WindowWidth="120">\r
    <BackGroundMap BGmap="Panel.dds" />\r
    <Container_Node Child_Cnt="1">\r
      <Style ParentNode="1" CtrlType="33554432" />\r
      <BaseWndProperty WindowID="2" WindowText="Fechar" WindowLeft="10" WindowTop="20" WindowHeight="80" WindowWidth="16">\r
        <BackGroundMap BGmap="Panel.dds"><NorUV NorUVLeft="1" NorUVTop="2" NorUVWidth="80" NorUVHeight="16" /></BackGroundMap>\r
        <BaseCtrlProperty FontColor="16777215" FontStyle="1" />\r
        <TextNode TextAlign="0" MultiLine="0" />\r
      </BaseWndProperty>\r
    </Container_Node>\r
  </BaseWndProperty>\r
</Root_Node>\r
"""


class Api(ProjectsApi):
    def __init__(self, answers: list | None = None):
        self.events: list = []
        self.answers = list(answers or [])
        self.prefs = Preferences(MemoryStore())
        self._setup_projects(self.prefs, Path("missing/UI"), None, lambda *args: self.answers.pop(0) if self.answers else None)

    def _emit(self, event, payload=None):
        self.events.append((event, payload))


@pytest.fixture
def project(tmp_path: Path, monkeypatch) -> Project:
    monkeypatch.setattr(project_module, "PROJECTS_ROOT", tmp_path / "projects")
    source = tmp_path / "source"
    source.mkdir()
    (source / "Panel.xml").write_bytes(XML.encode("big5"))
    (source / "Other.xml").write_bytes(XML.replace("Panel.dds", "Other.dds").encode("big5"))
    (source / "Panel.dds").write_bytes(b"DDS panel")
    (source / "Other.dds").write_bytes(b"DDS other")
    return Project.create("Bloco2", source, None, projects_root=tmp_path / "projects")


@pytest.fixture
def api(project: Project) -> Api:
    api = Api()
    api.open_project(str(project.root))
    return api


# ---- árvore -------------------------------------------------------------------------------
def test_tree_rows_carry_the_search_text_and_window_text(project: Project) -> None:
    rows = element_tree.tree_rows(project.ui_dir / "Panel.xml", ["Janela", "Botão"])
    assert [row["index"] for row in rows] == [0, 1]
    assert rows[1]["text"] == "Fechar"
    assert "botão" in rows[1]["search"] and "fechar" in rows[1]["search"] and "panel.dds" in rows[1]["search"]
    assert rows[0]["search"].startswith("1 janela")


def test_tree_columns_are_saved_in_the_preferences(api: Api) -> None:
    assert api.tree_columns() == ["2"]  # padrão da clássica: ParentNode escondido
    assert api.set_tree_columns(["0", "9"]) == ["0"]
    assert api.prefs.get("tree_hidden_columns") == "0" and api.tree_columns() == ["0"]


# ---- textura ------------------------------------------------------------------------------
def test_texture_names_and_copy_for_edit(api: Api, project: Project) -> None:
    xml = str(project.ui_dir / "Panel.xml")
    assert api.texture_names(xml) == ["Other.dds", "Panel.dds"]
    assert api.texture_copy_info(xml, "panel.DDS") == {"exists": True, "suggestion": "panel_custom.DDS"}
    assert api.copy_texture(xml, "Panel.dds", "Panel_custom") == {"name": "Panel_custom.dds"}
    assert (project.ui_dir / "Panel_custom.dds").read_bytes() == b"DDS panel"
    assert api.copy_texture(xml, "Panel.dds", "Panel_custom.dds") == {"error": "exists", "name": "Panel_custom.dds"}
    assert Path("Panel_custom.dds") in project.files()


def test_bring_texture_backs_up_what_it_replaces(project: Project, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "Panel.dds").write_bytes(b"DDS new")
    api = Api([str(outside / "Panel.dds")])
    api.open_project(str(project.root))
    xml = str(project.ui_dir / "Panel.xml")
    picked = api.pick_texture(xml)
    assert picked == {"path": str(outside / "Panel.dds"), "name": "Panel.dds", "replacing": True}
    assert api.bring_texture(xml, picked["path"]) == {"name": "Panel.dds"}
    assert (project.ui_dir / "Panel.dds").read_bytes() == b"DDS new"
    assert project.original_path_for(project.ui_dir / "Panel.dds").read_bytes() == b"DDS panel"
    assert api.pick_texture(xml) is None
    same, replacing = textures.bring_target(project.ui_dir, project.ui_dir / "Panel.dds")
    assert not replacing


# ---- arquivos: renomear, apagar, restaurar -------------------------------------------------
def test_rename_texture_and_retarget_the_xmls_that_use_it(api: Api, project: Project) -> None:
    texture = str(project.ui_dir / "Panel.dds")
    assert api.rename_check(texture, "a:b") == {"invalid": True}
    check = api.rename_check(texture, "Painel")
    assert check["name"] == "Painel.dds" and not check["replacing"] and check["texture_users"] == 1
    assert api.rename_check(texture, "Other")["replacing"]
    assert api.rename_file(texture, "Painel")["name"] == "Painel.dds"
    assert api.retarget_texture("Panel.dds", "Painel.dds") == 1
    assert b'BGmap="Painel.dds"' in (project.ui_dir / "Panel.xml").read_bytes()


def test_delete_and_restore_files(api: Api, project: Project) -> None:
    xml = project.ui_dir / "Panel.xml"
    api.open_xml(str(xml))
    assert api.delete_file_info(str(project.ui_dir / "Panel.dds")) == {"official": False, "texture_users": 1}
    project.remember_original(xml)
    xml.write_bytes(XML.replace("Fechar", "Sair").encode("big5"))
    history = api.file_history(str(xml))
    assert history["in_project"] and history["original"] is not None and history["backups"] == []
    diff = api.restore_preview(str(xml), history["original"], "Panel.xml (atual)", "versão restaurada")
    assert 'WindowText="Sair"' in diff and 'WindowText="Fechar"' in diff
    api.restore_file(str(xml), history["original"])
    assert b"Fechar" in xml.read_bytes()
    after = api.file_history(str(xml))
    assert len(after["backups"]) == 1 and after["backups"][0]["stamp"]
    api.delete_file(str(xml))
    assert not xml.exists() and api.shell_state()["open_path"] is None


# ---- fechar a janela com alterações ------------------------------------------------------
def test_closing_with_unsaved_changes_asks_the_front_first() -> None:
    api = Api()
    assert api._on_closing() is True
    api.set_unsaved(True)
    assert api._on_closing() is False
    import time

    deadline = time.time() + 2
    while not api.events and time.time() < deadline:
        time.sleep(0.01)
    assert api.events == [("close_requested", None)]
    destroyed = []
    api._window = type("Window", (), {"destroy": lambda self: destroyed.append(True)})()
    api.close_window()
    assert destroyed and api._on_closing() is True


def test_shell_state_reports_publish_on_save(api: Api) -> None:
    assert api.shell_state()["publish_on_save"] is False
    api.prefs.publish_on_save = True
    assert api.shell_state()["publish_on_save"] is True
