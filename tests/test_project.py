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


def test_project_can_start_from_a_zip(tmp_path: Path) -> None:
    import zipfile

    import pytest

    from gf_ui_editor.project import extract_ui_zip

    archive = tmp_path / "Minha UI.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("Minha UI/Radar.xml", "<Root_Node />")
        bundle.writestr("Minha UI/main.dds", b"DDS ")
    root = extract_ui_zip(archive, tmp_path / "out")
    assert root.name == "Minha UI"
    assert sorted(path.name for path in root.iterdir()) == ["Radar.xml", "main.dds"]

    loose = tmp_path / "solta.zip"
    with zipfile.ZipFile(loose, "w") as bundle:
        bundle.writestr("Radar.xml", "<Root_Node />")
    assert extract_ui_zip(loose, tmp_path / "out2") == (tmp_path / "out2").resolve()

    unsafe = tmp_path / "ruim.zip"
    with zipfile.ZipFile(unsafe, "w") as bundle:
        bundle.writestr("../fora.xml", "x")
    with pytest.raises(ValueError):
        extract_ui_zip(unsafe, tmp_path / "out3")
    assert not (tmp_path / "fora.xml").exists()

    empty = tmp_path / "vazia.zip"
    with zipfile.ZipFile(empty, "w") as bundle:
        bundle.writestr("leia-me.txt", "x")
    with pytest.raises(ValueError):
        extract_ui_zip(empty, tmp_path / "out4")


def test_import_file_replaces_same_name_anywhere_or_adds_to_root(tmp_path: Path) -> None:
    game = _game(tmp_path)
    project = Project.create("I", game / "UI", game, projects_root=tmp_path / "p")
    loose = tmp_path / "loose"
    loose.mkdir()
    (loose / "M.DDS").write_bytes(b"new dds")
    (loose / "Novo.xml").write_text("<n/>", encoding="utf-8")

    target, backup = project.import_file(loose / "M.DDS")
    assert target == project.ui_dir / "map" / "m.dds"
    assert target.read_bytes() == b"new dds"
    assert backup is not None and backup.read_bytes() == b"dds"
    assert project.original_path_for(target).read_bytes() == b"dds"

    target, backup = project.import_file(loose / "Novo.xml")
    assert target == project.ui_dir / "Novo.xml" and backup is None
    assert Path("Novo.xml") in project.files()


def test_projects_publishing_to_finds_projects_sharing_a_custom_folder(tmp_path: Path, monkeypatch) -> None:
    import gf_ui_editor.project as project_module
    from gf_ui_editor.game_layout import normalize_game_dir

    game = _game(tmp_path)
    (game / "client.ini").write_text("[Option]\n", encoding="utf-8")
    assert normalize_game_dir(game / "UI") == game
    assert normalize_game_dir(game) == game

    root = tmp_path / "projects"
    monkeypatch.setattr(project_module, "PROJECTS_ROOT", root)
    first = Project.create("UI-HERO", game / "UI", game, projects_root=root)
    second = Project.create("UI-HERO2", game / "UI", game, projects_root=root, publish_folder="UI-HERO")
    assert project_module.projects_publishing_to("ui-hero") == ["UI-HERO", "UI-HERO2"]
    assert project_module.projects_publishing_to("UI-HERO", exclude=second.root) == ["UI-HERO"]
    assert project_module.projects_publishing_to("UI-HERO2") == []
    assert first.custom_name == "UI-HERO"


def test_rename_replaces_existing_file_keeping_it_in_history_and_delete_keeps_a_copy(tmp_path: Path) -> None:
    game = _game(tmp_path)
    project = Project.create("R", game / "UI", game, projects_root=tmp_path / "p")
    (project.ui_dir / "Radar2.xml").write_text("<novo/>", encoding="utf-8")

    target, backup = project.rename_file(project.ui_dir / "Radar2.xml", "Radar.xml")
    assert target == project.ui_dir / "Radar.xml" and target.read_text(encoding="utf-8") == "<novo/>"
    assert backup is not None and backup.read_text(encoding="utf-8") == "<a/>"
    assert not (project.ui_dir / "Radar2.xml").exists()
    assert Path("Radar2.xml") not in project.files()

    copy = project.delete_file(project.ui_dir / "Radar.xml")
    assert copy.read_text(encoding="utf-8") == "<novo/>"
    assert Path("Radar.xml") not in project.files()


def _official_list(game: Path) -> None:
    """GameDataFileList.txt com os arquivos atuais de game/UI como oficiais."""
    import zlib

    lines = []
    for path in sorted((game / "UI").rglob("*")):
        if path.is_file():
            data = path.read_bytes()
            relative = path.relative_to(game).as_posix().replace("/", "\\")
            lines.append(f"{relative}|{len(data)}|{zlib.crc32(data) & 0xFFFFFFFF:08X}|1|0|")
    (game / "GameDataFileList.txt").write_text("\r\n".join(lines) + "\r\n", encoding="latin-1")


