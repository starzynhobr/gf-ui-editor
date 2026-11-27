"""Lista de arquivos, ordem das seções e texturas usadas pelos XMLs: sem Qt."""
from datetime import datetime
import os
from pathlib import Path
import subprocess
import sys

import pytest

from gf_ui_editor import file_list
from gf_ui_editor.file_list import FILE_SECTIONS
from gf_ui_editor.project import Project


def _project(tmp_path: Path, game: bool = False) -> Project:
    source = tmp_path / "source"
    (source / "skin").mkdir(parents=True)
    (source / "Radar.xml").write_bytes(b'<a BGmap="Main.dds"/>')
    (source / "Bag.xml").write_bytes(b'<a BGmap = "main.dds" x="1"/>')
    (source / "Shop.xml").write_bytes(b'<a BGmap="Other.dds"/>')
    (source / "Main.dds").write_bytes(b"dds")
    (source / "skin" / "m.dds").write_bytes(b"dds")
    game_dir = None
    if game:
        game_dir = tmp_path / "game"
        (game_dir / "UI").mkdir(parents=True)
    return Project.create("P", source, game_dir, projects_root=tmp_path / "projects")


def test_project_listing_splits_xml_and_main_folder_textures(tmp_path: Path) -> None:
    project = _project(tmp_path)
    (project.ui_dir / "Radar.xml").write_bytes(b'<a BGmap="Main.dds" y="2"/>')
    project.invalidate_changes()
    listing = file_list.project_listing(project)
    assert [path.as_posix() for path in listing.xml] == ["Bag.xml", "Radar.xml", "Shop.xml"]
    assert [path.as_posix() for path in listing.textures] == ["Main.dds"]  # skin/m.dds fica de fora
    assert listing.modified == {"Radar.xml"}
    assert listing.shared_publish == []


def test_loose_listing_sorts_and_skips_backups(tmp_path: Path) -> None:
    (tmp_path / "b.xml").write_text("x", encoding="utf-8")
    (tmp_path / "A.xml").write_text("x", encoding="utf-8")
    (tmp_path / "A.before-gf-ui-editor-20260101-000000.xml").write_text("x", encoding="utf-8")
    (tmp_path / "A.dds").write_bytes(b"dds")
    listing = file_list.loose_listing(tmp_path)
    assert [path.as_posix() for path in listing.xml] == ["A.xml", "b.xml"]
    assert listing.textures == [] and listing.modified == set()
    assert file_list.loose_listing(None) == file_list.FileListing()


def test_file_groups_keep_list_order() -> None:
    files = [Path("A.xml"), Path("B.xml"), Path("C.xml")]
    groups = file_list.file_groups(files, {"C.xml", "A.xml"}, {"B.xml"})
    assert list(groups) == list(FILE_SECTIONS)
    assert groups == {"layers": [Path("B.xml")], "changed": [Path("A.xml"), Path("C.xml")], "all": files}


def test_section_order_parsing_falls_back_to_default() -> None:
    assert file_list.parse_section_order("all,layers,changed") == ["all", "layers", "changed"]
    assert file_list.parse_section_order("") == list(FILE_SECTIONS)
    assert file_list.parse_section_order("all,layers") == list(FILE_SECTIONS)
    assert file_list.parse_section_order("all,layers,changed,all") == list(FILE_SECTIONS)
    assert file_list.parse_section_order("x,all,layers,changed") == ["all", "layers", "changed"]
    assert file_list.is_valid_section_order(["changed", "all", "layers"])
    assert not file_list.is_valid_section_order(["all", "layers"])


def test_drop_reorders_visible_sections_and_keeps_hidden_in_place() -> None:
    order = ["layers", "changed", "all"]
    everything = list(order)
    # Soltar Camadas depois do Todos (posição 3 = no fim).
    assert file_list.order_after_drop(order, everything, "layers", 3) == ["changed", "all", "layers"]
    # Soltar Todos antes das Camadas.
    assert file_list.order_after_drop(order, everything, "all", 0) == ["all", "layers", "changed"]
    # Soltar em cima dela mesma: nada muda.
    assert file_list.order_after_drop(order, everything, "changed", 1) is None
    # Alterados escondida (vazia): continua logo depois das Camadas.
    assert file_list.order_after_drop(order, ["layers", "all"], "layers", 2) == ["all", "layers", "changed"]
    assert file_list.order_after_drop(["changed", "layers", "all"], ["layers", "all"], "all", 0) == [
        "changed", "all", "layers"
    ]


