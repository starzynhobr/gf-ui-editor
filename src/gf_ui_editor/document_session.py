"""Editable XML session shared by web document and canvas operations."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from threading import RLock

from . import atlas, game_layout, window_geometry
from .canvas_document import PreviewContext, describe_scene, project_ui_root
from .project import Project
from .xml_document import UIDocument, UVRect


def _rect(value, *, dimensions: bool = True) -> window_geometry.Rect:
    if (
        not isinstance(value, (list, tuple)) or len(value) != 4
        or any(type(number) is not int for number in value)
        or (dimensions and min(value[2:]) < 0)
    ):
        raise ValueError("Geometria inválida.")
    return tuple(value)


def _index(document: UIDocument, value) -> int:
    if type(value) is not int or not 0 <= value < len(document.elements):
        raise ValueError("Elemento inválido.")
    return value


def save_document(document: UIDocument, project: Project | None) -> None:
    """Save with the same original, backup, and change-cache handling as Qt."""
    if not document.is_dirty:
        return
    in_project = project is not None and project.contains(document.path)
    if in_project:
        try:
            project.remember_original(document.path)
        except OSError:
            pass
    document.save(project.history_path_for(document.path) if in_project else None)
    if project is not None:
        project.invalidate_changes()
    if in_project:
        project.prune_history(document.path)


def _apply_edits(document: UIDocument, edits: list[dict]) -> None:
    """Validate against the current values and roll back the entire batch on failure."""
    originals = {}
    try:
        for edit in edits:
            index = _index(document, edit["index"])
            if index not in originals:
                originals[index] = document.elements[index]
                document.elements[index] = deepcopy(originals[index])
            element = document.elements[index]
            field, before, after = edit["field"], edit["before"], edit["after"]
            if field == "geometry":
                current = element.geometry
                before, after = _rect(before, dimensions=False), _rect(after)
                update = document.set_geometry
                args = (after,)
            elif field == "uv" and element.uv is not None:
                name = edit.get("name", atlas.NORMAL)
                current = atlas.atlas_states(document, index).get(name)
                before, after = UVRect(*_rect(before, dimensions=False)), UVRect(*_rect(after))
                if name == atlas.NORMAL:
                    update, args = document.set_uv, (after,)
                else:
                    update, args = document.set_button_uv, (name, after)
            elif field == "texture" and (after is None or isinstance(after, str)):
                current = element.texture_name
                update = document.set_texture
                args = (after,)
            elif field == "font" and isinstance(after, str):
                name = edit["name"]
                current = element.text_props.get(name)
                update = document.set_font
                args = (name, after)
            else:
                raise ValueError("Campo inválido para este elemento.")
            if before != current:
                raise ValueError("O elemento mudou desde o início da edição.")
            if before != after:
                update(index, *args)
    except Exception:
        for index, element in originals.items():
            document.elements[index] = element
        raise


def canvas_geometry_edits(
    document: UIDocument,
    context: PreviewContext,
    edits: list[dict],
    locked: set[int],
    *,
    preview: bool,
    root_background: bool,
) -> tuple[list[dict], bool]:
    """Turn scene-space canvas changes into reversible XML edits."""
    geometries = {element.index: element.geometry for element in document.elements}
    changes: dict[int, window_geometry.Change] = {}
    for edit in edits:
        index = _index(document, edit["index"])
        if index in locked:
            continue
        before = _rect(edit["before"], dimensions=False)
        if before != geometries[index]:
            raise ValueError("O elemento mudou desde o início da edição.")
        after = _rect(edit["after"])
        if after != before:
            changes[index] = (before, after)

    show_saved = True
    if 0 in changes:
        offsets = context.offsets(document)
        bounds = window_geometry.content_bounds(
            (geometry, offsets[index]) for index, geometry in geometries.items() if index
        ) if preview and context.anchored else None

        def without_ghost_area(rect):
            if bounds is not None and window_geometry.ghost_area(rect, bounds, lambda: root_background):
                return window_geometry.collapsed_root(rect, context.screen_for)
            return rect

        def preview_default_position():
            nonlocal show_saved
            root = geometries[0]
            if (
                preview and game_layout.rule_for(context.name) is None
                and game_layout.saved_position_applies(context.resolution, root, context.saved)
            ):
                show_saved = False
                return context.screen_for(root)
            return None

        changes = window_geometry.root_move_as_screen_move(
            changes, geometries, locked,
            set_by_game=lambda: context.anchored,
            resize_root=lambda rect, w, h: window_geometry.resized_root(rect, w, h, context.screen_for),
            frame_on_screen=lambda: context.screen_for(geometries[0]) if bounds is not None else None,
            without_ghost_area=without_ghost_area,
            preview_default_position=preview_default_position,
        )
    return [
        {"index": index, "field": "geometry", "before": before, "after": after}
        for index, (before, after) in changes.items() if before != after
    ], show_saved


class DocumentSession:
    def __init__(self) -> None:
        self._lock = RLock()
        self._document: UIDocument | None = None
        self._context: PreviewContext | None = None
        self._resolution: tuple[int, int] | None = None
        self._saved_positions = True

    def _require(self) -> tuple[UIDocument, PreviewContext]:
        if self._document is None or self._context is None:
            raise ValueError("Nenhum XML aberto.")
        return self._document, self._context

    def open(
        self, path: str | Path | None, resolution: tuple[int, int] | None = None, *, saved_positions: bool = True,
    ) -> dict | None:
        with self._lock:
            if path is None:
                self._document = self._context = self._resolution = None
                return None
            document = UIDocument.load(Path(path))
            context = PreviewContext.load(document.path, resolution, saved_positions=saved_positions)
            scene = describe_scene(document, context)
            self._document, self._context, self._resolution = document, context, resolution
            self._saved_positions = saved_positions
            return scene

    def configure_preview(
        self, path: str, resolution: tuple[int, int] | None, saved_positions: bool, *, keep_position_override: bool = False,
    ) -> dict | None:
        with self._lock:
            if self._document is None or self._document.path != Path(path).resolve():
                return None
            document, previous = self._require()
            effective = saved_positions and (previous.saved_positions if keep_position_override else True)
            context = PreviewContext.load(document.path, resolution, saved_positions=effective)
            scene = describe_scene(document, context)
            self._context, self._resolution, self._saved_positions = context, resolution, saved_positions
            return scene

    def edit(self, edits: list[dict]) -> dict:
        with self._lock:
            document, context = self._require()
            _apply_edits(document, edits)
            return describe_scene(document, context)

    def edit_canvas(self, edits: list[dict], locked: list[int], preview: bool, root_background: bool) -> dict:
        with self._lock:
            document, context = self._require()
            edits, show_saved = canvas_geometry_edits(
                document, context, edits, set(locked), preview=preview, root_background=root_background,
            )
            _apply_edits(document, edits)
            if not show_saved:
                context.saved = None
                context.saved_positions = False
            return {"doc": describe_scene(document, context), "edits": edits}

    def diff(self) -> str:
        with self._lock:
            document, _ = self._require()
            return document.unified_diff()

    def plan_atlas(self, path: str, index: int, before: dict, after: dict, resize: bool) -> list[dict]:
        with self._lock:
            document, _ = self._require()
            index = _index(document, index)
            current = atlas.atlas_states(document, index)
            if (
                document.path != Path(path).resolve()
                or {name: UVRect(*_rect(rect, dimensions=False)) for name, rect in before.items()} != current
            ):
                raise ValueError("O elemento mudou desde o início da edição.")
            return atlas.atlas_edits(
                document, index, {name: UVRect(*_rect(rect)) for name, rect in after.items()}, resize,
            )

    def refresh_texts(self, project: str) -> dict | None:
        with self._lock:
            if self._document is None:
                return None
            document, context = self._require()
            ui = project_ui_root(document.path)
            if ui is None or ui.parent.resolve() != Path(project).resolve():
                return None
            context.refresh_labels(document.path)
            return describe_scene(document, context)

    def save(self, project: Project | None) -> dict:
        with self._lock:
            document, context = self._require()
            save_document(document, project)
            return describe_scene(document, context)

    def revert(self) -> dict:
        with self._lock:
            document, _ = self._require()
            scene = self.open(document.path, self._resolution, saved_positions=self._saved_positions)
            assert scene is not None
            return scene

    def external_change(self) -> str | None:
        with self._lock:
            if self._document is None:
                return None
            document = self._document
            try:
                current = document.path.read_bytes()
            except FileNotFoundError:
                return "missing"
            except OSError:
                return None
            return sha256(current).hexdigest() if current != document.raw else None
