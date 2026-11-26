import subprocess
import sys
import zlib
from pathlib import Path

from gf_ui_editor import game_text_updates as updates
from gf_ui_editor.text_data import TRANSLATE_DIR, TextEdit, publish_edits


def _write_game(game: Path, files: dict[str, str]) -> None:
    """Grava os .ini e o GameDataFileListT.txt com os CRCs oficiais deles."""
    folder = game / TRANSLATE_DIR
    folder.mkdir(parents=True, exist_ok=True)
    lines = []
    for name, text in files.items():
        data = text.encode("cp1252")
        (folder / name).write_bytes(data)
        lines.append(f"{name}|{len(data)}|{zlib.crc32(data) & 0xFFFFFFFF:08X}|{len(data)}|0|")
    (game / "GameDataFileListT.txt").write_text("\r\n".join(lines) + "\r\n", encoding="latin-1")


V1 = "1|Espada|\r\n2|Escudo|\r\n3|Elmo|\r\n"
V2 = "1|Espada Longa|\r\n2|Escudo|\r\n4|Botas|\r\n"


def test_first_check_only_takes_the_snapshot(tmp_path: Path) -> None:
    game, root = tmp_path / "game", tmp_path / "projects"
    _write_game(game, {"T_Item.ini": V1})
    assert updates.check(game, root) is None
    assert updates.TextSnapshots(root).seen(game) == updates.official_crcs(game)
    assert updates.check(game, root) is None  # nada mudou


def test_update_lists_new_changed_and_removed_ids(tmp_path: Path) -> None:
    game, root = tmp_path / "game", tmp_path / "projects"
    _write_game(game, {"T_Item.ini": V1, "T_Other.ini": "9|x|\r\n"})
    updates.check(game, root)
    _write_game(game, {"T_Item.ini": V2, "T_Other.ini": "9|x|\r\n"})  # o launcher baixou a versão nova
    update = updates.check(game, root)
    assert update is not None and update.changed_files == ["T_Item.ini"]
    [item] = update.files
    assert item.new_ids == ["4"] and item.removed_ids == ["3"]
    assert item.changed == [("1", ["Espada"], ["Espada Longa"])]
    assert update.new_ids == 1 and update.changed_texts == 1
    # Continua avisando até o usuário marcar como visto.
    assert updates.check(game, root) is not None
    updates.acknowledge(game, root)
    assert updates.check(game, root) is None


def test_line_endings_alone_are_not_a_change(tmp_path: Path) -> None:
    game, root = tmp_path / "game", tmp_path / "projects"
    _write_game(game, {"T_Item.ini": "1|linha um\r\nlinha dois|\r\n"})
    updates.check(game, root)
    _write_game(game, {"T_Item.ini": "1|linha um\nlinha dois|\n"})
    update = updates.check(game, root)
    assert update is not None and update.changed_files == ["T_Item.ini"] and update.files == []


def test_published_files_are_not_taken_as_official(tmp_path: Path) -> None:
    game, root = tmp_path / "game", tmp_path / "projects"
    _write_game(game, {"T_Item.ini": V1})
    edits = {"T_Item.ini": {"1": TextEdit(["Minha Espada"], ["Espada"])}}
    publish_edits(game, edits)  # o jogo agora tem a edição; o CRC oficial não bate
    assert updates.check(game, root) is None
    blobs = list((root / updates.CACHE_FOLDER).glob("*.ini.gz"))
    assert blobs == []  # nada guardado: o arquivo atual não é o oficial


def test_update_without_previous_snapshot_is_reported_as_unavailable(tmp_path: Path) -> None:
    game, root = tmp_path / "game", tmp_path / "projects"
    _write_game(game, {"T_Item.ini": V1})
    publish_edits(game, {"T_Item.ini": {"1": TextEdit(["Minha"], ["Espada"])}})
    updates.check(game, root)  # visto, mas sem retrato (arquivo editado)
    _write_game(game, {"T_Item.ini": V2})
    update = updates.check(game, root)
    assert update is not None and update.unavailable == ["T_Item.ini"] and update.files == []


