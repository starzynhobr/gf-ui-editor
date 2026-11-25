"""Geometria da raiz e área fantasma: tabelas de entrada -> geometria, sem Qt."""
import os
from pathlib import Path
import subprocess
import sys

import pytest

from gf_ui_editor import window_geometry as wg
from gf_ui_editor.game_layout import root_screen_position

SCREEN = (1920, 1080)


def centered(geometry):
    """Onde o jogo põe a raiz de uma janela centralizada (Storage.xml)."""
    return root_screen_position("Storage.xml", SCREEN, geometry)


def top_right(geometry):
    return root_screen_position("Radar.xml", SCREEN, geometry)


@pytest.mark.parametrize(
    ("outer", "inner", "expected"),
    [
        ((0, 0, 10, 10), (0, 0, 10, 10), True),  # bordas valem
        ((0, 0, 10, 10), (2, 2, 3, 3), True),
        ((0, 0, 10, 10), (5, 5, 6, 1), False),
        ((0, 0, 10, 10), (-1, 0, 2, 2), False),
        ((0, 0, 0, 0), (0, 0, 0, 0), False),  # nulo nunca contém
        ((0, 0, 10, 10), (3, 3, 0, 4), False),  # nulo nunca está contido
        ((10, 10, -10, -10), (2, 2, 3, 3), True),  # largura negativa, como no Qt
    ],
)
def test_contains_matches_qrectf(outer, inner, expected) -> None:
    assert wg.contains(outer, inner) is expected


def test_content_bounds_unites_elements_with_preview_offset() -> None:
    assert wg.content_bounds([]) is None
    elements = [((10, 20, 30, 40), (0, 0)), ((-5, 100, 0, 0), (0, 0)), ((50, 0, 10, 10), (0, 12.5))]
    assert wg.content_bounds(elements) == (-5, 12.5, 65, 88.5)  # 0 x 0 conta com 1 px
    assert wg.content_bounds([((7, 8, 0, 3), (1, 1))]) == (8, 9, 1, 3)


@pytest.mark.parametrize(
    ("root", "bounds", "background", "expected"),
    [
        ((134, 302, 434, 306), (140, 310, 20, 20), False, None),  # conteúdo em cima da raiz
        ((600, 50, 200, 100), (0, 0, 200, 100), False, (600, 50, 200, 100)),  # saiu de cima
        ((600, 50, 200, 100), (0, 0, 200, 100), True, None),  # fundo visível: não é invisível
        ((600, 50, 1, 1), (0, 0, 200, 100), False, None),  # já encolhida
        ((600, 50, 1, 0), (0, 0, 200, 100), False, None),
        ((600, 50, 2, 0), (0, 0, 200, 100), False, (600, 50, 2, 1)),
        ((0, 0, 100, 100), (-8, -8, 116, 116), False, None),  # conteúdo maior, dentro da folga
        ((0, 0, 100, 100), (-8, 0, 50, 50), False, None),  # conteúdo dentro da raiz + folga
        ((0, 0, 100, 100), (-9, 0, 50, 50), False, (0, 0, 100, 100)),  # 1 px além da folga
        ((0, 0, 100, 100), (-9, 0, 120, 50), False, (0, 0, 100, 100)),
        ((0, 0, 100, 100), (4, 4, 104, 104), False, None),  # passa da raiz, mas dentro da folga
        ((0, 0, 100, 100), (4, 4, 105, 105), False, None),  # raiz dentro do conteúdo + folga
        ((0, 0, 100, 100), (10, 10, 105, 105), False, (0, 0, 100, 100)),  # nenhuma contém a outra
    ],
)
def test_ghost_area_table(root, bounds, background, expected) -> None:
    assert wg.ghost_area(root, bounds, lambda: background) == expected


def test_ghost_area_reads_the_background_only_at_the_end() -> None:
    calls: list[int] = []

    def background() -> bool:
        calls.append(1)
        return False

    wg.ghost_area((0, 0, 100, 100), (10, 10, 20, 20), background)
    wg.ghost_area((0, 0, 1, 1), (500, 500, 20, 20), background)
    assert calls == []
    wg.ghost_area((0, 0, 100, 100), (500, 500, 20, 20), background)
    assert calls == [1]


