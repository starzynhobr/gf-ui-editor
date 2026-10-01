from __future__ import annotations

import os
from pathlib import Path
import struct

from PIL import Image
from PIL.ImageQt import ImageQt
from PySide6.QtGui import QPixmap

from .xml_document import UIElement


_HIGH_NIBBLE = [(value >> 4) * 17 for value in range(256)]
_LOW_NIBBLE = [(value & 15) * 17 for value in range(256)]


def open_dds_rgba(path: Path) -> Image.Image:
    """Abre uma textura como RGBA.

    As DDS sem compressão do jogo (32 bits BGRA/RGBA e 16 bits ARGB4444) são
    montadas com operações nativas do Pillow: o decodificador genérico dele
    para esses formatos roda em Python puro, byte a byte, e segurava o GIL a
    ponto de travar a interface enquanto as texturas carregavam.
    """
    with open(path, "rb") as handle:
        header = handle.read(128)
        if len(header) == 128 and header[:4] == b"DDS ":
            height, width = struct.unpack_from("<II", header, 12)
            flags, fourcc, bits, red, green, blue, alpha = struct.unpack_from("<I4sIIIII", header, 80)
            uncompressed = not flags & 0x4
            if uncompressed and bits == 32 and (red, green, blue) in ((0xFF0000, 0xFF00, 0xFF), (0xFF, 0xFF00, 0xFF0000)):
                data = handle.read(width * height * 4)
                rawmode = ("BGRA" if red == 0xFF0000 else "RGBA") if alpha else ("BGRX" if red == 0xFF0000 else "RGBX")
                return Image.frombuffer("RGBA", (width, height), data, "raw", rawmode, 0, 1).copy()
            if uncompressed and bits == 16 and (alpha, red, green, blue) == (0xF000, 0xF00, 0xF0, 0xF):
                data = handle.read(width * height * 2)
                low_byte = Image.frombuffer("L", (width, height), data[0::2], "raw", "L", 0, 1)
                high_byte = Image.frombuffer("L", (width, height), data[1::2], "raw", "L", 0, 1)
                return Image.merge(
                    "RGBA",
                    (
                        high_byte.point(_LOW_NIBBLE),
                        low_byte.point(_HIGH_NIBBLE),
                        low_byte.point(_LOW_NIBBLE),
                        high_byte.point(_HIGH_NIBBLE),
                    ),
                )
    with Image.open(path) as source:
        return source.convert("RGBA")


class TextureCache:
    def __init__(self, ui_directory: Path):
        self.ui_directory = ui_directory.resolve()
        # Chaves por caminho em texto: Path.resolve() custa milissegundos por
        # chamada no Windows e era chamado centenas de vezes por arquivo aberto.
        self._images: dict[str, tuple[int, int, Image.Image]] = {}
        self._index: dict[str, Path] | None = None
        self.missing: set[str] = set()

    def _source_image(self, texture_path: Path) -> Image.Image:
        key = os.path.normcase(str(texture_path))
        stat = os.stat(texture_path)
        signature = (stat.st_mtime_ns, stat.st_size)
        cached = self._images.get(key)
        if cached is not None and cached[:2] == signature:
            return cached[2]
        source = open_dds_rgba(texture_path)
        self._images[key] = (*signature, source)
        return source

    def _name_index(self) -> dict[str, Path]:
        if self._index is None:
            index: dict[str, Path] = {}
            with os.scandir(self.ui_directory) as entries:
                for entry in entries:
                    if entry.is_file():
                        index[entry.name.lower()] = Path(entry.path)
            self._index = index
        return self._index

    def path_for(self, texture_name: str) -> Path | None:
        """Busca sem diferenciar maiúsculas, como o jogo; relista a pasta uma vez se faltar."""
        lowered = texture_name.lower()
        path = self._name_index().get(lowered)
        if path is None or not path.exists():
            self._index = None
            path = self._name_index().get(lowered)
        return path

    def invalidate(self, texture_path: Path | None = None) -> None:
        if texture_path is None:
            self._images.clear()
            self._index = None
            return
        self._images.pop(os.path.normcase(str(texture_path)), None)

    def prepare_source(self, texture_name: str) -> tuple[Path, tuple[int, int, Image.Image]] | None:
        """Decodifica uma DDS sem criar objetos Qt; pode rodar em outra thread."""
        texture_path = self.path_for(texture_name)
        if texture_path is None:
            return None
        stat = os.stat(texture_path)
        image = open_dds_rgba(texture_path)
        return texture_path, (stat.st_mtime_ns, stat.st_size, image)

    def install_source(self, source: tuple[Path, tuple[int, int, Image.Image]]) -> None:
        path, cached = source
        self._images[os.path.normcase(str(path))] = cached

    def has_source(self, texture_name: str) -> bool:
        path = self.path_for(texture_name)
        if path is None:
            return False
        cached = self._images.get(os.path.normcase(str(path)))
        if cached is None:
            return False
        stat = os.stat(path)
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
