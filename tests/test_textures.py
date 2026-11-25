import os
from pathlib import Path
import subprocess
import sys

import pytest

from gf_ui_editor import textures
from gf_ui_editor.project import Project


def test_ui_texture_names_include_only_top_level_texture_files(tmp_path: Path) -> None:
    for name in ("z.dds", "B.tga", "a.DDS", "ignored.png", "ignored.dds.bak"):
        (tmp_path / name).touch()
    nested = tmp_path / "folder.TGA"
    nested.mkdir()
    (nested / "nested.dds").touch()

    assert textures.ui_texture_names(tmp_path) == ["a.DDS", "B.tga", "z.dds"]
    assert textures.ui_texture_names(nested) == ["nested.dds"]


def test_copy_new_project_texture_creates_no_history(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    (base / "atlas.dds").touch()
    project = Project.create("P", base, None, projects_root=tmp_path / "projects")
    source = tmp_path / "source.dds"
    source.write_bytes(b"new texture")

    target = textures.copy_texture_for_edit(project, source, "new.dds")

    assert target == project.ui_dir / "new.dds"
    assert target.read_bytes() == source.read_bytes()
    assert project.history(target) == []
    assert not project.original_path_for(target).exists()


def test_replacing_project_texture_records_each_version_and_keeps_original(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    (base / "atlas.dds").write_bytes(b"original")
    project = Project.create("P", base, None, projects_root=tmp_path / "projects")
    source = tmp_path / "atlas.dds"
    source.write_bytes(b"first edit")

    target = textures.copy_texture_for_edit(project, source, "atlas.dds")
    assert target.read_bytes() == b"first edit"
    assert [entry.read_bytes() for entry in project.history(target)] == [b"original"]

    source.write_bytes(b"second edit")
    textures.backup_texture_for_edit(project, target)
    textures.copy_texture_for_edit(None, source, target)

    assert target.read_bytes() == b"second edit"
    assert {entry.read_bytes() for entry in project.history(target)} == {b"original", b"first edit"}
    assert len(project.history(target)) == 2
    assert project.original_path_for(target).read_bytes() == b"original"


def test_copy_texture_for_edit_propagates_copy_errors(tmp_path: Path) -> None:
    target = tmp_path / "new.dds"

    with pytest.raises(FileNotFoundError):
        textures.copy_texture_for_edit(None, tmp_path / "missing.dds", target)

    assert not target.exists()


def test_service_does_not_import_qt() -> None:
    code = "import sys, gf_ui_editor.textures; print(any(name.startswith('PySide6') for name in sys.modules))"
    env = {**os.environ, "PYTHONPATH": str(Path(textures.__file__).parents[1])}
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, check=True)
    assert result.stdout.strip() == "False"
