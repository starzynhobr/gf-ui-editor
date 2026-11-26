"""Exportar para várias resoluções: regras, ajustes guardados, zips e a referência do Harlem."""

from __future__ import annotations

import json
import os
from pathlib import Path
import zipfile

import pytest

from gf_ui_editor import multi_resolution as mr
from gf_ui_editor.xml_document import UIDocument

BASE = (1366, 768)
TEXTURE = '<BackGroundMap BGmap="main.dds"><NorUV NorUVLeft="0" NorUVTop="0" NorUVWidth="8" NorUVHeight="8"/></BackGroundMap>'


def element(window_id: str, x: int, y: int, width: int, height: int, inner: str = "") -> str:
    # WindowHeight é a largura e WindowWidth é a altura, como nos XML do jogo.
    return (
        f'<Style CtrlType="268435456"/><BaseWndProperty WindowID="{window_id}" WindowLeft="{x}" WindowTop="{y}" '
        f'WindowHeight="{width}" WindowWidth="{height}" Visible="1">{inner}</BaseWndProperty>'
    )


def write_window(folder: Path, name: str, root: tuple[int, int, int, int], children: list[str], *, textured_root=False) -> Path:
    x, y, width, height = root
    path = folder / name
    path.write_text(
        f'<Root_Node UI_File_Name="{name}"><Style CtrlType="268435456"/>'
        f'<BaseWndProperty WindowID="1" WindowLeft="{x}" WindowTop="{y}" WindowHeight="{width}" WindowWidth="{height}">'
        f'{TEXTURE if textured_root else ""}'
        f'<Container_Node Child_Cnt="{len(children)}">{"".join(children)}</Container_Node>'
        "</BaseWndProperty></Root_Node>",
        encoding="ascii",
    )
    return path


def source(path: Path, mode: str = "auto", game_dir: Path | None = None) -> mr.WindowSource:
    return mr.WindowSource(path.name, UIDocument.load(path), mode, game_dir)


def visible_at(src: mr.WindowSource, text: str | None, target, index: int) -> tuple[int, int]:
    """Onde o elemento aparece na tela alvo com o XML gerado."""
    document = src.document.with_text(text) if text else src.document
    rect = mr.screen_rects(src, target, document)[index]
    return rect[0], rect[1]


# ---- regra por eixo ----------------------------------------------------------------------
def test_axis_rule_by_piece_center():
    assert mr.infer_axis(0, 100, 1366) == mr.START
    assert mr.infer_axis(633, 100, 1366) == mr.MIDDLE  # centralizado
    assert mr.infer_axis(1266, 100, 1366) == mr.END
    assert mr.infer_axis(0, 2000, 1366) == mr.START  # maior que a tela
    # Pedaço pequeno perto do limite fica na borda; barra larga começando no mesmo X fica no meio.
    assert mr.infer_axis(455, 39, 1366) == mr.START
    assert mr.infer_axis(450, 200, 1366) == mr.MIDDLE
    # Simétrico na borda direita.
    assert mr.infer_axis(1366 - 455 - 39, 39, 1366) == mr.END
    assert mr.infer_axis(1366 - 450 - 200, 200, 1366) == mr.MIDDLE


def test_axis_placement_keeps_edge_distance_or_proportion():
    assert mr.place_axis(mr.START, 20, 100, 1366, 1920) == 20
    assert mr.place_axis(mr.END, 1246, 100, 1366, 1920) == 1920 - 100 - 20
    assert mr.place_axis(mr.MIDDLE, 633, 100, 1366, 1920) == 910  # continua centralizado
    # Numa tela menor, não sai da tela.
    assert mr.place_axis(mr.END, 1700, 200, 1920, 1366) == 1366 - 200 - 20
    assert mr.place_axis(mr.START, 1500, 200, 1920, 1366) == 1166