def test_project_impact_finds_reverted_changed_and_missing_edits(tmp_path: Path) -> None:
    game = tmp_path / "game"
    _write_game(game, {"T_Item.ini": V2})  # atualização já baixada: jogo com o oficial novo
    edits = {
        "T_Item.ini": {
            "1": TextEdit(["Minha Espada"], ["Espada"]),  # oficial mudou por baixo e a edição sumiu do jogo
            "2": TextEdit(["Meu Escudo"], ["Escudo"]),  # só desfeita
            "3": TextEdit(["Meu Elmo"], ["Elmo"]),  # ID sumiu
        }
    }
    impact = updates.project_impact(game, edits)
    assert sorted(impact.reverted) == [("T_Item.ini", "1"), ("T_Item.ini", "2")]
    assert impact.official_changed == [("T_Item.ini", "1", ["Espada"], ["Espada Longa"])]
    assert impact.missing == [("T_Item.ini", "3")]
    # Depois do reenvio (F5) nada mais está desfeito.
    publish_edits(game, {"T_Item.ini": {k: v for k, v in edits["T_Item.ini"].items() if k != "3"}})
    again = updates.project_impact(game, edits)
    assert again.reverted == [] and again.official_changed == []


def test_publishing_texts_keeps_the_official_snapshot_first(tmp_path: Path, monkeypatch) -> None:
    from types import SimpleNamespace

    from gf_ui_editor import project as project_module, publishing, text_data

    game, root, project_root = tmp_path / "game", tmp_path / "projects", tmp_path / "proj"
    project_root.mkdir()
    monkeypatch.setattr(project_module, "PROJECTS_ROOT", root)
    _write_game(game, {"T_Item.ini": V1})
    text_data.save_edits(project_root, {"T_Item.ini": {"1": TextEdit(["Minha Espada"], ["Espada"])}})
    project = SimpleNamespace(root=project_root, game_dir=game, history_dir=project_root / ".history")
    outcome = publishing.publish_texts(project, texts_disabled=False)
    assert outcome.changed == 1
    crc = updates.official_crcs(game)["T_Item.ini"]
    snapshot = updates.TextSnapshots(root).load("T_Item.ini", crc)
    assert snapshot is not None and snapshot.by_id["1"].fields == ["Espada"]  # o oficial, não a edição
    # Com o retrato, a atualização seguinte é comparada mesmo com o jogo editado.
    updates.check(game, root)
    _write_game(game, {"T_Item.ini": V2})
    update = updates.check(game, root)
    assert update is not None and update.unavailable == [] and update.files[0].new_ids == ["4"]


def test_service_does_not_import_qt() -> None:
    code = "import sys, gf_ui_editor.game_text_updates; print(any(m.startswith('PySide6') for m in sys.modules))"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "False"


def test_bridge_reports_update_and_reverted_edits_until_acknowledged(tmp_path: Path, monkeypatch) -> None:
    from types import SimpleNamespace

    from gf_ui_editor import project as project_module, text_data
    from gf_ui_editor.web_api.text_updates import TextUpdatesApi

    game, root, project_root = tmp_path / "game", tmp_path / "projects", tmp_path / "proj"
    project_root.mkdir()
    monkeypatch.setattr(project_module, "PROJECTS_ROOT", root)
    _write_game(game, {"T_Item.ini": V1})
    api = TextUpdatesApi()
    api._project = SimpleNamespace(root=project_root, game_dir=game)
    assert api.text_updates_check() is None  # primeira vez: só o retrato
    text_data.save_edits(project_root, {"T_Item.ini": {"2": TextEdit(["Meu Escudo"], ["Escudo"])}})
    _write_game(game, {"T_Item.ini": V2})  # atualização baixada; a edição não está no jogo
    report = api.text_updates_check()
    assert report["update"]["new_ids"] == 1 and report["update"]["changed_texts"] == 1
    assert report["reverted"] == [{"file": "T_Item.ini", "id": "2"}]
    api.text_updates_acknowledge()
    still = api.text_updates_check()
    assert still["update"] is None and still["reverted"]  # visto, mas a edição continua a reenviar