def test_move_section_up_and_down() -> None:
    order = ["layers", "changed", "all"]
    assert file_list.order_after_move(order, order, "all", -1) == ["layers", "all", "changed"]
    assert file_list.order_after_move(order, order, "layers", 1) == ["changed", "layers", "all"]
    assert file_list.order_after_move(order, order, "layers", -1) is None
    assert file_list.order_after_move(order, order, "all", 1) is None
    assert file_list.order_after_move(order, ["layers", "all"], "changed", 1) is None  # escondida
    assert file_list.order_after_move(order, ["layers", "all"], "all", -1) == ["all", "layers", "changed"]


def test_merge_hidden_puts_section_after_its_old_neighbour() -> None:
    assert file_list.merge_hidden(["layers", "changed", "all"], ["all", "layers"], ["changed"]) == [
        "all", "layers", "changed"
    ]
    assert file_list.merge_hidden(["changed", "layers", "all"], ["all", "layers"], ["changed"]) == [
        "changed", "all", "layers"
    ]


def test_section_heights_parsing() -> None:
    assert file_list.parse_section_heights('{"layers": 150, "changed": 80.6, "x": "a"}') == {"layers": 150, "changed": 80}
    assert file_list.parse_section_heights("not json") == {}
    assert file_list.parse_section_heights("[1, 2]") == {}


def test_xml_using_texture_is_case_insensitive_and_exact(tmp_path: Path) -> None:
    project = _project(tmp_path)
    found = file_list.xml_using_texture(project, "Main.dds")
    assert sorted(path.name for path in found) == ["Bag.xml", "Radar.xml"]
    assert file_list.xml_using_texture(project, "Main") == []


def test_retarget_texture_changes_only_bgmap_and_keeps_history(tmp_path: Path) -> None:
    project = _project(tmp_path)
    users = file_list.xml_using_texture(project, "Main.dds")
    file_list.retarget_texture(project, users, "Main.dds", "Novo.dds")
    assert (project.ui_dir / "Radar.xml").read_bytes() == b'<a BGmap="Novo.dds"/>'
    assert (project.ui_dir / "Bag.xml").read_bytes() == b'<a BGmap = "Novo.dds" x="1"/>'
    assert (project.ui_dir / "Shop.xml").read_bytes() == b'<a BGmap="Other.dds"/>'
    radar = project.ui_dir / "Radar.xml"
    backups, original = file_list.history_entries(project, radar)
    assert len(backups) == 1 and backups[0].read_bytes() == b'<a BGmap="Main.dds"/>'
    assert original is not None and original.read_bytes() == b'<a BGmap="Main.dds"/>'
    assert project.modified_files() == {"Bag.xml", "Radar.xml"}


def test_history_entries_of_loose_file(tmp_path: Path) -> None:
    path = tmp_path / "Radar.xml"
    path.write_text("x", encoding="utf-8")
    old = tmp_path / "Radar.before-gf-ui-editor-20260101-000000.xml"
    new = tmp_path / "Radar.before-gf-ui-editor-20260202-000000.xml"
    for backup in (old, new, tmp_path / "Bag.before-gf-ui-editor-20260303-000000.xml"):
        backup.write_text("x", encoding="utf-8")
    assert file_list.history_entries(None, path) == ([new, old], None)


def test_backup_stamp() -> None:
    assert file_list.backup_stamp(Path("A.before-gf-ui-editor-20260911-212528.xml")) == datetime(2026, 9, 11, 21, 25, 28)
    assert file_list.backup_stamp(Path("A.xml")) is None


def test_service_does_not_import_qt() -> None:
    """A interface web vai usar o mesmo serviço: importar não pode puxar o PySide6."""
    code = "import sys, gf_ui_editor.file_list; print(any(name.startswith('PySide6') for name in sys.modules))"
    env = {**os.environ, "PYTHONPATH": str(Path(file_list.__file__).parents[1])}
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, check=True)
    assert result.stdout.strip() == "False"


def test_rename_target_keeps_the_extension_and_flags_replacement(tmp_path: Path) -> None:
    project = _project(tmp_path)
    radar = project.ui_dir / "Radar.xml"
    assert file_list.rename_target(radar, "Mapa") == (project.ui_dir / "Mapa.xml", False)
    assert file_list.rename_target(radar, "Mapa.txt") == (project.ui_dir / "Mapa.txt", False)
    assert file_list.rename_target(radar, "Bag") == (project.ui_dir / "Bag.xml", True)
    assert file_list.rename_target(radar, "radar") == (project.ui_dir / "radar.xml", False)  # só a caixa muda
    assert file_list.has_invalid_chars("a/b") and file_list.has_invalid_chars(r"a\b") and file_list.has_invalid_chars('a"b')
    assert not file_list.has_invalid_chars("Novo nome.xml")