# ---- janelas fixas (X/Y do XML) ------------------------------------------------------------
def test_fixed_window_pieces_follow_their_corner_or_the_middle(tmp_path):
    # BasicChar fica no X/Y do XML: retrato no canto, barras no meio da base, ícone à direita.
    path = write_window(tmp_path, "BasicChar.xml", (0, 0, 0, 0), [
        element("2", 0, 0, 228, 89, TEXTURE),
        element("5", 570, 700, 226, 55, TEXTURE),
        element("6", 1300, 10, 40, 40, TEXTURE),
        element("60", 1310, 20, 0, 0),  # tamanho zero: vai junto do ícone
    ])
    src = source(path)
    plan = mr.analyze(src, BASE)
    assert plan.kind == mr.FIXED
    rules = {piece.key: piece.rule for piece in plan.pieces}
    assert rules == {"id:2": (mr.START, mr.START), "id:5": (mr.MIDDLE, mr.END), "id:6": (mr.END, mr.START)}
    assert plan.piece("id:6").indexes == (3, 4)

    result = mr.generate(src, plan, (1920, 1080))
    assert result.changed
    assert 0 not in result.geometries and 1 not in result.geometries  # o canto fica igual
    assert visible_at(src, result.text, (1920, 1080), 2) == (847, 1012)  # meio na base: mesma proporção e distância da base
    assert visible_at(src, result.text, (1920, 1080), 3) == (1854, 10)  # 26 px da direita, como antes
    assert visible_at(src, result.text, (1920, 1080), 4) == (1864, 20)


def test_top_left_fixed_window_does_not_change(tmp_path):
    path = write_window(tmp_path, "Team.xml", (0, 0, 0, 0), [
        element("100", 1, 10, 273, 53, TEXTURE),
        element("200", 1, 90, 273, 53, TEXTURE),  # lista: os quadros andam juntos
        element("300", 1, 170, 273, 53, TEXTURE),
        element("400", 1, 250, 273, 53, TEXTURE),
    ])
    src = source(path)
    plan = mr.analyze(src, BASE)
    assert len(plan.pieces) == 1
    assert not mr.generate(src, plan, (2560, 1440)).changed


def test_off_screen_pieces_stay_where_they_are(tmp_path):
    path = write_window(tmp_path, "Team.xml", (0, 0, 0, 0), [
        element("100", 1200, 700, 100, 40, TEXTURE),
        element("900", 5000, 5000, 30, 30, TEXTURE),  # estacionado fora da tela
        element("901", 1340, 300, 100, 40, TEXTURE),  # saindo pela direita
    ])
    src = source(path)
    plan = mr.analyze(src, BASE)
    assert plan.parked == (2,)
    assert plan.piece("id:901").rule == (mr.GAME, mr.GAME)
    result = mr.generate(src, plan, (1920, 1080))
    assert set(result.geometries) == {1}


# ---- janelas que o jogo posiciona ----------------------------------------------------------
def test_game_anchored_window_untouched_stays_identical(tmp_path):
    path = write_window(tmp_path, "Menu.xml", (0, 0, 740, 118), [element("2000", 10, 10, 700, 90, TEXTURE)], textured_root=True)
    src = source(path)
    plan = mr.analyze(src, BASE)
    assert plan.kind == mr.GAME_PLACED
    assert [piece.rule for piece in plan.pieces] == [(mr.GAME, mr.GAME)]
    for target in mr.COMMON_RESOLUTIONS:
        assert not mr.generate(src, plan, target).changed


def test_game_window_with_real_root_follows_the_game_even_if_content_is_offset(tmp_path):
    # CastingBar do Harlem: raiz do tamanho da barra e o conteúdo 162 px acima. O jogo leva junto.
    path = write_window(tmp_path, "CastingBar.xml", (0, 170, 297, 23), [element("1000", 0, 8, 297, 11, TEXTURE)])
    src = source(path)
    plan = mr.analyze(src, BASE)
    assert plan.pieces[0].rule == (mr.GAME, mr.GAME)
    assert not mr.generate(src, plan, (1920, 1080)).changed


def test_detached_content_of_a_game_window_moves_by_the_root_only(tmp_path):
    # ElfAttack: o jogo põe a raiz (0x0) no canto inferior direito; o conteúdo foi solto no meio.
    path = write_window(tmp_path, "ElfAttack.xml", (695, 243, 0, 0), [
        element("10000", 0, 0, 295, 46, TEXTURE),
        element("12000", 7, 7, 32, 32, TEXTURE),
    ])
    src = source(path)
    plan = mr.analyze(src, BASE)
    piece, = plan.pieces
    assert piece.rect == (631, 455, 295, 46)
    assert piece.rule == (mr.MIDDLE, mr.MIDDLE)
    result = mr.generate(src, plan, (1920, 1080))
    assert set(result.geometries) == {0}  # só a raiz muda, como na UI do Harlem
    wanted = mr.target_rect(piece, BASE, (1920, 1080))
    assert visible_at(src, result.text, (1920, 1080), 1) == wanted[:2]
    assert visible_at(src, result.text, (1920, 1080), 2) == (wanted[0] + 7, wanted[1] + 7)


