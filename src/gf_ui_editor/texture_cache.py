from __future__ import annotations

from pathlib import Path

from PIL import Image
from PIL.ImageQt import ImageQt
from PySide6.QtGui import QPixmap

from .xml_document import UIElement


class TextureCache:
    def __init__(self, ui_directory: Path):
        self.ui_directory = ui_directory.resolve()
        self._images: dict[Path, tuple[int, int, Image.Image]] = {}
        self.missing: set[str] = set()

    def _source_image(self, texture_path: Path) -> Image.Image:
        resolved = texture_path.resolve()
        stat = resolved.stat()
        signature = (stat.st_mtime_ns, stat.st_size)
        cached = self._images.get(resolved)
        if cached is not None and cached[:2] == signature:
            return cached[2]
        source = Image.open(resolved).convert("RGBA")
        self._images[resolved] = (*signature, source)
        return source

    def path_for(self, texture_name: str) -> Path | None:
        direct = self.ui_directory / texture_name
        if direct.exists():
            return direct
        lowered = texture_name.lower()
        for candidate in self.ui_directory.iterdir():
            if candidate.is_file() and candidate.name.lower() == lowered:
                return candidate
        return None

    def invalidate(self, texture_path: Path | None = None) -> None:
        if texture_path is None:
            self._images.clear()
            return
        self._images.pop(texture_path.resolve(), None)

    def prepare_source(self, texture_name: str) -> tuple[Path, tuple[int, int, Image.Image]] | None:
        """Decodifica uma DDS sem criar objetos Qt; pode rodar em outra thread."""
        texture_path = self.path_for(texture_name)
        if texture_path is None:
            return None
        resolved = texture_path.resolve()
        stat = resolved.stat()
        with Image.open(resolved) as source:
            image = source.convert("RGBA")
        return resolved, (stat.st_mtime_ns, stat.st_size, image)

    def install_source(self, source: tuple[Path, tuple[int, int, Image.Image]]) -> None:
        path, cached = source
        self._images[path] = cached

    def has_source(self, texture_name: str) -> bool:
        path = self.path_for(texture_name)
        if path is None:
            return False
        cached = self._images.get(path.resolve())
        if cached is None:
            return False
        stat = path.stat()
        return cached[:2] == (stat.st_mtime_ns, stat.st_size)

    def source_pixmap(self, texture_name: str) -> QPixmap | None:
        texture_path = self.path_for(texture_name)
        if texture_path is None:
            self.missing.add(texture_name)
            return None
        try:
            source = self._source_image(texture_path)
            return QPixmap.fromImage(ImageQt(source))
        except Exception:
            self.missing.add(texture_name)
            return None

    def pixmap_for(self, element: UIElement) -> QPixmap | None:
        if not element.texture_name or not element.uv:
            return None
        if element.uv.width <= 0 or element.uv.height <= 0:
            return None
        texture_path = self.path_for(element.texture_name)
        if texture_path is None:
            self.missing.add(element.texture_name)
            return None
        try:
            source = self._source_image(texture_path)
            uv = element.uv
            cropped = source.crop((uv.left, uv.top, uv.left + uv.width, uv.top + uv.height))
            if element.progress_offset is not None:
                offset_x, offset_y = element.progress_offset
                filled = source.crop(
                    (
                        uv.left + offset_x,
                        uv.top + offset_y,
                        uv.left + offset_x + uv.width,
                        uv.top + offset_y + uv.height,
                    )
                )
                # O jogo desenha a faixa deslocada sobre a textura-base. Como o
                # XML não contém o valor atual, o editor representa 100% cheio.
                cropped = Image.alpha_composite(cropped, filled)
            if cropped.size != (element.width, element.height) and element.width and element.height:
                cropped = cropped.resize((element.width, element.height), Image.Resampling.NEAREST)
            return QPixmap.fromImage(ImageQt(cropped))
        except Exception:
            self.missing.add(element.texture_name)
            return None
