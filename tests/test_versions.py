import json
import shutil
import zipfile
import zlib
from pathlib import Path

import pytest

from gf_ui_editor import cleanup, multi_resolution, text_data, versions
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


def test_resolutions_adjustments_round_trip_and_removal(tmp_path: Path) -> None:
    game = _game(tmp_path)
    project = Project.create("V", game / "UI", game, projects_root=tmp_path / "projects")
    store = multi_resolution.ResolutionStore(project.root)

    # Versão antes de existir qualquer ajuste de resolução.
    before_res = versions.save_version(project, "sem resolucoes")
    assert versions.list_versions(project)[0].resolutions == 0

    settings = multi_resolution.ResolutionSettings(
        base=(1366, 768),
        targets=[(1920, 1080), (2560, 1440)],
        adjustments={"Radar.xml": {"1920x1080": {"id:1": (120, 40)}}},
    )
    store.save(settings)
    with_res = versions.save_version(project, "com ajustes")
    listed = {v.label: v for v in versions.list_versions(project)}
    assert listed["com ajustes"].resolutions == 1
    assert listed["com ajustes"].files == 1

    # Muda os ajustes e restaura a versão "com ajustes".
    store.set_adjustment("Radar.xml", (1920, 1080), "id:1", (999, 888))
    store.set_adjustment("Menu.xml", (2560, 1440), "id:2", (10, 20))
    result = versions.restore_version(project, with_res)
    assert result.written == 1 and result.removed == 0 and result.unresolved == []
    restored = store.load()
    assert restored.base == (1366, 768)
    assert restored.targets == [(1920, 1080), (2560, 1440)]
    assert restored.adjustments == {"Radar.xml": {"1920x1080": {"id:1": (120, 40)}}}
    # O resolutions.json anterior foi guardado no histórico e entra na limpeza.
    history_files = list((project.history_dir / multi_resolution.STORE_NAME).glob("*.json"))
    assert len(history_files) == 1
    assert "999" in history_files[0].read_text(encoding="utf-8")
    assert any(path.parent.name == multi_resolution.STORE_NAME for path in cleanup.scan(project).history_all)

    # Restaurar a versão salva antes dos ajustes remove resolutions.json (com backup no histórico).
    result_clear = versions.restore_version(project, before_res)
    assert result_clear.removed == 1 and not store.path.exists()
    assert len(list((project.history_dir / multi_resolution.STORE_NAME).glob("*.json"))) == 2


def test_resolution_variants_dds_dedup_restore_and_branch(tmp_path: Path) -> None:
    game = _game(tmp_path)
    project = Project.create("V", game / "UI", game, projects_root=tmp_path / "projects")
    store = multi_resolution.ResolutionStore(project.root)

    # Um .dds alterado na UI + variantes: uma igual à da UI, duas iguais entre si e uma exclusiva.
    (project.ui_dir / "skin" / "m.dds").write_bytes(b"DDS-MODIFIED")
    dds_1080 = tmp_path / "main_1080.dds"
    dds_1080.write_bytes(b"DDS-1080-CUSTOM")
    dds_same_ui = tmp_path / "same_ui.dds"
    dds_same_ui.write_bytes(b"DDS-MODIFIED")

    store.add_variant((1920, 1080), "main.dds", dds_1080)
    store.add_variant((2560, 1440), "main.dds", dds_1080)  # mesmo conteúdo da 1920x1080
    store.add_variant((1920, 1080), "skin/m.dds", dds_same_ui)  # mesmo conteúdo de ui/skin/m.dds

    checkpoint = versions.save_version(project, "variantes")
    with zipfile.ZipFile(checkpoint) as archive:
        names = set(archive.namelist())
        assert "ui/skin/m.dds" in names
        assert "resolutions/1920x1080/main.dds" in names
        # Deduplicadas: não entram duplicadas no .zip.
        assert "resolutions/2560x1440/main.dds" not in names
        assert "resolutions/1920x1080/skin/m.dds" not in names
    [listed] = versions.list_versions(project)
    assert listed.resolutions == 3 and listed.files == 4

    # Altera uma variante, apaga outra e cria uma variante nova que não existia na versão.
    (project.root / "resolutions" / "1920x1080" / "main.dds").write_bytes(b"DDS-BROKEN")
    store.remove_variant((2560, 1440), "main.dds")
    extra = tmp_path / "extra.dds"
    extra.write_bytes(b"DDS-EXTRA")
    store.add_variant((1600, 900), "extra.dds", extra)

    # Criar projeto a partir da versão traz as variantes restauradas.
    branched_root = versions.project_from_version(project, checkpoint, "Ramo Res")
    assert (branched_root / "resolutions" / "1920x1080" / "main.dds").read_bytes() == b"DDS-1080-CUSTOM"
    assert (branched_root / "resolutions" / "2560x1440" / "main.dds").read_bytes() == b"DDS-1080-CUSTOM"
    assert not (branched_root / "resolutions" / "1600x900" / "extra.dds").exists()

    # Restaurar no projeto original devolve tudo e limpa a pasta vazia 1600x900.
    result = versions.restore_version(project, checkpoint)
    assert result.unresolved == []
    assert (project.root / "resolutions" / "1920x1080" / "main.dds").read_bytes() == b"DDS-1080-CUSTOM"
    assert (project.root / "resolutions" / "2560x1440" / "main.dds").read_bytes() == b"DDS-1080-CUSTOM"
    assert (project.root / "resolutions" / "1920x1080" / "skin" / "m.dds").read_bytes() == b"DDS-MODIFIED"
    assert not (project.root / "resolutions" / "1600x900").exists()
    # A variante alterada e a removida foram para o histórico.
    assert any(p.read_bytes() == b"DDS-BROKEN" for p in (project.history_dir / "resolutions" / "1920x1080" / "main.dds").glob("*.dds"))
    assert any(p.read_bytes() == b"DDS-EXTRA" for p in (project.history_dir / "resolutions" / "1600x900" / "extra.dds").glob("*.dds"))


