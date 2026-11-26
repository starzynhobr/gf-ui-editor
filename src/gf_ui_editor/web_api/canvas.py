"""Ponte: documento XML e canvas (dono: bloco 1, canvas)."""

from __future__ import annotations

from pathlib import Path

from ..about import GAME_RESOLUTIONS, parse_resolution
from ..backgrounds import BACKGROUNDS_DIRECTORY
from ..canvas_document import TEXT_MODES, PreviewContext, describe_document, describe_scene
from ..game_layout import DEFAULT_HUD
from ..game_text_raster import prepare_web_rasterizer, web_text_mask
from ..text_preview import layer_text
from ..web_assets import WebAssets
from ..xml_document import DocumentError


BACKGROUND_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp"}


class CanvasApi:
    """Métodos públicos viram window.pywebview.api.<nome>. Só tipos JSON."""

    def _attach_canvas_assets(self) -> None:
        if getattr(self, "_canvas_assets", None) is not None:
            return
        prepare_web_rasterizer()
        self._canvas_assets = WebAssets(self._window, self._emit)
        self._window.events.closed += self._canvas_assets.close

    def canvas_text_masks(self, requests: list[list]) -> list[tuple[int, int, str]]:
        """Rasterize the batch in input order so the browser can reuse each mask by style and size."""
        return [web_text_mask(*request) for request in requests]

    def asset_base(self, xml_path: str) -> str:
        path = Path(xml_path)
        project = getattr(self, "_project", None)
        if project is not None and project.contains(path):
            return self._canvas_assets.base(path.parent, watch=True, project=project)
        return self._canvas_assets.base(path.parent, watch=True)

    def canvas_background_base(self) -> str:
        return self._canvas_assets.base(BACKGROUNDS_DIRECTORY)

    def canvas_preferences(self) -> dict:
        prefs = self._prefs
        background = prefs.game_background
        resolution = prefs.game_resolution
        mode = prefs.get("background_mode", "custom" if background else "builtin")
        return {
            "resolution": resolution if resolution == "off" or parse_resolution(resolution) else "game",
            "presets": GAME_RESOLUTIONS,
            "background": mode if mode in ("none", "builtin", "custom") else "builtin",
            "backgroundPath": background,
            "savedPositions": prefs.canvas_saved_positions,
            "character": prefs.canvas_character,
            "outlines": prefs.canvas_outlines,
            "ids": prefs.canvas_ids,
            "text": prefs.text_mode if prefs.text_mode in TEXT_MODES else "off",
        }

    def canvas_set_preference(
        self, path: str, key: str, value: str | bool, game_size: list[int] | None = None,
    ) -> dict:
        prefs = self._prefs
        doc = None
        if key == "resolution":
            size = parse_resolution(value) if isinstance(value, str) else None
            if size is None and value not in ("game", "off"):
                raise ValueError("Use o formato largura x altura, por exemplo 1366x768.")
            doc = self._document_session.configure_preview(
                path, size or (tuple(game_size) if game_size else None), prefs.canvas_saved_positions,
                keep_position_override=True,
            )
            prefs.game_resolution = f"{size[0]}x{size[1]}" if size else value
        elif key == "savedPositions" and type(value) is bool:
            size = parse_resolution(prefs.game_resolution) or (tuple(game_size) if game_size else None)
            doc = self._document_session.configure_preview(path, size, value)
            prefs.canvas_saved_positions = value
        elif key == "character" and type(value) is bool:
            prefs.canvas_character = value
        elif key == "outlines" and type(value) is bool:
            prefs.canvas_outlines = value
            if not value:
                prefs.canvas_ids = False
        elif key == "ids" and type(value) is bool:
            prefs.canvas_ids = value
        elif key == "text" and value in TEXT_MODES:
            prefs.text_mode = value
        elif key == "background" and value in ("builtin", "custom", "none"):
            prefs.background_mode = value
        else:
            raise ValueError("Preferência do canvas inválida.")
        return {"preferences": self.canvas_preferences(), "doc": doc}

    def canvas_choose_background(self) -> dict:
        previous = self._prefs.game_background
        game = self._game_dir()
        start = Path(previous).parent if previous else game / "ScreenCapture" if game else None
        chosen = self._ask_path("open", start, ("Imagens (*.png;*.jpg;*.jpeg;*.bmp)",))
        if chosen is not None:
            if chosen.suffix.lower() not in BACKGROUND_EXTENSIONS or not chosen.is_file():
                raise ValueError("Escolha uma imagem PNG, JPG ou BMP.")
            self._prefs.game_background = str(chosen)
            self._prefs.background_mode = "custom"
        return self.canvas_preferences()

    def canvas_custom_background(self) -> dict | None:
        path = Path(self._prefs.game_background)
        if path.suffix.lower() not in BACKGROUND_EXTENSIONS or not path.is_file():
            return None
        return {"base": self._canvas_assets.base(path.parent), "name": path.name}

    def canvas_layers(self, path: str, resolution: list[int] | None = None, saved_positions: bool = True) -> dict:
        project = self._project
        if project is None or not project.contains(Path(path)):
            return {"names": [], "scenes": [], "inProject": False}
        scenes = []
        if resolution is not None:
            current = Path(path).resolve()
            for name in project.reference_layers:
                source = (project.ui_dir / name).resolve()
                if source == current or not project.contains(source) or source.suffix.lower() != ".xml":
                    continue
                try:
                    document = project.load_document(source)
                    context = PreviewContext.load(source, tuple(resolution), saved_positions=saved_positions)
                except (DocumentError, OSError, ValueError):
                    continue
                scene = describe_scene(document, context)
                for item, element in zip(scene["elements"], document.elements, strict=True):
                    item["layer_text"] = layer_text(element, {})
                scenes.append({"name": name, "base": self.asset_base(str(source)), "scene": scene})
        return {"names": project.reference_layers, "scenes": scenes, "inProject": True}

    def canvas_change_layers(self, path: str, action: str, name: str | None = None) -> None:
        """Update the project layers shared by the canvas toolbar and file list."""
        project = self._project
        if project is None or not project.contains(Path(path)):
            raise ValueError("Nenhum projeto aberto.")
        if action == "default":
            available = {file.as_posix().lower(): file.as_posix() for file in project.files()}
            known = {name.lower() for name in project.reference_layers}
            layers = [
                *project.reference_layers,
                *(available[name.lower()] for name in DEFAULT_HUD if name.lower() in available and name.lower() not in known),
            ]
        elif action == "clear":
            layers = []
        elif action in ("add", "remove") and name:
            candidate = (project.ui_dir / name).resolve()
            if not project.contains(candidate) or candidate.suffix.lower() != ".xml" or not project.read_path(candidate).is_file():
                raise ValueError("Camada inválida.")
            relative = project.relative_key(candidate)
            layers = [layer for layer in project.reference_layers if layer.lower() != relative.lower()]
            if action == "add":
                layers.append(relative)
        else:
            raise ValueError("Ação de camadas inválida.")
        previous = project.reference_layers
        project.reference_layers = layers
        try:
            project.save_manifest()
        except Exception:
            project.reference_layers = previous
            raise

    def open_document(self, path: str, resolution: list[int] | None = None, saved_positions: bool = True) -> dict:
        size = tuple(resolution) if resolution is not None else None
        project = getattr(self, "_project", None)
        target = Path(path)
        return describe_document(
            target, size, saved_positions=saved_positions,
            source=project.read_path(target) if project is not None else None,
        )