def test_centered_window_from_server_dll(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    (game / "client.ini").write_text("[Option]\n")
    (game / "Violet.dll").write_bytes(b"")
    path = write_window(tmp_path, "SelfEquipment.xml", (552, 174, 0, 0), [element("1001", 0, 0, 279, 347, TEXTURE)])
    src = source(path, game_dir=game)
    plan = mr.analyze(src, BASE)
    assert plan.kind == mr.GAME_PLACED
    assert plan.pieces[0].rule == (mr.START, mr.MIDDLE)
    result = mr.generate(src, plan, (1920, 1080))
    assert visible_at(src, result.text, (1920, 1080), 1) == (131, 366)


def test_manual_adjustment_overrides_the_rule(tmp_path):
    path = write_window(tmp_path, "ElfAttack.xml", (695, 243, 0, 0), [element("10000", 0, 0, 295, 46, TEXTURE)])
    src = source(path)
    plan = mr.analyze(src, BASE)
    result = mr.generate(src, plan, (1920, 1080), {"id:10000": (1064, 811)})
    assert result.pieces[0].adjusted
    assert visible_at(src, result.text, (1920, 1080), 1) == (1064, 811)
    # Um ajuste também move uma janela que o jogo leva sozinho.
    menu = source(write_window(tmp_path, "Menu.xml", (0, 0, 1, 1), [element("2000", 0, 0, 700, 90, TEXTURE)]))
    menu_plan = mr.analyze(menu, BASE)
    moved = mr.generate(menu, menu_plan, (1920, 1080), {menu_plan.pieces[0].key: (100, 100)})
    assert visible_at(menu, moved.text, (1920, 1080), 1) == (100, 100)


def test_user_root_mode_and_unknown_windows(tmp_path):
    path = write_window(tmp_path, "Whatever.xml", (1200, 700, 100, 40), [], textured_root=True)
    unknown = mr.analyze(source(path), BASE)
    assert unknown.kind == mr.UNKNOWN and unknown.pieces[0].rule == (mr.GAME, mr.GAME)
    fixed = mr.analyze(source(path, mode="xml"), BASE)
    assert fixed.kind == mr.FIXED and fixed.pieces[0].rule == (mr.END, mr.END)
    result = mr.generate(source(path, mode="xml"), fixed, (1920, 1080))
    assert result.geometries == {0: (1754, 1012, 100, 40)}
    unused = write_window(tmp_path, "Untitled.xml", (0, 0, 10, 10), [])
    assert mr.analyze(source(unused), BASE) is None


# ---- ajustes e variantes no projeto --------------------------------------------------------
def test_store_keeps_only_what_differs(tmp_path):
    store = mr.ResolutionStore(tmp_path)
    assert store.load().adjustments == {}
    store.set_adjustment("ElfAttack.xml", (1920, 1080), "id:10000", (10, 20))
    settings = store.load()
    assert settings.for_file("elfattack.xml", (1920, 1080)) == {"id:10000": (10, 20)}
    assert settings.for_file("ElfAttack.xml", (1600, 900)) == {}
    store.set_adjustment("ElfAttack.xml", (1920, 1080), "id:10000", None)
    assert json.loads(store.path.read_text(encoding="utf-8"))["adjustments"] == {}

    art = tmp_path / "main.dds"
    art.write_bytes(b"DDS 1920")
    store.add_variant((1920, 1080), "main.dds", art)
    assert store.variants((1920, 1080)) == {"main.dds": tmp_path / "resolutions" / "1920x1080" / "main.dds"}
    assert store.remove_variant((1920, 1080), "MAIN.dds")
    assert not (tmp_path / "resolutions" / "1920x1080").exists()
    with pytest.raises(ValueError):
        store.add_variant((1920, 1080), "../fora.dds", art)
    # Arquivo estragado não derruba a tela.
    store.path.write_text("{", encoding="utf-8")
    assert store.load().adjustments == {}


def test_resolution_keys():
    assert mr.parse_resolution_key("1920x1080") == (1920, 1080)
    assert mr.parse_resolution_key("2560 × 1440") == (2560, 1440)
    assert mr.parse_resolution_key("10x10") is None
    assert mr.resolution_list(["1920x1080", [1920, 1080], (1600, 900), "nada"]) == [(1920, 1080), (1600, 900)]


def make_project(tmp_path: Path):
    from gf_ui_editor.project import Project

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    write_window(source_dir, "ElfAttack.xml", (695, 243, 0, 0), [element("10000", 0, 0, 295, 46, TEXTURE)])
    write_window(source_dir, "Menu.xml", (0, 0, 740, 118), [], textured_root=True)
    (source_dir / "main.dds").write_bytes(b"DDS base")
    return Project.create("Red", source_dir, None, projects_root=tmp_path / "projects")


def test_project_export_one_zip_per_resolution(tmp_path):
    project = make_project(tmp_path)
    store = mr.ResolutionStore(project.root)
    art = tmp_path / "main-1920.dds"
    art.write_bytes(b"DDS 1920")
    store.add_variant((1920, 1080), "main.dds", art)
    targets = [(1366, 768), (1920, 1080)]
    outputs = mr.build_outputs(mr.project_sources(project), BASE, targets, store.load(), store)
    assert sorted(outputs[0].files) == []
    assert sorted(outputs[1].files) == ["ElfAttack.xml", "main.dds"]

    out = tmp_path / "out"
    changed = mr.export_zips(project, out, outputs, whole=False, all_resolution=True)
    assert [(target, path.name, count) for target, path, count in changed] == [
        ((1366, 768), "Red 1366x768.zip", 0),
        ((1920, 1080), "Red 1920x1080.zip", 2),
        (None, "Red All Resolution.zip", 3),
    ]
    assert not (out / "Red 1366x768.zip").exists()
    with zipfile.ZipFile(out / "Red 1920x1080.zip") as archive:
        assert sorted(archive.namelist()) == ["Red 1920x1080/ElfAttack.xml", "Red 1920x1080/main.dds"]
        assert archive.read("Red 1920x1080/main.dds") == b"DDS 1920"
        text = archive.read("Red 1920x1080/ElfAttack.xml").decode("big5")
    assert 'WindowLeft="695"' not in text

    whole = mr.export_zips(project, tmp_path / "whole", outputs, whole=True, all_resolution=False)
    with zipfile.ZipFile(whole[0][1]) as archive:
        assert sorted(archive.namelist()) == ["Red 1366x768/ElfAttack.xml", "Red 1366x768/Menu.xml", "Red 1366x768/main.dds"]
        assert archive.read("Red 1366x768/main.dds") == b"DDS base"
    with zipfile.ZipFile(whole[1][1]) as archive:
        assert archive.read("Red 1920x1080/main.dds") == b"DDS 1920"


def test_project_sources_respect_root_mode(tmp_path):
    project = make_project(tmp_path)
    project.root_modes["Menu.xml"] = "xml"
    modes = {item.relative: item.mode for item in mr.project_sources(project)}
    assert modes == {"ElfAttack.xml": "auto", "Menu.xml": "xml"}


# ---- referência: as UIs do Harlem ----------------------------------------------------------
HARLEM = Path(os.environ.get("GF_HARLEM_UIS", Path.home() / "Downloads" / "UI_s"))
TARGETS = ((1600, 900), (1920, 1080), (2560, 1440))


def harlem_zip(folder: Path, resolution) -> Path | None:
    key = mr.resolution_key(resolution)
    return next((path for path in sorted(folder.glob("*.zip")) if key in path.name), None)


def harlem_documents(archive: Path, sandbox: Path) -> dict[str, UIDocument]:
    """Os XML do zip, copiados para a caixa de areia (os zips nunca entram no repositório)."""
    documents = {}
    with zipfile.ZipFile(archive) as data:
        for info in data.infolist():
            name = info.filename.rsplit("/", 1)[-1]
            if info.is_dir() or not name.lower().endswith(".xml"):
                continue
            target = sandbox / archive.stem / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data.read(info))
            try:
                documents[name] = UIDocument.load(target)
            except Exception:  # noqa: BLE001 - XML quebrado na UI dele não entra na conta
                continue
    return documents