def test_old_version_without_resolutions_preserves_current_resolutions(tmp_path: Path) -> None:
    game = _game(tmp_path)
    project = Project.create("V", game / "UI", game, projects_root=tmp_path / "projects")
    (project.ui_dir / "Radar.xml").write_text("<antigo/>", encoding="utf-8")

    # Simula uma versão antiga (sem a chave "resolutions" em version.json).
    old_zip = versions.versions_dir(project) / "20260101-120000_antiga.zip"
    old_zip.parent.mkdir(parents=True, exist_ok=True)
    old_manifest = {
        "format": versions.FORMAT,
        "app_version": "0.7.0",
        "name": project.name,
        "label": "antiga",
        "created": "2026-01-01T12:00:00",
        "files": ["Menu.xml", "Radar.xml", "skin/m.dds"],
        "shipped": ["Radar.xml"],
        "root_modes": {},
        "reference_layers": [],
        "text_edits": {},
    }
    with zipfile.ZipFile(old_zip, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(versions.MANIFEST, json.dumps(old_manifest))
        archive.writestr("ui/Radar.xml", "<antigo/>")

    # Estado atual: Radar mudou e existem ajustes e variante de resolução.
    (project.ui_dir / "Radar.xml").write_text("<atual/>", encoding="utf-8")
    store = multi_resolution.ResolutionStore(project.root)
    store.set_adjustment("Radar.xml", (1920, 1080), "id:1", (321, 123))
    dds = tmp_path / "v.dds"
    dds.write_bytes(b"DDS-KEEP")
    store.add_variant((1920, 1080), "main.dds", dds)

    result = versions.restore_version(project, old_zip)
    assert result.unresolved == []
    assert (project.ui_dir / "Radar.xml").read_text(encoding="utf-8") == "<antigo/>"
    # Compatibilidade: ajustes e variantes atuais continuam intactos.
    assert store.load().adjustments == {"Radar.xml": {"1920x1080": {"id:1": (321, 123)}}}
    assert (project.root / "resolutions" / "1920x1080" / "main.dds").read_bytes() == b"DDS-KEEP"


def test_light_project_pins_official_resolution_variant_by_crc(tmp_path: Path) -> None:
    game = _game(tmp_path)
    project = Project.create("Leve", game / "UI", game, projects_root=tmp_path / "projects", light=True)
    store = multi_resolution.ResolutionStore(project.root)
    store.set_adjustment("Radar.xml", (1920, 1080), "id:1", (50, 60))

    # Uma variante com os mesmos bytes do arquivo oficial skin/m.dds e outra customizada.
    store.add_variant((1600, 900), "skin/m.dds", game / "UI" / "skin" / "m.dds")
    custom_dds = tmp_path / "custom.dds"
    custom_dds.write_bytes(b"DDS-LIGHT-CUSTOM")
    store.add_variant((1920, 1080), "main.dds", custom_dds)

    checkpoint = versions.save_version(project, "leve com res")
    with zipfile.ZipFile(checkpoint) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read(versions.MANIFEST).decode("utf-8"))
        assert "resolutions.json" in names
        assert "resolutions/1920x1080/main.dds" in names
        # Variante igual ao oficial vai referenciada pela base compartilhada (.official-ui), fora do .zip.
        assert "resolutions/1600x900/skin/m.dds" not in names
        assert "1600x900/skin/m.dds" in manifest["resolutions"]["official_files"]

    # Altera os ajustes, sobrescreve as variantes e troca o arquivo na pasta do jogo.
    store.set_adjustment("Radar.xml", (1920, 1080), "id:1", (9, 9))
    (project.root / "resolutions" / "1600x900" / "skin" / "m.dds").write_bytes(b"changed")
    (project.root / "resolutions" / "1920x1080" / "main.dds").write_bytes(b"changed")
    (game / "UI" / "skin" / "m.dds").write_bytes(b"updated game")

    result = versions.restore_version(project, checkpoint)
    assert result.unresolved == []
    assert result.reverted == 1 and result.written == 2
    assert Project.load(project.root).light is True
    assert store.load().adjustments == {"Radar.xml": {"1920x1080": {"id:1": (50, 60)}}}
    assert (project.root / "resolutions" / "1600x900" / "skin" / "m.dds").read_bytes() == b"dds"
    assert (project.root / "resolutions" / "1920x1080" / "main.dds").read_bytes() == b"DDS-LIGHT-CUSTOM"