@pytest.mark.parametrize(
    ("geometry", "width", "height", "screen_for", "expected"),
    [
        # Centralizada: (1920-1)//2 - (1920-434)//2 = 216 e (1080-1)//2 - (1080-306)//2 = 152.
        ((134, 302, 434, 306), 1, 1, centered, (134 + 216, 302 + 152, 1, 1)),
        ((134, 302, 434, 306), 434, 306, centered, (134, 302, 434, 306)),
        ((0, 0, 100, 50), 140, 70, centered, (-20, -10, 140, 70)),
        ((-63, -12, 740, 118), 660, 78, centered, (-23, 8, 660, 78)),
    ],
)
def test_resized_root_keeps_content_in_place(geometry, width, height, screen_for, expected) -> None:
    assert wg.resized_root(geometry, width, height, screen_for) == expected
    if (width, height) == (1, 1):
        assert wg.collapsed_root(geometry, screen_for) == expected


def test_resized_root_follows_a_corner_anchor() -> None:
    geometry = (10, 0, 200, 120)
    resized = wg.resized_root(geometry, 240, 120, top_right)
    # A raiz anda exatamente o que o jogo a deslocaria por ficar 40 px mais larga.
    shift = top_right((10, 0, 240, 120))[0] - top_right(geometry)[0]
    assert resized == (10 + shift, 0, 240, 120)


class Calls:
    """Funções da interface, gravando o que foi chamado."""

    def __init__(self, set_by_game=True, frame=(500, 300), shown_at=None, ghost=lambda g: g):
        self.log: list[str] = []
        self._set_by_game, self._frame, self._shown_at, self._ghost = set_by_game, frame, shown_at, ghost

    def kwargs(self):
        def set_by_game():
            self.log.append("set_by_game")
            return self._set_by_game

        def resize_root(geometry, width, height):
            self.log.append(f"resize {geometry} {width}x{height}")
            return wg.resized_root(geometry, width, height, centered)

        def frame_on_screen():
            self.log.append("frame")
            return self._frame

        def without_ghost_area(geometry):
            self.log.append(f"without_ghost {geometry}")
            return self._ghost(geometry)

        def preview_default_position():
            self.log.append("preview_default")
            return self._shown_at

        return dict(
            set_by_game=set_by_game, resize_root=resize_root, frame_on_screen=frame_on_screen,
            without_ghost_area=without_ghost_area, preview_default_position=preview_default_position,
        )


GEOMETRIES = {0: (134, 302, 434, 306), 1: (140, 310, 20, 20), 2: (200, 320, 10, 10)}


def test_changes_without_the_root_pass_through_untouched() -> None:
    calls = Calls()
    changes = {1: ((140, 310, 20, 20), (150, 310, 20, 20))}
    assert wg.root_move_as_screen_move(changes, GEOMETRIES, set(), **calls.kwargs()) is changes
    assert calls.log == []


def test_root_of_a_window_the_game_places_moves_the_other_way() -> None:
    calls = Calls()
    change = {0: ((134, 302, 434, 306), (134 - 463, 302 + 4, 434, 306))}
    assert wg.root_move_as_screen_move(change, GEOMETRIES, set(), **calls.kwargs()) == {
        0: (GEOMETRIES[0], (134 + 463, 302 - 4, 434, 306))
    }
    assert calls.log == ["set_by_game", "frame", "without_ghost (597, 298, 434, 306)"]


def test_root_move_collapses_when_the_ui_says_a_ghost_would_stay() -> None:
    calls = Calls(ghost=lambda g: wg.collapsed_root(g, centered))
    change = {0: ((134, 302, 434, 306), (134 - 463, 302 + 4, 434, 306))}
    result = wg.root_move_as_screen_move(change, GEOMETRIES, set(), **calls.kwargs())
    assert result == {0: (GEOMETRIES[0], (134 + 463 + 216, 302 - 4 + 152, 1, 1))}  # caso do teste de interface


def test_frame_drag_uses_the_drag_delta_not_the_xml_position() -> None:
    # A moldura pode estar desenhada fora do X/Y do XML: vale só o deslocamento.
    calls = Calls()
    change = {0: ((900, 500, 434, 306), (910, 480, 434, 306))}
    assert wg.root_move_as_screen_move(change, GEOMETRIES, set(), **calls.kwargs())[0][1] == (124, 322, 434, 306)


def test_root_of_a_placed_window_without_frame_or_movement_skips_the_ghost_check() -> None:
    calls = Calls(frame=None)
    change = {0: ((134, 302, 434, 306), (100, 302, 434, 306))}
    assert wg.root_move_as_screen_move(change, GEOMETRIES, set(), **calls.kwargs())[0][1] == (168, 302, 434, 306)
    assert calls.log == ["set_by_game", "frame"]
    calls = Calls()
    same = {0: ((134, 302, 434, 306), (134, 302, 434, 306))}
    assert wg.root_move_as_screen_move(same, GEOMETRIES, set(), **calls.kwargs())[0][1] == GEOMETRIES[0]
    assert calls.log == ["set_by_game", "frame"]  # sem deslocamento: não procura área fantasma


