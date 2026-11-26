"""Editable atlas states and the XML edits produced by one Apply."""

from dataclasses import astuple
from math import ceil, floor

from .xml_document import UIDocument, UVRect

NORMAL = "NorUV"


def crop_between(
    first: tuple[float, float], second: tuple[float, float], size: tuple[int, int],
) -> UVRect:
    width, height = size
    left = max(0, min(floor(min(first[0], second[0])), width - 1))
    top = max(0, min(floor(min(first[1], second[1])), height - 1))
    right = max(left + 1, min(ceil(max(first[0], second[0])), width))
    bottom = max(top + 1, min(ceil(max(first[1], second[1])), height))
    return UVRect(left, top, right - left, bottom - top)


def resize_crop(crop: UVRect, handle: str, point: tuple[float, float], size: tuple[int, int]) -> UVRect:
    x, y = point
    return crop_between(
        (x if "left" in handle else crop.left, y if "top" in handle else crop.top),
        (x if "right" in handle else crop.left + crop.width, y if "bottom" in handle else crop.top + crop.height),
        size,
    )


def move_crop(crop: UVRect, delta: tuple[int, int], size: tuple[int, int]) -> UVRect:
    dx, dy = delta
    width, height = size
    return UVRect(
        max(0, min(crop.left + dx, width - crop.width)),
        max(0, min(crop.top + dy, height - crop.height)),
        crop.width, crop.height,
    )


def atlas_states(document: UIDocument, index: int) -> dict[str, UVRect]:
    element = document.elements[index]
    if element.uv is None:
        return {}
    states = {NORMAL: element.uv}
    if document.button_states_editable and ("ButtonNode" in element.child_tags or "ThumbUV" in element.button_uvs):
        states.update(element.button_uvs)
    return states


def atlas_edits(document: UIDocument, index: int, cuts: dict[str, UVRect], resize: bool) -> list[dict]:
    states = atlas_states(document, index)
    if not states or cuts.keys() - states.keys():
        raise ValueError("Recorte do atlas inválido para este elemento.")
    edits = [
        {"index": index, "field": "uv", "name": name, "before": astuple(states[name]), "after": astuple(cut)}
        for name, cut in cuts.items() if cut != states[name]
    ]
    if resize:
        element = document.elements[index]
        normal = cuts.get(NORMAL, states[NORMAL])
        # Geometry is in visual axes. UIDocument writes width to WindowHeight and height to WindowWidth.
        after = (element.x, element.y, normal.width, normal.height)
        if element.geometry != after:
            edits.append({"index": index, "field": "geometry", "before": element.geometry, "after": after})
    return edits
