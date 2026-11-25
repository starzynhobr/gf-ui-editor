import zipfile
import zlib
from pathlib import Path

import pytest

from gf_ui_editor import text_data, versions
from gf_ui_editor.project import Project


def _game(tmp_path: Path) -> Path:
    game = tmp_path / "game"
    ui = game / "UI"
    (ui / "skin").mkdir(parents=True)
    (ui / "Radar.xml").write_text("<a/>", encoding="utf-8")
    (ui / "Menu.xml").write_text("<menu/>", encoding="utf-8")
    (ui / "skin" / "m.dds").write_bytes(b"dds")
    lines = []
    for path in sorted(ui.rglob("*")):
        if path.is_file():
            data = path.read_bytes()
            relative = path.relative_to(game).as_posix().replace("/", "\\")
            lines.append(f"{relative}|{len(data)}|{zlib.crc32(data) & 0xFFFFFFFF:08X}|1|0|")
    (game / "GameDataFileList.txt").write_text("\r\n".join(lines) + "\r\n", encoding="latin-1")
    return game


def test_version_keeps_only_what_differs_from_official(tmp_path: Path) -> None:
    game = _game(tmp_path)
    project = Project.create("V", game / "UI", game, projects_root=tmp_path / "projects")
    (project.ui_dir / "Radar.xml").write_text("<b/>", encoding="utf-8")
    saved = versions.save_version(project, "Primeira ideia")
    with zipfile.ZipFile(saved) as archive:
        assert sorted(archive.namelist()) == ["ui/Radar.xml", "version.json"]
    [listed] = versions.list_versions(project)
    assert listed.label == "Primeira ideia" and listed.files == 1
    assert "Primeira ideia" in versions.version_title(listed)


def test_restore_brings_back_files_reverts_official_and_removes_new(tmp_path: Path) -> None:
    game = _game(tmp_path)
    project = Project.create("V", game / "UI", game, projects_root=tmp_path / "projects")
    radar, menu = project.ui_dir / "Radar.xml", project.ui_dir / "Menu.xml"
    radar.write_text("<b/>", encoding="utf-8")
    text_data.save_edits(project.root, {"T_TextIndex.ini": {"10": text_data.TextEdit(["Sair"], ["Fechar"])}})
    checkpoint = versions.save_version(project, "boa")

    # Depois da versão: mexe no Radar de novo, no Menu (era oficial) e cria um arquivo.
    radar.write_text("<c/>", encoding="utf-8")
    project.remember_original(menu)  # o editor guarda o original no 1º salvamento
    menu.write_text("<menu mudado/>", encoding="utf-8")
    (project.ui_dir / "Novo.xml").write_text("<novo/>", encoding="utf-8")
    text_data.save_edits(project.root, {})

    result = versions.restore_version(project, checkpoint)
    assert radar.read_text(encoding="utf-8") == "<b/>"
    assert menu.read_text(encoding="utf-8") == "<menu/>"  # voltou ao oficial
    assert not (project.ui_dir / "Novo.xml").exists()
    assert (result.written, result.reverted, result.removed, result.unresolved) == (1, 1, 1, [])
    assert text_data.load_edits(project.root)["T_TextIndex.ini"]["10"].fields == ["Sair"]
    # O estado de antes de restaurar ficou guardado como versão.
    assert [v.label for v in versions.list_versions(project)] == ["antes de restaurar", "boa"]
    # E o que foi trocado/removido está no histórico.
    assert any(p.read_text(encoding="utf-8") == "<c/>" for p in project.history(radar))


def test_official_copy_comes_from_the_game_folder_when_there_is_no_original(tmp_path: Path) -> None:
    game = _game(tmp_path)
    project = Project.create("V", game / "UI", game, projects_root=tmp_path / "projects")
    checkpoint = versions.save_version(project)
    (project.ui_dir / "skin" / "m.dds").write_bytes(b"editado fora")  # sem original no histórico
    result = versions.restore_version(project, checkpoint)
    assert (project.ui_dir / "skin" / "m.dds").read_bytes() == b"dds"
    assert result.reverted == 1
    # Sem cópia oficial em lugar nenhum, o arquivo fica como está e é avisado.
    (project.ui_dir / "skin" / "m.dds").write_bytes(b"de novo")
    (game / "UI" / "skin" / "m.dds").write_bytes(b"outra UI")
    result = versions.restore_version(project, checkpoint)
    assert result.unresolved == ["skin/m.dds"] and (project.ui_dir / "skin" / "m.dds").read_bytes() == b"de novo"


def test_project_from_version_is_a_new_project_with_that_state(tmp_path: Path) -> None:
    game = _game(tmp_path)
    project = Project.create("Original", game / "UI", game, projects_root=tmp_path / "projects")
    (project.ui_dir / "Radar.xml").write_text("<b/>", encoding="utf-8")
    checkpoint = versions.save_version(project, "b")
    (project.ui_dir / "Radar.xml").write_text("<c/>", encoding="utf-8")
    new_root = versions.project_from_version(project, checkpoint, "Variante B")
    assert (new_root / "ui" / "Radar.xml").read_text(encoding="utf-8") == "<b/>"
    assert (project.ui_dir / "Radar.xml").read_text(encoding="utf-8") == "<c/>"  # original intacto
    assert Project.load(new_root).name == "Variante B"
    assert versions.list_versions(Project.load(new_root)) == []


def test_invalid_version_is_refused(tmp_path: Path) -> None:
    game = _game(tmp_path)
    project = Project.create("V", game / "UI", game, projects_root=tmp_path / "projects")
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"not a zip")
    with pytest.raises(ValueError):
        versions.restore_version(project, bad)
