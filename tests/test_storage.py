import json
from pathlib import Path

from gf_ui_editor import game_updates, project as project_module, storage, text_data
from gf_ui_editor.project import Project


def test_old_json_project_is_imported_into_sqlite_and_keeps_the_originals(tmp_path: Path) -> None:
    root = tmp_path / "Antigo"
    (root / "ui").mkdir(parents=True)
    (root / "ui" / "Menu.xml").write_bytes(b"<Root_Node />")
    (root / "data").mkdir()
    (root / "project.json").write_text(json.dumps({
        "name": "Antigo", "game_dir": str(tmp_path / "game"), "include_assets": False,
        "root_modes": {"Menu.xml": "center"}, "publish_folder": "STZ-UI",
        "reference_layers": ["Radar.xml", "Menu.xml"], "base_hashes": {"Menu.xml": "abc"},
    }), encoding="utf-8")
    (root / ".hash-cache.json").write_text(json.dumps({"Menu.xml": [13, 5, "def"]}), encoding="utf-8")
    (root / "data" / "text-edits.json").write_text(json.dumps(
        {"T_TextIndex.ini": {"935": {"fields": ["slots remaining."], "original": ["message slots remaining."]}}}
    ), encoding="utf-8")

    project = Project.load(root)
    assert (project.name, project.publish_folder, project.root_modes) == ("Antigo", "STZ-UI", {"Menu.xml": "center"})
    assert project.reference_layers == ["Radar.xml", "Menu.xml"]  # a ordem das camadas se mantém
    assert project.base_hashes == {"Menu.xml": "abc"}
    assert text_data.load_edits(root)["T_TextIndex.ini"]["935"].fields == ["slots remaining."]
    assert (root / storage.PROJECT_DB).is_file()
    assert (root / "project.json.migrated").is_file() and not (root / "project.json").exists()
    assert (root / "data" / "text-edits.json.migrated").is_file()
    assert project_module.list_projects(tmp_path) == [root]

    project.reference_layers = ["Menu.xml"]
    project.save_manifest()
    storage.close_all()
    assert Project.load(root).reference_layers == ["Menu.xml"]  # reabre do banco, sem JSON


def test_schema_version_is_recorded_so_future_migrations_can_run(tmp_path: Path) -> None:
    database = storage.project_database(tmp_path)
    assert database.query("PRAGMA user_version")[0][0] == len(storage.PROJECT_MIGRATIONS)
    storage.close_all()
    # Abrir de novo não reaplica as migrações já feitas.
    assert storage.project_database(tmp_path).query("PRAGMA user_version")[0][0] == len(storage.PROJECT_MIGRATIONS)


def test_official_versions_move_from_versions_json_to_the_shared_database(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(project_module, "PROJECTS_ROOT", tmp_path)
    monkeypatch.setattr(game_updates, "_versions_cache", None)
    cache = game_updates.cache_dir()
    cache.mkdir(parents=True)
    (cache / game_updates.VERSIONS).write_text(json.dumps({"basicchar.xml": ["AAA", "BBB"]}), encoding="utf-8")
    assert game_updates._versions() == {"basicchar.xml": ["AAA", "BBB"]}
    game_updates._record_version("BasicChar.xml", "CCC")
    assert (cache / "versions.json.migrated").is_file()
    monkeypatch.setattr(game_updates, "_versions_cache", None)
    assert storage.SharedStore(tmp_path).official_versions() == {"basicchar.xml": ["AAA", "BBB", "CCC"]}
