"""Ponte: documento XML e canvas (dono: bloco 1, canvas)."""

from __future__ import annotations

from pathlib import Path

from ..backgrounds import BACKGROUNDS_DIRECTORY
from ..canvas_document import describe_document
from ..web_assets import WebAssets


class CanvasApi:
    """Métodos públicos viram window.pywebview.api.<nome>. Só tipos JSON."""

    def _attach_canvas_assets(self) -> None:
        self._canvas_assets = WebAssets(self._window, self._emit)
        self._window.events.closed += self._canvas_assets.close

    def asset_base(self, xml_path: str) -> str:
        return self._canvas_assets.base(Path(xml_path).parent, watch=True)

    def canvas_background_base(self) -> str:
        return self._canvas_assets.base(BACKGROUNDS_DIRECTORY)

    def open_document(self, path: str, resolution: list[int] | None = None, saved_positions: bool = True) -> dict:
        size = tuple(resolution) if resolution is not None else None
        return describe_document(Path(path), size, saved_positions=saved_positions)
