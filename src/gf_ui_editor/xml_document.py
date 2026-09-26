from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import difflib
import os
from pathlib import Path
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET


START_TAG_RE = re.compile(r"<BaseWndProperty\b[^>]*>")
NOR_UV_TAG_RE = re.compile(r"<NorUV\b[^>]*>")


class DocumentError(RuntimeError):
    """Erro legível ao abrir ou salvar um documento."""

    def __init__(self, message: str, *, code: str = "", details: dict[str, object] | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


class ExternalModificationError(DocumentError):
    """O arquivo mudou no disco depois de ser aberto."""


@dataclass(frozen=True)
class UVRect:
    left: int
    top: int
    width: int
    height: int


@dataclass
class UIElement:
    index: int
    window_id: str
    parent_id: str | None
    ctrl_type: str | None
    kind: str
    attrs: dict[str, str]
    original_attrs: dict[str, str]
    texture_name: str | None = None
    uv: UVRect | None = None
    original_uv: UVRect | None = None
    progress_offset: tuple[int, int] | None = None
    child_tags: tuple[str, ...] = field(default_factory=tuple)

    @staticmethod
    def _number(attrs: dict[str, str], name: str, default: int = 0) -> int:
        try:
            return int(attrs.get(name, default))
        except (TypeError, ValueError):
            return default

    @property
    def x(self) -> int:
        return self._number(self.attrs, "WindowLeft")

    @property
    def y(self) -> int:
        return self._number(self.attrs, "WindowTop")

    @property
    def width(self) -> int:
        # Neste formato, WindowHeight representa a extensão horizontal.
        return max(0, self._number(self.attrs, "WindowHeight"))

    @property
    def height(self) -> int:
        # Neste formato, WindowWidth representa a extensão vertical.
        return max(0, self._number(self.attrs, "WindowWidth"))

    @property
    def geometry(self) -> tuple[int, int, int, int]:
        return self.x, self.y, self.width, self.height

    @property
    def visible(self) -> bool:
        return self.attrs.get("Visible", "1") != "0"

    @property
    def window_text(self) -> str:
        return self.attrs.get("WindowText", "")

    @property
    def font_color(self) -> str:
        return self.attrs.get("FontColor", "")

    @property
    def font_style(self) -> str:
        return self.attrs.get("FontStyle", "")

    @property
    def changed_attributes(self) -> dict[str, str]:
        return {
            name: value
            for name, value in self.attrs.items()
            if self.original_attrs.get(name) != value
        }

    @property
    def changed_uv_attributes(self) -> dict[str, str]:
        if self.uv is None:
            return {}
        current = {
            "NorUVLeft": self.uv.left,
            "NorUVTop": self.uv.top,
            "NorUVWidth": max(0, self.uv.width),
            "NorUVHeight": max(0, self.uv.height),
        }
        if self.original_uv is None:
            return {name: str(value) for name, value in current.items()}
        original = {
            "NorUVLeft": self.original_uv.left,
            "NorUVTop": self.original_uv.top,
            "NorUVWidth": self.original_uv.width,
            "NorUVHeight": self.original_uv.height,
        }
        return {
            name: str(value)
            for name, value in current.items()
            if value != original[name]
        }

    def set_geometry(self, x: int, y: int, width: int, height: int) -> None:
        values = {
            "WindowLeft": x,
            "WindowTop": y,
            "WindowHeight": max(0, width),
            "WindowWidth": max(0, height),
        }
        for name, value in values.items():
            original = self.original_attrs.get(name)
            try:
                original_value = int(original) if original is not None else 0
            except ValueError:
                original_value = 0
            if value == original_value:
                if original is None:
                    self.attrs.pop(name, None)
                else:
                    self.attrs[name] = original
            else:
                self.attrs[name] = str(value)

    def set_uv(self, left: int, top: int, width: int, height: int) -> None:
        if self.uv is None:
            return
        self.uv = UVRect(left, top, max(0, width), max(0, height))


def _integer(attrs: dict[str, str], name: str, default: int = 0) -> int:
    try:
        return int(attrs.get(name, default))
    except (TypeError, ValueError):
        return default


def _kind_for(base: ET.Element, ctrl_type: str | None) -> str:
    # Somente os atributos diretos descrevem este controle. Descendentes dentro
    # de Container_Node pertencem a outros elementos da interface.
    tags = {child.tag for child in list(base)}
    if "MultiEditNode" in tags:
        return "multiline_text"
    if "SingleEditNode" in tags:
        return "text_field"
    if "ButtonNode" in tags:
        return "button"
    if "TextNode" in tags:
        return "text"
    if "SlotNode" in tags:
        return "slot"
    if "ProgressNode" in tags:
        return "progress"
    if "TrackNode" in tags:
        return "slider"
    if "PictureNode" in tags:
        return "image"
    if ctrl_type == "268435456":
        return "panel"
    return "control" if ctrl_type else "window"


class UIDocument:
    encoding = "big5"

    def __init__(self, path: Path, raw: bytes, text: str, root: ET.Element):
        self.path = path
        self.raw = raw
        self.text = text
        self.root = root
        self.elements: list[UIElement] = []
        self._start_tags = list(START_TAG_RE.finditer(text))
        self._uv_start_tags = list(NOR_UV_TAG_RE.finditer(text))
        self._build_elements()
        if len(self._start_tags) != len(self.elements):
            raise DocumentError(
                "Não foi possível relacionar todos os elementos ao texto original "
                f"({len(self.elements)} elementos, {len(self._start_tags)} tags).",
                code="element_count",
                details={"elements": len(self.elements), "tags": len(self._start_tags)},
            )
        uv_count = sum(element.uv is not None for element in self.elements)
        if len(self._uv_start_tags) != uv_count:
            raise DocumentError(
                "Não foi possível relacionar todos os recortes NorUV ao texto original "
                f"({uv_count} recortes, {len(self._uv_start_tags)} tags).",
                code="uv_count",
                details={"cuts": uv_count, "tags": len(self._uv_start_tags)},
            )

    @classmethod
    def load(cls, path: str | Path) -> "UIDocument":
        xml_path = Path(path).resolve()
        try:
            raw = xml_path.read_bytes()
        except OSError as exc:
            raise DocumentError(f"Não foi possível ler {xml_path}: {exc}", code="read", details={"path": xml_path, "error": exc}) from exc
        try:
            text = raw.decode(cls.encoding)
        except UnicodeDecodeError as exc:
            raise DocumentError(f"O arquivo não pôde ser decodificado como Big5: {exc}", code="decode", details={"error": exc}) from exc
        if text.encode(cls.encoding) != raw:
            raise DocumentError("A leitura Big5 não preserva exatamente os bytes do arquivo.", code="roundtrip")
        try:
            root = ET.fromstring(text)
        except ET.ParseError as exc:
            raise DocumentError(f"XML inválido: {exc}", code="invalid_xml", details={"error": exc}) from exc
        return cls(xml_path, raw, text, root)

    @property
    def is_dirty(self) -> bool:
        return any(
            element.changed_attributes or element.changed_uv_attributes
            for element in self.elements
        )

    def _build_elements(self) -> None:
        def walk(parent: ET.Element) -> None:
            last_style: ET.Element | None = None
            for child in list(parent):
                if child.tag == "Style":
                    last_style = child
                    continue
                if child.tag == "BaseWndProperty":
                    style_attrs = last_style.attrib if last_style is not None else {}
                    self.elements.append(self._make_element(child, style_attrs))
                    last_style = None
                walk(child)

        walk(self.root)

    def _make_element(self, base: ET.Element, style_attrs: dict[str, str]) -> UIElement:
        attrs = dict(base.attrib)
        background = base.find("BackGroundMap")
        texture_name = background.attrib.get("BGmap") if background is not None else None
        uv_node = background.find("NorUV") if background is not None else None
        uv = None
        if uv_node is not None:
            uv = UVRect(
                _integer(uv_node.attrib, "NorUVLeft"),
                _integer(uv_node.attrib, "NorUVTop"),
                _integer(uv_node.attrib, "NorUVWidth"),
                _integer(uv_node.attrib, "NorUVHeight"),
            )
        progress_offset = None
        progress_node = base.find("ProgressNode")
        offset_node = (
            progress_node.find("./OffSetUV/SOffset-0")
            if progress_node is not None
            else None
        )
        if offset_node is not None:
            progress_offset = (
                _integer(offset_node.attrib, "x"),
                _integer(offset_node.attrib, "y"),
            )
        ctrl_type = style_attrs.get("CtrlType")
        return UIElement(
            index=len(self.elements),
            window_id=attrs.get("WindowID", "?"),
            parent_id=style_attrs.get("ParentNode"),
            ctrl_type=ctrl_type,
            kind=_kind_for(base, ctrl_type),
            attrs=attrs,
            original_attrs=dict(attrs),
            texture_name=texture_name,
            uv=uv,
            original_uv=uv,
            progress_offset=progress_offset,
            child_tags=tuple(child.tag for child in base),
        )

    def set_geometry(self, index: int, geometry: tuple[int, int, int, int]) -> None:
        self.elements[index].set_geometry(*geometry)

    def set_uv(self, index: int, uv: UVRect) -> None:
        self.elements[index].set_uv(uv.left, uv.top, uv.width, uv.height)

    @staticmethod
    def _replace_attribute(tag: str, name: str, value: str) -> str:
        pattern = re.compile(rf'(\b{re.escape(name)}\s*=\s*")[^"]*(")')
        if pattern.search(tag):
            return pattern.sub(rf"\g<1>{value}\g<2>", tag, count=1)
        return tag[:-1] + f' {name}="{value}">'

    def render_text(self) -> str:
        replacements: list[tuple[int, int, str]] = []
        for element, match in zip(self.elements, self._start_tags, strict=True):
            tag = match.group(0)
            for name, value in element.changed_attributes.items():
                tag = self._replace_attribute(tag, name, value)
            replacements.append((match.start(), match.end(), tag))

        uv_elements = [element for element in self.elements if element.uv is not None]
        for element, match in zip(uv_elements, self._uv_start_tags, strict=True):
            tag = match.group(0)
            for name, value in element.changed_uv_attributes.items():
                tag = self._replace_attribute(tag, name, value)
            replacements.append((match.start(), match.end(), tag))

        chunks: list[str] = []
        cursor = 0
        for start, end, tag in sorted(replacements):
            chunks.append(self.text[cursor:start])
            chunks.append(tag)
            cursor = end
        chunks.append(self.text[cursor:])
        return "".join(chunks)

    def unified_diff(self) -> str:
        """Retorna apenas a prévia textual; não grava nem cria backup."""
        return "\n".join(
            difflib.unified_diff(
                self.text.splitlines(),
                self.render_text().splitlines(),
                fromfile=self.path.name,
                tofile=f"{self.path.name} (editado)",
                lineterm="",
            )
        )

    def _backup_path(self) -> Path:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        candidate = self.path.with_name(
            f"{self.path.stem}.before-gf-ui-editor-{stamp}{self.path.suffix}"
        )
        number = 2
        while candidate.exists():
            candidate = self.path.with_name(
                f"{self.path.stem}.before-gf-ui-editor-{stamp}-{number}{self.path.suffix}"
            )
            number += 1
        return candidate

    def save(self) -> Path:
        try:
            current_raw = self.path.read_bytes()
        except OSError as exc:
            raise DocumentError(f"Não foi possível reler o arquivo antes de salvar: {exc}", code="reread", details={"error": exc}) from exc
        if current_raw != self.raw:
            raise ExternalModificationError(
                "O XML foi alterado por outro programa desde que foi aberto. "
                "Reabra o arquivo para não sobrescrever mudanças externas.",
                code="external_change",
            )

        new_text = self.render_text()
        try:
            ET.fromstring(new_text)
            new_raw = new_text.encode(self.encoding)
        except (ET.ParseError, UnicodeEncodeError) as exc:
            raise DocumentError(f"A versão editada não passou pela validação: {exc}", code="validation", details={"error": exc}) from exc

        backup = self._backup_path()
        try:
            shutil.copyfile(self.path, backup)
            fd, temporary_name = tempfile.mkstemp(
                prefix=f".{self.path.stem}.", suffix=".gf-ui-editor.tmp", dir=self.path.parent
            )
            try:
                with os.fdopen(fd, "wb") as temporary:
                    temporary.write(new_raw)
                    temporary.flush()
                    os.fsync(temporary.fileno())
                os.replace(temporary_name, self.path)
            except Exception:
                try:
                    os.unlink(temporary_name)
                except OSError:
                    pass
                raise
        except OSError as exc:
            raise DocumentError(f"Falha ao criar backup ou gravar o XML: {exc}", code="write", details={"error": exc}) from exc

        self.raw = new_raw
        self.text = new_text
        self._start_tags = list(START_TAG_RE.finditer(new_text))
        self._uv_start_tags = list(NOR_UV_TAG_RE.finditer(new_text))
        for element in self.elements:
            element.original_attrs = dict(element.attrs)
            element.original_uv = element.uv
        return backup
