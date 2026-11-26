from datetime import datetime
import os
from pathlib import Path
import subprocess
import sys

import pytest

from gf_ui_editor import home


def test_home_projects_lists_the_current_project_then_most_recent(tmp_path: Path) -> None:
    oldest, recent, tied, current = (tmp_path / name for name in ("oldest", "recent", "tied", "current"))
    roots = [oldest, recent, tied, current]
    for root, timestamp in zip(roots, (10, 30, 30, 20)):
        root.mkdir()
        manifest = root / "project.json"
        manifest.touch()
        os.utime(manifest, (timestamp, timestamp))

    assert home.home_projects(roots, current) == [(current, 20), (recent, 30), (tied, 30), (oldest, 10)]
    assert home.home_projects(roots, None) == [(recent, 30), (tied, 30), (current, 20), (oldest, 10)]
    assert roots == [oldest, recent, tied, current]


def test_project_disk_size_includes_nested_files(tmp_path: Path) -> None:
    history = tmp_path / "history"
    history.mkdir()
    (history / "original.xml").write_bytes(b"original")
    (tmp_path / "project.json").write_bytes(b"{}")

    assert home.project_disk_size(tmp_path) == 10
    assert home.project_disk_size(tmp_path / "missing") == 0


@pytest.mark.parametrize(("size", "expected"), [(0, "0 KB"), (2049, "2 KB"), (2 * 1024**2, "2 MB"), (1024**3, "1.0 GB")])
def test_human_size(size: int, expected: str) -> None:
    assert home.human_size(size) == expected


def test_relative_age_keeps_thresholds_and_rounding(monkeypatch) -> None:
    now = datetime(2026, 11, 25, 12).timestamp()
    monkeypatch.setattr(home.time, "time", lambda: now)

    assert home.relative_age(0) == ("date", None)
    assert home.relative_age(now + 10) == ("now", None)
    assert home.relative_age(now - 89) == ("now", None)
    assert home.relative_age(now - 90) == ("minutes", 2)
    assert home.relative_age(now - 3599) == ("minutes", 60)
    assert home.relative_age(now - 3600) == ("hours", 1)
    assert home.relative_age(now - 86399) == ("hours", 24)
    assert home.relative_age(now - 86400) == ("yesterday", None)
    assert home.relative_age(now - 2 * 86400) == ("days", 2)
    assert home.relative_age(now - 29 * 86400) == ("days", 29)
    assert home.relative_age(now - 30 * 86400) == ("date", "26/10/2026")


def test_path_comparisons_keep_platform_case_rules(tmp_path: Path) -> None:
    ui_dir = tmp_path / "UI"
    items = [("sub/Radar.xml", tmp_path / "game" / "Radar.xml")]
    open_path = ui_dir / "sub" / "radar.xml"
    case_insensitive = os.path.normcase("Radar.xml") == "radar.xml"

    assert home.is_same_root(ui_dir, tmp_path / "ui") == case_insensitive
    assert not home.is_same_root(None, ui_dir)
    assert home.pull_affects_open_file(ui_dir, items, open_path) == case_insensitive
    assert home.pull_affects_open_file(ui_dir, items, ui_dir / "sub" / "Radar.xml")
    assert not home.pull_affects_open_file(ui_dir, items, ui_dir / "Radar.xml")
    assert not home.pull_affects_open_file(ui_dir, items, None)


def test_service_does_not_import_qt() -> None:
    code = "import sys, gf_ui_editor.home; print(any(name.startswith('PySide6') for name in sys.modules))"
    env = {**os.environ, "PYTHONPATH": str(Path(home.__file__).parents[1])}
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, check=True)
    assert result.stdout.strip() == "False"