def test_delete_warning_for_official_xml_and_used_texture(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path, game=True)
    seen: list[str] = []
    monkeypatch.setattr(file_list, "official_text_for", lambda game_dir, relative: seen.append(relative) or (
        "<oficial/>" if relative == "Radar.xml" else None
    ))
    assert file_list.delete_warning(project, project.ui_dir / "Radar.xml") == file_list.DeleteWarning(official=True)
    assert file_list.delete_warning(project, project.ui_dir / "Shop.xml") == file_list.DeleteWarning()
    assert seen == ["Radar.xml", "Shop.xml"]
    assert file_list.delete_warning(project, project.ui_dir / "Main.dds") == file_list.DeleteWarning(texture_users=2)
    assert file_list.delete_warning(project, project.ui_dir / "skin" / "m.dds") == file_list.DeleteWarning()


def test_delete_warning_without_game_folder_skips_the_official_check(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path)
    monkeypatch.setattr(file_list, "official_text_for", lambda *_args: pytest.fail("sem pasta do jogo"))
    assert file_list.delete_warning(project, project.ui_dir / "Radar.xml") == file_list.DeleteWarning()


def test_import_plan_points_to_existing_files_by_name(tmp_path: Path) -> None:
    project = _project(tmp_path)
    outside = tmp_path / "fora"
    outside.mkdir()
    for name in ("m.dds", "Novo.xml"):
        (outside / name).write_bytes(b"x")
    targets, replaced = file_list.import_plan(project, [outside / "m.dds", outside / "Novo.xml"])
    assert targets == {outside / "m.dds": project.ui_dir / "skin" / "m.dds", outside / "Novo.xml": project.ui_dir / "Novo.xml"}
    assert replaced == [project.ui_dir / "skin" / "m.dds"]


def test_restore_diff_compares_big5_lines(tmp_path: Path) -> None:
    current, source = tmp_path / "A.xml", tmp_path / "old.xml"
    current.write_bytes("<a>\n<b x=\"1\"/>\n".encode("big5"))
    source.write_bytes("<a>\n<b x=\"2\"/>\n".encode("big5"))
    assert file_list.restore_diff(current, source, "A.xml (atual)", "versão") == (
        "--- A.xml (atual)\n+++ versão\n@@ -1,2 +1,2 @@\n <a>\n-<b x=\"1\"/>\n+<b x=\"2\"/>"
    )
    assert file_list.restore_diff(current, current, "a", "b") == ""
    with pytest.raises(OSError):
        file_list.restore_diff(current, tmp_path / "sumiu.xml", "a", "b")


def test_restore_file_of_loose_xml_keeps_a_backup_beside_it(tmp_path: Path) -> None:
    current, source = tmp_path / "A.xml", tmp_path / "old.xml"
    current.write_bytes(b"novo")
    source.write_bytes(b"velho")
    file_list.restore_file(None, current, source, now=datetime(2026, 11, 25, 9, 8, 7))
    assert current.read_bytes() == b"velho"
    assert (tmp_path / "A.before-gf-ui-editor-20261125-090807.xml").read_bytes() == b"novo"
    assert file_list.history_entries(None, current)[0] == [tmp_path / "A.before-gf-ui-editor-20261125-090807.xml"]


def test_restore_file_in_project_goes_through_its_history(tmp_path: Path) -> None:
    project = _project(tmp_path)
    radar = project.ui_dir / "Radar.xml"
    source = tmp_path / "old.xml"
    source.write_bytes(b"<velho/>")
    file_list.restore_file(project, radar, source)
    assert radar.read_bytes() == b"<velho/>"
    backups, _original = file_list.history_entries(project, radar)
    assert [backup.read_bytes() for backup in backups] == [b'<a BGmap="Main.dds"/>']
    assert not list(radar.parent.glob("Radar.before-gf-ui-editor-*"))


def test_folder_stamp_changes_when_files_come_go_or_change(tmp_path) -> None:
    from gf_ui_editor.file_list import folder_stamp

    assert folder_stamp(None) == "" and folder_stamp(tmp_path / "missing") == ""
    (tmp_path / "A.xml").write_text("<a/>", encoding="utf-8")
    first = folder_stamp(tmp_path)
    assert first and folder_stamp(tmp_path) == first
    (tmp_path / "sub").mkdir()
    assert folder_stamp(tmp_path) == first  # subpastas não contam
    (tmp_path / "B.dds").write_bytes(b"dds")
    added = folder_stamp(tmp_path)
    assert added != first
    (tmp_path / "B.dds").rename(tmp_path / "C.dds")
    renamed = folder_stamp(tmp_path)
    assert renamed != added
    (tmp_path / "A.xml").write_text("<a x='1'/>", encoding="utf-8")
    assert folder_stamp(tmp_path) != renamed
    (tmp_path / "C.dds").unlink()
    assert folder_stamp(tmp_path) not in (added, renamed)