def test_restore_failure_does_not_leave_half_written_file_or_temp(tmp_path: Path, monkeypatch) -> None:
    game = _game(tmp_path)
    project = Project.create("V", game / "UI", game, projects_root=tmp_path / "projects")
    store = multi_resolution.ResolutionStore(project.root)
    store.set_adjustment("Radar.xml", (1920, 1080), "id:1", (10, 20))
    dds = tmp_path / "main.dds"
    dds.write_bytes(b"DDS-V1")
    store.add_variant((1920, 1080), "main.dds", dds)
    checkpoint = versions.save_version(project, "v1")

    # Estado atual antes da restauração que vai falhar no meio da escrita.
    store.set_adjustment("Radar.xml", (1920, 1080), "id:1", (77, 88))
    variant_path = project.root / "resolutions" / "1920x1080" / "main.dds"
    variant_path.write_bytes(b"DDS-CURRENT-INTACT")

    real_copy2 = shutil.copy2

    def flaky_copy2(src, dst, *args, **kwargs):
        if Path(dst).parent == variant_path.parent and str(dst).endswith(versions.TEMP_SUFFIX):
            Path(dst).write_bytes(b"HALF-")
            raise OSError("disco cheio")
        return real_copy2(src, dst, *args, **kwargs)

    monkeypatch.setattr(versions.shutil, "copy2", flaky_copy2)
    with pytest.raises(OSError, match="disco cheio"):
        versions.restore_version(project, checkpoint)

    # O arquivo original permaneceu inteiro e nenhum temporário sobrou na pasta.
    assert variant_path.read_bytes() == b"DDS-CURRENT-INTACT"
    assert not list(variant_path.parent.glob(f"*{versions.TEMP_SUFFIX}"))


def test_restore_rejects_path_traversal_in_resolutions(tmp_path: Path) -> None:
    game = _game(tmp_path)
    project = Project.create("V", game / "UI", game, projects_root=tmp_path / "projects")
    bad_zip = versions.versions_dir(project) / "20260101-120000_bad.zip"
    bad_zip.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "format": versions.FORMAT,
        "name": project.name,
        "label": "bad",
        "created": "2026-01-01T12:00:00",
        "files": [],
        "shipped": [],
        "resolutions": {"config": False, "files": ["../escape.dds"]},
    }
    with zipfile.ZipFile(bad_zip, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(versions.MANIFEST, json.dumps(manifest))
        archive.writestr("resolutions/../escape.dds", b"evil")

    with pytest.raises(ValueError, match="Caminho inválido"):
        versions.restore_version(project, bad_zip)
    assert not (project.root / "escape.dds").exists()
