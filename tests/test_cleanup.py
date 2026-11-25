import os
import time
import zlib
from pathlib import Path

from gf_ui_editor import cleanup
from gf_ui_editor.project import Project


def _game(tmp_path: Path) -> Path:
    game = tmp_path / "game"
    ui = game / "UI"
    (ui / "itemicon").mkdir(parents=True)
    (ui / "map").mkdir()
    (ui / "Radar.xml").write_text("<a/>", encoding="utf-8")
    (ui / "itemicon" / "a.dds").write_bytes(b"icon-a")
    (ui / "itemicon" / "b.dds").write_bytes(b"icon-b")
    (ui / "map" / "m.dds").write_bytes(b"map")
    lines = []
    for path in sorted(ui.rglob("*")):
        if path.is_file():
            data = path.read_bytes()
            relative = path.relative_to(game).as_posix().replace("/", "\\")
            lines.append(f"{relative}|{len(data)}|{zlib.crc32(data) & 0xFFFFFFFF:08X}|1|0|")
    (game / "GameDataFileList.txt").write_text("\r\n".join(lines) + "\r\n", encoding="latin-1")
    return game


def test_history_cleanup_keeps_originals_and_can_drop_only_old_backups(tmp_path: Path) -> None:
    game = _game(tmp_path)
    project = Project.create("C", game / "UI", game, projects_root=tmp_path / "projects")
    radar = project.ui_dir / "Radar.xml"
    project.remember_original(radar)
    old = project.history_path_for(radar)
    old.write_text("<velho/>", encoding="utf-8")
    past = time.time() - 60 * 86400
    os.utime(old, (past, past))
    recent = project.history_path_for(radar)
    recent.write_text("<recente/>", encoding="utf-8")

    plan = cleanup.scan(project)
    assert plan.history_old == [old] and set(plan.history_all) == {old, recent}
    result = cleanup.apply(project, plan, history="old")
    assert result.removed == 1 and not old.exists() and recent.exists()
    assert project.original_path_for(radar).exists()

    cleanup.apply(project, cleanup.scan(project), history="all")
    assert project.history(radar) == [] and project.original_path_for(radar).exists()


def test_icons_cleanup_removes_only_official_icons_and_turns_off_include_assets(tmp_path: Path) -> None:
    game = _game(tmp_path)
    project = Project.create("C", game / "UI", game, projects_root=tmp_path / "projects", include_assets=True)
    (project.ui_dir / "itemicon" / "b.dds").write_bytes(b"editado")
    plan = cleanup.scan(project)
    assert [p.name for p in plan.icons] == ["a.dds"] and plan.icons_left == 1
    cleanup.apply(project, plan, icons=True)
    assert not (project.ui_dir / "itemicon" / "a.dds").exists()
    assert (project.ui_dir / "itemicon" / "b.dds").exists() and project.include_assets  # sobrou um editado
    assert (project.ui_dir / "map" / "m.dds").exists()  # a opção dos ícones não mexe no map

    (project.ui_dir / "itemicon" / "b.dds").write_bytes(b"icon-b")  # voltou ao oficial
    cleanup.apply(project, cleanup.scan(project), icons=True)
    assert not project.include_assets and Project.load(project.root).include_assets is False


def test_custom_copy_cleanup_drops_files_the_ui_does_not_need(tmp_path: Path) -> None:
    game = _game(tmp_path)
    project = Project.create("C", game / "UI", game, projects_root=tmp_path / "projects")
    (project.ui_dir / "Radar.xml").write_text("<b/>", encoding="utf-8")
    custom = game / "UICustom" / project.custom_name
    (custom / "map").mkdir(parents=True)
    (custom / "Radar.xml").write_text("<b/>", encoding="utf-8")
    (custom / "map" / "m.dds").write_bytes(b"map")  # envio antigo levava tudo
    (custom / "Velho.xml").write_text("<x/>", encoding="utf-8")
    plan = cleanup.scan(project)
    assert sorted(p.name for p in plan.custom) == ["Velho.xml", "m.dds"]
    cleanup.apply(project, plan, custom=True)
    assert (custom / "Radar.xml").exists() and not (custom / "map").exists() and not (custom / "Velho.xml").exists()


def test_adopted_publish_folder_is_never_cleaned(tmp_path: Path) -> None:
    game = _game(tmp_path)
    (game / "UICustom" / "Alheia").mkdir(parents=True)
    (game / "UICustom" / "Alheia" / "Outro.xml").write_text("<x/>", encoding="utf-8")
    project = Project.create("C", game / "UI", game, projects_root=tmp_path / "projects", publish_folder="Alheia")
    assert cleanup.scan(project).custom == []


def test_maps_cleanup_removes_official_maps_even_without_include_assets(tmp_path: Path) -> None:
    game = _game(tmp_path)
    project = Project.create("C", game / "UI", game, projects_root=tmp_path / "projects")
    assert not (project.ui_dir / "map").exists()  # projetos novos já vêm sem o map
    # Projeto antigo: tinha o map copiado, com um mapa editado.
    (project.ui_dir / "map").mkdir()
    (project.ui_dir / "map" / "m.dds").write_bytes(b"map")
    (project.ui_dir / "map" / "editado.dds").write_bytes(b"meu mapa")
    plan = cleanup.scan(project)
    assert [p.name for p in plan.maps] == ["m.dds"] and plan.maps_left == 1
    cleanup.apply(project, plan, maps=True)
    assert not (project.ui_dir / "map" / "m.dds").exists()
    assert (project.ui_dir / "map" / "editado.dds").exists()
    assert [p.as_posix() for p in project.files() if p.parts[0] == "map"] == ["map/editado.dds"]
