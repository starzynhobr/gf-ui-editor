"""Texto que o canvas mostra em cada controle: sem Qt."""
import os
from pathlib import Path
import subprocess
import sys

from gf_ui_editor import text_preview
from gf_ui_editor.text_preview import LONG, SHORT
from gf_ui_editor.xml_document import UIElement

TEXT_PROPS = {"FontColor": "16777215", "TextAlign": "0"}


def _element(
    window_id: str = "10", text: str = "", tags: tuple[str, ...] = ("TextNode",), width: int = 80,
    props: dict[str, str] | None = None, **extra: str,
) -> UIElement:
    attrs = {"WindowText": text, "WindowHeight": str(width), "WindowWidth": "20", **extra}  # o jogo troca largura/altura
    return UIElement(
        0, window_id, None, None, "text", attrs, dict(attrs),
        child_tags=tags, text_props=TEXT_PROPS if props is None else props,
    )


def test_player_sample_comes_before_every_mode() -> None:
    element = _element(text="XML")
    for mode in ("off", "game", "xml", "short", "long"):
        assert text_preview.element_text(element, mode, {}, sample="StarzynhoBR3") == "StarzynhoBR3"
    assert text_preview.element_text(element, "xml", {}, sample="") == "XML"  # amostra vazia não conta


def test_off_and_xml_modes() -> None:
    assert text_preview.element_text(_element(text="Olá"), "off", {}) == ""
    assert text_preview.element_text(_element(text="Olá"), "xml", {}) == "Olá"
    assert text_preview.element_text(_element(text=""), "xml", {}) == ""
    assert text_preview.element_text(_element(text="Olá", tags=()), "xml", {}) == "Olá"


def test_game_mode_uses_the_label_and_window_text_only_for_text_controls() -> None:
    labels = {"10": "Rótulo"}
    assert text_preview.element_text(_element(text="Olá"), "game", labels) == "Rótulo"
    assert text_preview.element_text(_element("11", text="Olá"), "game", labels) == "Olá"
    assert text_preview.element_text(_element("11", text="Olá", tags=("ButtonNode",)), "game", labels) == "Olá"
    assert text_preview.element_text(_element("11", text="PX1-1", tags=()), "game", labels) == ""  # nome interno


def test_labels_function_is_called_only_in_game_mode() -> None:
    calls: list[int] = []

    def labels() -> dict[str, str]:
        calls.append(1)
        return {"10": "Rótulo"}

    assert text_preview.element_text(_element(), "short", labels) is SHORT
    assert text_preview.element_text(_element(), "xml", labels) == ""
    assert calls == []
    assert text_preview.element_text(_element(), "game", labels) == "Rótulo" and calls == [1]


def test_samples_only_for_empty_text_controls_with_room() -> None:
    assert text_preview.element_text(_element(), "short", {}) is SHORT
    assert text_preview.element_text(_element(), "long", {}) is LONG
    assert text_preview.element_text(_element(tags=("ButtonNode",)), "long", {}) is LONG
    assert text_preview.element_text(_element(text="Olá"), "short", {}) == "Olá"
    assert text_preview.element_text(_element(tags=()), "short", {}) == ""
    assert text_preview.element_text(_element(props={}), "short", {}) == ""
    assert text_preview.element_text(_element(width=3), "short", {}) == ""
    assert text_preview.element_text(_element(width=4), "short", {}) is SHORT


def test_layer_text() -> None:
    labels = {"10": "Rótulo"}
    assert text_preview.layer_text(_element(text="Olá"), labels) == "Rótulo"
    assert text_preview.layer_text(_element("11", text="Olá"), labels) == "Olá"
    assert text_preview.layer_text(_element("11", text="PX1-1", tags=()), labels) == ""
    assert text_preview.layer_text(_element(text="Olá"), labels, sample="100") == "100"
    assert text_preview.layer_text(_element(text="Olá"), labels, sample=None) == "Rótulo"


def test_search_text_joins_every_field_in_casefold() -> None:
    element = _element("5010", text="Nome", tags=())
    element.parent_id, element.ctrl_type, element.texture_name = "5000", "TextCtrl", "Main.DDS"
    assert text_preview.search_text(element, "Texto", "StraßE") == "5010 texto 5000 nome main.dds textctrl strasse"
    bare = _element("1", tags=())
    assert text_preview.search_text(bare, "Painel", "") == "1 painel" + " " * 5  # 7 campos, 5 vazios


def test_service_does_not_import_qt() -> None:
    code = "import sys, gf_ui_editor.text_preview; print(any(name.startswith('PySide6') for name in sys.modules))"
    env = {**os.environ, "PYTHONPATH": str(Path(text_preview.__file__).parents[1])}
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, check=True)
    assert result.stdout.strip() == "False"