def test_resizing_the_root_of_a_window_the_game_places_keeps_content() -> None:
    calls = Calls()
    change = {0: ((134, 302, 434, 306), (124, 297, 474, 326))}
    result = wg.root_move_as_screen_move(change, GEOMETRIES, set(), **calls.kwargs())
    assert result == {0: (GEOMETRIES[0], (124, 297, 474, 326))}
    assert calls.log == ["set_by_game", "resize (144, 307, 434, 306) 474x326"]


def test_dragging_the_root_of_a_free_window_moves_everything_but_locked() -> None:
    calls = Calls(set_by_game=False)
    change = {0: ((134, 302, 434, 306), (164, 282, 434, 306))}
    result = wg.root_move_as_screen_move(change, GEOMETRIES, {2}, **calls.kwargs())
    assert result == {
        0: (GEOMETRIES[0], (164, 282, 434, 306)),
        1: (GEOMETRIES[1], (170, 290, 20, 20)),
    }
    assert list(result) == [0, 1]
    assert calls.log == ["set_by_game", "preview_default"]
    locked_root = wg.root_move_as_screen_move(change, GEOMETRIES, {0}, **Calls(set_by_game=False).kwargs())
    assert set(locked_root) == {0, 1, 2}  # a raiz sempre vai


def test_free_window_shown_at_its_saved_position_lands_where_it_was_dropped() -> None:
    calls = Calls(set_by_game=False, shown_at=(300, 200))
    change = {0: ((134, 302, 434, 306), (174, 332, 434, 306))}
    result = wg.root_move_as_screen_move(change, GEOMETRIES, set(), **calls.kwargs())
    assert result[0] == (GEOMETRIES[0], (340, 230, 434, 306))
    assert result[1] == (GEOMETRIES[1], (346, 238, 20, 20))


def test_free_window_resize_or_root_with_children_keeps_the_difference() -> None:
    calls = Calls(set_by_game=False)
    resize = {0: ((134, 302, 434, 306), (134, 302, 450, 306))}
    assert wg.root_move_as_screen_move(resize, GEOMETRIES, set(), **calls.kwargs()) == {
        0: (GEOMETRIES[0], (134, 302, 450, 306))
    }
    assert calls.log == ["set_by_game"]  # mudar o tamanho não move a janela inteira
    calls = Calls()
    together = {
        0: ((916, 452, 1, 1), (941, 443, 1, 1)),
        1: ((140, 310, 20, 20), (165, 301, 20, 20)),
    }
    result = wg.root_move_as_screen_move(together, {**GEOMETRIES, 0: (916, 452, 1, 1)}, set(), **calls.kwargs())
    assert result == {0: ((916, 452, 1, 1), (941, 443, 1, 1)), 1: ((140, 310, 20, 20), (165, 301, 20, 20))}
    assert calls.log == []  # com outros elementos, a janela não é consultada


def test_root_from_panel() -> None:
    calls = Calls()
    kwargs = {key: value for key, value in calls.kwargs().items() if key in ("resize_root", "without_ghost_area")}
    root = (134, 302, 434, 306)
    # Caso medido no jogo: o painel mostra a moldura em (743, 387); +234, +52 na tela.
    assert wg.root_from_panel(root, (743 + 234, 387 + 52, 434, 306), (743, 387), **kwargs) == (-100, 250, 434, 306)
    assert calls.log == ["without_ghost (-100, 250, 434, 306)"]
    calls.log.clear()
    assert wg.root_from_panel(root, (743, 387, 434, 306), (743, 387), **kwargs) == root
    assert calls.log == []
    resized = wg.root_from_panel(root, (733, 387, 474, 326), (743, 387), **kwargs)
    assert resized == wg.resized_root((144, 302, 434, 306), 474, 326, centered)
    assert calls.log == ["resize (144, 302, 434, 306) 474x326"]


def test_service_does_not_import_qt() -> None:
    code = "import sys, gf_ui_editor.window_geometry; print(any(name.startswith('PySide6') for name in sys.modules))"
    env = {**os.environ, "PYTHONPATH": str(Path(wg.__file__).parents[1])}
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, check=True)
    assert result.stdout.strip() == "False"
