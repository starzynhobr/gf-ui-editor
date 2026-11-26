"""Describe a document using the same preview coordinates as the classic canvas."""

from __future__ import annotations

from dataclasses import astuple, dataclass
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


@dataclass
class PreviewContext:
    name: str
    resolution: tuple[int, int]
    game_dir: Path | None
    mode: str
    labels: dict[str, str]
    saved: window_geometry.Rect | None

    @classmethod
    def load(
        cls, path: Path, resolution: tuple[int, int] | None = None, *, saved_positions: bool = True,
    ) -> PreviewContext:
        game_dir, mode, overrides = _preview_context(path)
        if resolution is None:
            resolution = (game_layout.client_resolution(game_dir) if game_dir else None) or (1024, 768)
        if len(resolution) != 2 or any(type(value) is not int or value <= 0 for value in resolution):
            raise ValueError("Invalid canvas resolution")
        section = game_layout.saved_section_for(path.name)
        saved = game_layout.load_user_positions(game_dir / "User.ini").get(section) if saved_positions and game_dir and section else None
        return cls(path.name, resolution, game_dir, mode, game_texts.labels_for(path.name, game_dir, overrides), saved)

    def screen_for(self, rect: window_geometry.Rect) -> tuple[int, int]:
        return game_layout.root_screen_position(
            self.name, self.resolution, rect, self.saved, mode=self.mode, game_dir=self.game_dir,
        )

    @property
    def anchored(self) -> bool:
        return self.mode == "auto" and (
            game_layout.placement(self.name) in ("anchor", "placed") or game_layout.is_centered(self.name, self.game_dir)
        )

    def offsets(self, document: UIDocument) -> list[tuple[int, int]]:
        root_y = document.elements[0].y if document.elements else 0
        return [element_preview_offset(self.name, root_y, element, self.mode == "auto") for element in document.elements]


def describe_document(path: Path, resolution: tuple[int, int] | None = None, *, saved_positions: bool = True) -> dict:
    document = UIDocument.load(path)
    return describe_scene(document, PreviewContext.load(document.path, resolution, saved_positions=saved_positions))


def describe_scene(document: UIDocument, context: PreviewContext) -> dict:
    name = document.path.name
    resolution = context.resolution
    elements = [_element(element, name, context.labels) for element in document.elements]

    root, *children = document.elements or [None]
    root_rect = root.geometry if root else (0, 0, *resolution)
    root_x, root_y = root_rect[:2]
    bounds = window_geometry.nearby_bounds(root_rect, (element.geometry for element in children))
    screen_x, screen_y = context.screen_for(root_rect) if root else (0, 0)
    x, y = root_x - screen_x, root_y - screen_y
    offsets = context.offsets(document)
    content = window_geometry.content_bounds(
        (element.geometry, offset) for element, offset in zip(children, offsets[1:])
    ) if context.anchored else None
    drawn = GAME_DRAWN_AREAS.get(name.lower()) if root else None
    background = backgrounds.pick(resolution)
    return {
        "elements": elements,
        "bounds": bounds,
        "dirty": document.is_dirty,
        "ghost_area": window_geometry.ghost_area(root_rect, content, lambda: False) if content is not None else None,
        "frame_anchor_delta": (
            tuple((after - before) / 2 for after, before in zip(
                context.screen_for((root_x, root_y, root_rect[2] + 2, root_rect[3] + 2)),
                (screen_x, screen_y),
            )) if content is not None else None
        ),
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
