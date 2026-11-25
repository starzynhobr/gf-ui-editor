"""Prepare a read-only scene using the same coordinates as the classic canvas."""

from __future__ import annotations

from dataclasses import astuple
from pathlib import Path

from . import backgrounds, game_layout, game_texts, player_sample, storage, text_preview, window_geometry
from .xml_document import UIDocument, UIElement, UVRect

TEXT_MODES = ("off", "game", "xml", "short", "long")
GAME_DRAWN_AREAS = {"basicchar.xml": (23, 7, 76, 76)}


def element_preview_offset(name: str, root_y: int, element: UIElement, enabled: bool) -> tuple[int, int]:
    target = game_layout.menu_shortcut_preview_y(name, element.window_id, root_y)
    return (0, target - element.y) if enabled and target is not None and element.kind == "slot" else (0, 0)


def _preview_context(path: Path) -> tuple[Path | None, str, dict[int, str]]:
    for parent in path.parents:
        if parent.name.lower() == "ui" and (parent.parent / storage.PROJECT_DB).is_file():
            return storage.peek_preview_context(parent.parent, path.relative_to(parent).as_posix())
    beside = path.parent.parent
    return (beside if game_layout.looks_like_game_dir(beside) else None), "auto", {}


def _uv(rect: UVRect | None) -> tuple[int, int, int, int] | None:
    return astuple(rect) if rect is not None else None


def _element(element: UIElement, name: str, labels: dict[str, str]) -> dict:
    sample = player_sample.sample_text(name, element.window_id)
    texts = {}
    for mode in TEXT_MODES:
        value = text_preview.element_text(element, mode, labels)
        # Keep sample tokens separate from literal XML text so the UI can translate them.
        texts[mode] = {"value": value} if isinstance(value, str) else {"sample": value.value}
    return {
        "index": element.index,
        "id": element.window_id,
        "parent": element.parent_id,
        "kind": element.kind,
        "ctrl_type": element.ctrl_type,
        "geometry": element.geometry,
        "texture": element.texture_name,
        "uv": _uv(element.uv),
        "button_uvs": {state: _uv(rect) for state, rect in element.button_uvs.items()},
        "progress_offset": element.progress_offset,
        "visible": element.visible,
        "text_props": element.text_props,
        "button": "ButtonNode" in element.child_tags,
        "texts": texts,
        "sample_text": sample,
        "sample_icon": player_sample.sample_icon(name, element.window_id),
    }


def describe_document(path: Path, resolution: tuple[int, int] | None = None, *, saved_positions: bool = True) -> dict:
    document = UIDocument.load(path)
    name = document.path.name
    game_dir, mode, overrides = _preview_context(document.path)
    labels = game_texts.labels_for(name, game_dir, overrides)
    elements = [_element(element, name, labels) for element in document.elements]
    if resolution is None:
        resolution = (game_layout.client_resolution(game_dir) if game_dir else None) or (1024, 768)
    if len(resolution) != 2 or any(type(value) is not int or value <= 0 for value in resolution):
        raise ValueError("Invalid canvas resolution")

    root, *children = document.elements or [None]
    root_rect = root.geometry if root else (0, 0, *resolution)
    root_x, root_y = root_rect[:2]
    bounds = window_geometry.nearby_bounds(root_rect, (element.geometry for element in children))
    section = game_layout.saved_section_for(name)
    saved = game_layout.load_user_positions(game_dir / "User.ini").get(section) if saved_positions and game_dir and section else None
    screen_x, screen_y = game_layout.root_screen_position(
        name, resolution, root_rect, saved, mode=mode, game_dir=game_dir,
    ) if root else (0, 0)
    x, y = root_x - screen_x, root_y - screen_y
    offsets = [element_preview_offset(name, root_y, element, mode == "auto") for element in document.elements]
    anchored = mode == "auto" and (
        game_layout.placement(name) in ("anchor", "placed") or game_layout.is_centered(name, game_dir)
    )
    content = window_geometry.content_bounds(
        (element.geometry, offset) for element, offset in zip(children, offsets[1:])
    ) if anchored else None
    drawn = GAME_DRAWN_AREAS.get(name.lower()) if root else None
    background = backgrounds.pick(resolution)
    return {
        "elements": elements,
        "bounds": bounds,
        "preview": {
            "screen": (x, y, *resolution),
            "root_on_screen": (screen_x, screen_y),
            "offsets": offsets,
            "frame": root_rect if content is not None else None,
            "content": content,
            "drawn": (x + drawn[0], y + drawn[1], drawn[2], drawn[3]) if drawn else None,
            "background": background.name if background else None,
        },
    }