def harlem_rect(src: mr.WindowSource, document: UIDocument, ids: list[str], target) -> tuple | None:
    rects = mr.screen_rects(src, target, document)
    first: dict[str, int] = {}
    for item in document.elements:
        first.setdefault(item.window_id, item.index)
    found = [rects[first[i]] for i in ids if i in first]
    found = [r for r in found if r[0] < target[0] and r[1] < target[1] and r[0] + max(1, r[2]) > 0 and r[1] + max(1, r[3]) > 0]
    return mr._union((r[0], r[1], max(1, r[2]), max(1, r[3])) for r in found) if found else None


@pytest.mark.parametrize("set_name", ["RED", "BlueBerry", "Drahsin"])
def test_reference_against_harlem_uis(set_name, tmp_path, capsys):
    folder = HARLEM / set_name
    base_zip = harlem_zip(folder, BASE) if folder.is_dir() else None
    if base_zip is None:
        pytest.skip(f"UIs do Harlem não encontradas em {folder}")
    game = tmp_path / "game"
    game.mkdir()
    (game / "client.ini").write_text("[Option]\n")
    (game / "Violet.dll").write_bytes(b"")  # Look/SelfEquipment são centralizadas pelo Violet.dll
    base_docs = harlem_documents(base_zip, tmp_path)
    sources = [mr.WindowSource(name, document, "auto", game) for name, document in base_docs.items()]
    targets = [target for target in TARGETS if harlem_zip(folder, target)]
    outputs = mr.build_outputs(sources, BASE, targets, mr.ResolutionSettings())
    by_name = {src.relative: src for src in sources}
    plans = {src.relative: mr.analyze(src, BASE) for src in sources}

    report = []
    for output in outputs:
        theirs = harlem_documents(harlem_zip(folder, output.target), tmp_path)
        harlem_changed = {
            name for name, document in theirs.items()
            if name in base_docs and document.raw != base_docs[name].raw
        }
        # Nada muda sem o Harlem também ter mudado (nenhum falso positivo nos ~320 XML).
        assert set(output.files) <= harlem_changed, set(output.files) - harlem_changed
        assert "ElfAttack.xml" in output.files
        for result in output.windows:
            if not result.changed:
                continue
            src, plan = by_name[result.relative], plans[result.relative]
            for placement, piece in zip(result.pieces, plan.pieces):
                ids = [src.document.elements[i].window_id for i in piece.indexes]
                got = harlem_rect(src, theirs[result.relative], ids, output.target)
                if got is None:
                    continue
                error = (placement.rect[0] - got[0], placement.rect[1] - got[1])
                report.append((result.relative, mr.resolution_key(output.target), placement.key, mr.describe_rule(piece.rule), placement.rect[:2], got[:2], error))
            # O XML gerado põe cada pedaço exatamente onde a regra mandou.
            document = src.document.with_text(result.text)
            rects = mr.screen_rects(src, output.target, document)
            for placement, piece in zip(result.pieces, plan.pieces):
                drawn = mr._union((rects[i][0], rects[i][1], max(1, rects[i][2]), max(1, rects[i][3])) for i in piece.indexes)
                assert drawn[:2] == placement.rect[:2], (result.relative, placement.key)

    errors = {(name, res, key): error for name, res, key, _rule, _ours, _theirs, error in report}
    # Janelas onde a regra coincide com a escolha dele (tolerância de poucos pixels).
    if set_name in ("RED", "BlueBerry"):
        assert all(abs(v) <= 12 for v in errors[("LookEquipment.xml", "1920x1080", "id:1001")])
        assert all(abs(v) <= 12 for v in errors[("SelfEquipment.xml", "1920x1080", "id:1001")])
        assert errors[("BasicChar.xml", "1920x1080", "id:2")] == (0, 0)
        for target in TARGETS:
            assert errors[("BasicChar.xml", mr.resolution_key(target), "id:10000")] == (0, 0)
    with capsys.disabled():
        print(f"\n[{set_name}] janela / resolução / pedaço / regra / nossa posição / a dele / diferença")
        for row in report:
            print("  ", *row)
