import zipfile
from pathlib import Path

from gf_ui_editor.project import Project, is_backup_file, select_custom_ui


def _game(tmp_path: Path) -> Path:
    game = tmp_path / "game"
    ui = game / "UI"
    (ui / "map").mkdir(parents=True)
    (ui / "Radar.xml").write_text("<a/>", encoding="utf-8")
    (ui / "map" / "m.dds").write_bytes(b"dds")
    (ui / "Radar.before-gf-ui-editor-20260101-000000.xml").write_text("old", encoding="utf-8")
    (ui / "NPCTalk_original.xml").write_text("old", encoding="utf-8")
    (game / "Launcher.ini").write_bytes(
        b"[Config]\r\nLanguage=pt\r\nUIAplicada=padrao\r\nUISig=\"x\"\r\n[Cache]\r\nFull=0.1.6\r\n"
    )
    return game


def test_backup_names_are_recognised() -> None:
    assert is_backup_file("BasicChar.before-gf-ui-editor-20260911-212528.xml")
    assert is_backup_file("BasicChar_old.xml")
    assert is_backup_file("main - Copia.dds")
    assert is_backup_file("ElfUI_bac.xml")
    assert not is_backup_file("_Shop.xml")
    assert not is_backup_file("BasicChar.xml")


def test_project_lifecycle(tmp_path: Path) -> None:
    game = _game(tmp_path)
    project = Project.create("Minha UI", game / "UI", game, projects_root=tmp_path / "projects")
    assert [p.as_posix() for p in project.files()] == ["map/m.dds", "Radar.xml"]
    assert project.modified_files() == set()

    (project.ui_dir / "Radar.xml").write_text("<b/>", encoding="utf-8")
    assert project.modified_files() == {"Radar.xml"}
    assert Project.load(project.root).base_hashes == project.base_hashes

    backup = project.history_path_for(project.ui_dir / "Radar.xml")
    assert backup.parent == project.history_dir / "Radar.xml"

    archive = project.export_zip(tmp_path / "out.zip")
    assert sorted(zipfile.ZipFile(archive).namelist()) == ["Minha-UI/Radar.xml", "Minha-UI/map/m.dds"]

    result = project.publish()
    assert (game / "UICustom" / "Minha-UI" / "Radar.xml").read_text(encoding="utf-8") == "<b/>"
    assert (game / "UI" / "Radar.xml").read_text(encoding="utf-8") == "<b/>"
    assert result.copied_to_ui == 1 and result.launcher_updated
    ini = (game / "Launcher.ini").read_bytes()
    assert b"UIAplicada=custom:Minha-UI\r\n" in ini and b"UI=custom:Minha-UI\r\n[Cache]" in ini
    # Arquivos que não são do projeto continuam na pasta UI do jogo.
    assert (game / "UI" / "NPCTalk_original.xml").exists()
    # Publicar de novo sem mudanças não copia nada.
    assert project.publish().copied_to_ui == 0


def test_publish_mirrors_custom_folder(tmp_path: Path) -> None:
    game = _game(tmp_path)
    project = Project.create("X", game / "UI", game, projects_root=tmp_path / "projects")
    stale = game / "UICustom" / "X" / "Stale.xml"
    stale.parent.mkdir(parents=True)
    stale.write_text("x", encoding="utf-8")
    project.publish(copy_to_ui=False, select_in_launcher=False)
    assert not stale.exists()


def test_select_custom_ui_appends_missing_keys(tmp_path: Path) -> None:
    ini = tmp_path / "Launcher.ini"
    ini.write_bytes(b"[Config]\nLanguage=pt\n")
    assert select_custom_ui(ini, "A")
    assert ini.read_bytes() == b"[Config]\nLanguage=pt\nUI=custom:A\nUIAplicada=custom:A\n"
    assert not select_custom_ui(ini, "A")


