import zlib
from pathlib import Path

from gf_ui_editor import game_sync
from gf_ui_editor.project import Project


def _game(tmp_path: Path) -> Path:
    game = tmp_path / "game"
    ui = game / "UI"
    ui.mkdir(parents=True)
    (ui / "Radar.xml").write_text("<a/>", encoding="utf-8")
    (ui / "Menu.xml").write_text("<menu/>", encoding="utf-8")
    lines = []
    for path in sorted(ui.rglob("*")):
        data = path.read_bytes()
        relative = path.relative_to(game).as_posix().replace("/", "\\")
        lines.append(f"{relative}|{len(data)}|{zlib.crc32(data) & 0xFFFFFFFF:08X}|1|0|")
    (game / "GameDataFileList.txt").write_text("\r\n".join(lines) + "\r\n", encoding="latin-1")
    return game


def _project(tmp_path: Path, game: Path, name: str = "P") -> Project:
    return Project.create(name, game / "UI", game, projects_root=tmp_path / "projects")


def test_f5_backs_up_a_game_file_edited_outside_and_not_what_it_sent(tmp_path: Path) -> None:
    game = _game(tmp_path)
    project = _project(tmp_path, game)
    radar = project.ui_dir / "Radar.xml"
    radar.write_text("<b/>", encoding="utf-8")
    first = project.publish(select_in_launcher=False)
    assert first.game_backups == []  # a pasta tinha o oficial
    # Editado na pasta do jogo (como o Harlem fazia), depois o projeto muda e o F5 sobrescreve.
    (game / "UI" / "Radar.xml").write_text("<editado no jogo/>", encoding="utf-8")
    radar.write_text("<c/>", encoding="utf-8")
    second = project.publish(select_in_launcher=False)
    [(relative, backup)] = second.game_backups
    assert relative == "Radar.xml" and backup.read_text(encoding="utf-8") == "<editado no jogo/>"
    assert "-jogo" in backup.name and (game / "UI" / "Radar.xml").read_text(encoding="utf-8") == "<c/>"
    # O que o próprio editor mandou não é "editado fora".
    radar.write_text("<d/>", encoding="utf-8")
    assert project.publish(select_in_launcher=False).game_backups == []


def test_f5_does_not_back_up_files_applied_from_another_ui(tmp_path: Path) -> None:
    game = _game(tmp_path)
    other = game / "UICustom" / "Outra"
    other.mkdir(parents=True)
    (other / "Radar.xml").write_text("<outra/>", encoding="utf-8")
    (game / "UI" / "Radar.xml").write_text("<outra/>", encoding="utf-8")  # o launcher aplicou "Outra"
    project = _project(tmp_path, game)
    (project.ui_dir / "Radar.xml").write_text("<b/>", encoding="utf-8")
    assert project.publish(select_in_launcher=False).game_backups == []


def test_sent_record_is_shared_between_projects(tmp_path: Path) -> None:
    game = _game(tmp_path)
    first, second = _project(tmp_path, game, "A"), _project(tmp_path, game, "B")
    (first.ui_dir / "Radar.xml").write_text("<a1/>", encoding="utf-8")
    first.publish(select_in_launcher=False)
    (second.ui_dir / "Radar.xml").write_text("<b1/>", encoding="utf-8")
    assert second.publish(select_in_launcher=False).game_backups == []  # quem mandou foi o editor


def test_compare_lists_differences_with_their_origin_and_pull_keeps_history(tmp_path: Path) -> None:
    game = _game(tmp_path)
    project = _project(tmp_path, game)
    (project.ui_dir / "Radar.xml").write_text("<b/>", encoding="utf-8")
    project.publish(select_in_launcher=False)
    (game / "UI" / "Radar.xml").write_text("<feito no jogo/>", encoding="utf-8")
    (game / "UI" / "Novo.xml").write_text("<novo/>", encoding="utf-8")
    (project.ui_dir / "Menu.xml").write_text("<menu mudado/>", encoding="utf-8")  # pasta tem o oficial
    candidates = game_sync.compare(project, game / "UI")
    by_name = {item.relative: item for item in candidates}
    assert set(by_name) == {"Radar.xml", "Novo.xml", "Menu.xml"}
    assert by_name["Radar.xml"].origin == game_sync.EDITED_OUTSIDE
    assert by_name["Menu.xml"].origin == game_sync.OFFICIAL
    assert by_name["Novo.xml"].new
    assert candidates[-1].relative == "Menu.xml"  # oficiais por último

    count = game_sync.pull(project, [("Radar.xml", by_name["Radar.xml"].source), ("Novo.xml", by_name["Novo.xml"].source)])
    assert count == 2
    assert (project.ui_dir / "Radar.xml").read_text(encoding="utf-8") == "<feito no jogo/>"
    assert (project.ui_dir / "Novo.xml").exists()
    assert any(p.read_text(encoding="utf-8") == "<b/>" for p in project.history(project.ui_dir / "Radar.xml"))
    assert (project.ui_dir / "Menu.xml").read_text(encoding="utf-8") == "<menu mudado/>"  # não marcado


def test_pull_sources_list_game_ui_and_custom_uis(tmp_path: Path) -> None:
    game = _game(tmp_path)
    (game / "UICustom" / "Hero").mkdir(parents=True)
    assert [label for label, _ in game_sync.pull_sources(game)] == ["UI", "UICustom/Hero"]