def test_ui_ships_only_files_that_differ_from_official(tmp_path: Path) -> None:
    import pytest

    game = _game(tmp_path)
    _official_list(game)
    project = Project.create("Enxuta", game / "UI", game, projects_root=tmp_path / "projects")
    # Nada alterado: o .zip não tem o que levar.
    with pytest.raises(ValueError):
        project.export_zip(tmp_path / "vazio.zip")
    assert project.shipped_files() == ([], 2)

    (project.ui_dir / "Radar.xml").write_text("<b/>", encoding="utf-8")
    (project.ui_dir / "Novo.dds").write_bytes(b"novo")  # não existe no oficial: vai
    stale = game / "UICustom" / "Enxuta" / "map" / "m.dds"  # de um envio antigo, completo
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"dds")

    result = project.publish()
    custom = game / "UICustom" / "Enxuta"
    assert sorted(p.relative_to(custom).as_posix() for p in custom.rglob("*") if p.is_file()) == ["Novo.dds", "Radar.xml"]
    assert result.skipped_official == 1  # o map/m.dds, igual ao oficial
    assert (game / "UI" / "Radar.xml").read_text(encoding="utf-8") == "<b/>"

    archive = project.export_zip(tmp_path / "out.zip")
    assert sorted(zipfile.ZipFile(archive).namelist()) == ["Enxuta/Novo.dds", "Enxuta/Radar.xml"]
    assert project.last_export == (2, 1)


def test_ui_folder_still_gets_official_files_the_project_has(tmp_path: Path) -> None:
    # A pasta UI pode estar com o arquivo de outra UI aplicada antes: o F5 a deixa igual ao projeto.
    game = _game(tmp_path)
    _official_list(game)
    project = Project.create("Base", game / "UI", game, projects_root=tmp_path / "projects")
    (game / "UI" / "map" / "m.dds").write_bytes(b"de outra UI")
    project.publish()
    assert (game / "UI" / "map" / "m.dds").read_bytes() == b"dds"
    assert not (game / "UICustom" / "Base" / "map" / "m.dds").exists()


def test_duplicate_project_copies_everything_but_history_and_gets_its_own_folder(tmp_path: Path) -> None:
    from gf_ui_editor.project import ProjectNameTaken, duplicate_project

    game = _game(tmp_path)
    project = Project.create("Base", game / "UI", game, projects_root=tmp_path / "projects")
    (project.ui_dir / "Radar.xml").write_text("<b/>", encoding="utf-8")
    project.history_dir.mkdir(parents=True, exist_ok=True)
    (project.history_dir / "old.xml").write_text("x", encoding="utf-8")
    project.publish_folder = "Outra-UI"
    project.save_manifest()

    copy_root = duplicate_project(project.root, "Base v2")
    copy = Project.load(copy_root)
    assert copy.name == "Base v2" and copy.custom_name == "Base-v2" and copy.publish_folder == ""
    assert (copy.ui_dir / "Radar.xml").read_text(encoding="utf-8") == "<b/>"
    assert not (copy_root / ".history").exists()
    assert Project.load(project.root).name == "Base"  # o original não muda
    import pytest

    with pytest.raises(ProjectNameTaken):
        duplicate_project(project.root, "Base v2")


def test_rename_project_moves_folder_custom_ui_and_launcher_selection(tmp_path: Path) -> None:
    from gf_ui_editor.project import rename_project, selected_ui

    game = _game(tmp_path)
    project = Project.create("Velho", game / "UI", game, projects_root=tmp_path / "projects")
    project.publish()  # cria UICustom/Velho e seleciona no launcher
    assert selected_ui(game / "Launcher.ini") == "custom:Velho"

    new_root = rename_project(project.root, "Novo Nome")
    assert not project.root.exists() and Project.load(new_root).name == "Novo Nome"
    assert (game / "UICustom" / "Novo-Nome").is_dir() and not (game / "UICustom" / "Velho").exists()
    assert selected_ui(game / "Launcher.ini") == "custom:Novo-Nome"


def test_delete_project_trashes_project_and_optionally_its_own_custom_ui(tmp_path: Path) -> None:
    from gf_ui_editor.project import delete_project, owned_custom_folder

    game = _game(tmp_path)
    keep = Project.create("Fica", game / "UI", game, projects_root=tmp_path / "projects")
    gone = Project.create("Sai", game / "UI", game, projects_root=tmp_path / "projects")
    gone.publish(copy_to_ui=False, select_in_launcher=False)
    assert owned_custom_folder(gone) == game / "UICustom" / "Sai"
    trashed: list[Path] = []

    def fake_trash(path: Path) -> bool:
        import shutil

        trashed.append(path)
        shutil.rmtree(path)
        return True

    assert delete_project(gone.root, fake_trash, remove_custom=True) == [gone.root, game / "UICustom" / "Sai"]
    assert not gone.root.exists() and not (game / "UICustom" / "Sai").exists() and keep.root.exists()

    # Pasta UICustom compartilhada com outro projeto: não é "dele", fica.
    shared = Project.create("Par", game / "UI", game, projects_root=tmp_path / "projects")
    shared.publish_folder = "Fica"
    shared.save_manifest()
    keep.publish(copy_to_ui=False, select_in_launcher=False)
    assert owned_custom_folder(Project.load(shared.root)) is None
    delete_project(shared.root, fake_trash, remove_custom=True)
    assert (game / "UICustom" / "Fica").is_dir()


def test_checking_who_publishes_where_does_not_keep_other_projects_open(tmp_path: Path) -> None:
    import os

    from gf_ui_editor import storage
    from gf_ui_editor.project import projects_publishing_to

    game = _game(tmp_path)
    other = Project.create("Outro", game / "UI", game, projects_root=tmp_path / "projects")
    other.publish_folder = "Comum"
    other.save_manifest()
    storage.close_all()
    assert projects_publishing_to("Comum", projects_root=tmp_path / "projects") == ["Outro"]
    assert projects_publishing_to("comum", projects_root=tmp_path / "projects") == ["Outro"]
    # Nenhuma conexão ficou aberta: a pasta pode ser renomeada (no Windows, falharia com o banco aberto).
    os.replace(other.root, other.root.with_name("Movido"))