def test_game_asset_folders_are_opt_in(tmp_path: Path) -> None:
    game = _game(tmp_path)
    (game / "UI" / "itemicon").mkdir()
    (game / "UI" / "itemicon" / "A1.dds").write_bytes(b"icon")
    lean = Project.create("Lean", game / "UI", game, projects_root=tmp_path / "p")
    assert "itemicon/A1.dds" not in lean.base_hashes
    full = Project.create("Full", game / "UI", game, projects_root=tmp_path / "p", include_assets=True)
    assert "itemicon/A1.dds" in full.base_hashes
    assert Project.load(full.root).include_assets
    assert any(path.as_posix() == "itemicon/A1.dds" for path in Project.load(full.root).files())


def test_history_original_and_restore(tmp_path: Path) -> None:
    game = _game(tmp_path)
    project = Project.create("H", game / "UI", game, projects_root=tmp_path / "p")
    radar = project.ui_dir / "Radar.xml"

    project.remember_original(radar)
    original = project.original_path_for(radar)
    assert original.read_text(encoding="utf-8") == "<a/>"

    first = project.history_path_for(radar)
    first.write_text("<a/>", encoding="utf-8")
    radar.write_text("<b/>", encoding="utf-8")
    assert project.history(radar) == [first]  # o original não aparece na lista

    project.restore(radar, original)
    assert radar.read_text(encoding="utf-8") == "<a/>"
    assert len(project.history(radar)) == 2  # o estado "<b/>" ficou guardado
    assert any(p.read_text(encoding="utf-8") == "<b/>" for p in project.history(radar))

    radar.write_text("<c/>", encoding="utf-8")
    project.remember_original(radar)  # já existe: não sobrescreve
    assert original.read_text(encoding="utf-8") == "<a/>"


def test_unpublished_files_and_previous_launcher_selection(tmp_path: Path) -> None:
    from gf_ui_editor.project import selected_ui

    game = _game(tmp_path)
    (game / "Launcher.ini").write_bytes(b"[Config]\r\nUI=custom:Outra UI\r\nUIAplicada=custom:Outra UI\r\n")
    project = Project.create("P", game / "UI", game, projects_root=tmp_path / "p")
    assert project.unpublished_files() == set()

    (project.ui_dir / "Radar.xml").write_text("<b/>", encoding="utf-8")
    assert project.unpublished_files() == {"Radar.xml"}  # salvo no projeto, ainda não no jogo

    result = project.publish()
    assert result.previous_selection == "custom:Outra UI"  # o launcher aberto reaplicaria esta
    assert not result.launcher_running  # não há Launcher.exe rodando desta pasta
    assert selected_ui(game / "Launcher.ini") == "custom:P"
    assert project.unpublished_files() == set()

    # O launcher reaplica outra UI por cima: o projeto volta a aparecer como não publicado.
    (game / "UI" / "Radar.xml").write_text("<a/>", encoding="utf-8")
    assert project.unpublished_files() == {"Radar.xml"}


def test_project_from_a_custom_ui_publishes_back_into_it_without_deleting(tmp_path: Path) -> None:
    game = _game(tmp_path)
    original = game / "UICustom" / "UI GF ROUGE"
    original.mkdir(parents=True)
    (original / "Radar.xml").write_text("<a/>", encoding="utf-8")
    (original / "Radar - Copia.xml").write_text("backup do usuario", encoding="utf-8")
    (original / "so-aqui.dds").write_bytes(b"x")

    project = Project.create("UI GF ROUGE", original, game, projects_root=tmp_path / "p", publish_folder="UI GF ROUGE")
    assert project.custom_name == "UI GF ROUGE"  # nome exato, com espaços
    assert Project.load(project.root).publish_folder == "UI GF ROUGE"

    (project.ui_dir / "Radar.xml").write_text("<b/>", encoding="utf-8")
    (project.ui_dir / "so-aqui.dds").unlink()  # removido no projeto
    project.files(refresh=True)
    result = project.publish()

    assert result.custom_dir == original
    assert (original / "Radar.xml").read_text(encoding="utf-8") == "<b/>"
    # Na pasta adotada nada é apagado: nem backups do usuário, nem arquivos fora do projeto.
    assert (original / "Radar - Copia.xml").exists() and (original / "so-aqui.dds").exists()
    assert b"UI=custom:UI GF ROUGE" in (game / "Launcher.ini").read_bytes()
