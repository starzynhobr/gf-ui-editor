"""Standalone XML texture resolution, comparison, and project import."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from threading import RLock
import xml.etree.ElementTree as ET

from . import gamedata, game_updates
from .project import Project, _install_new_file
from .textures import find_texture, ui_texture_names
from .xml_document import UIDocument, unified_xml_diff


def texture_relative(name: str) -> Path | None:
    path = Path(name.replace("\\", "/"))
    if path.anchor or ".." in path.parts or path.suffix.lower() not in (".dds", ".tga"):
        return None
    return path


@dataclass(frozen=True, eq=False)
class StandaloneTextures:
    directory: Path
    project: Project | None
    game: Path | None

    def project_texture(self, relative: Path) -> Path | None:
        if self.project is None:
            return None
        path = find_texture(self.project.ui_dir, relative.as_posix(), self.project)
        if path is not None and path.resolve().is_relative_to(self.project.ui_dir.resolve()):
            source = self.project.read_path(path)
            return source if source.is_file() else None
        return None

    def base_texture(self, relative: Path) -> Path | None:
        if self.game is None:
            return None
        entry = gamedata.official_ui_files(self.game).get(relative.as_posix().lower())
        if entry is None:
            return None
        crc = entry[1]
        if self.project is not None:
            for extension in ("xml", "bin"):
                path = self.project.base_path(f"{crc}.{extension}")
                if path.is_file():
                    return path
        return game_updates.cached_version(crc)

    def local_texture(self, relative: Path) -> Path | None:
        path = find_texture(self.directory, relative.as_posix())
        return path if path is not None and path.resolve().is_relative_to(self.directory.resolve()) else None

    def resolve(self, name: str) -> Path | None:
        relative = texture_relative(name)
        if relative is None:
            return None
        return self.local_texture(relative) or self.project_texture(relative) or self.fallback_texture(relative)

    def fallback_texture(self, relative: Path) -> Path | None:
        path = self.base_texture(relative)
        if path is None and self.game is not None:
            ui = self.game / "UI"
            candidate = find_texture(ui, relative.as_posix())
            if candidate is not None and candidate.resolve().is_relative_to(ui.resolve()):
                path = candidate
        return path

    def names(self) -> list[str]:
        names: dict[str, str] = {}
        if self.game is not None:
            if (self.game / "UI").is_dir():
                names.update({name.lower(): name for name in ui_texture_names(self.game / "UI")})
            for key in gamedata.official_ui_files(self.game):
                if key not in names and "/" not in key and (relative := texture_relative(key)) and self.base_texture(relative):
                    names[key] = key
        if self.project is not None:
            names.update({name.lower(): name for name in ui_texture_names(self.project.ui_dir, self.project)})
        if self.directory.is_dir():
            names.update({name.lower(): name for name in ui_texture_names(self.directory)})
        return sorted(names.values(), key=str.lower)

    def copy_texture(self, source: Path, relative: Path) -> Path:
        target = self.directory / relative
        if not target.resolve().is_relative_to(self.directory.resolve()):
            raise ValueError("Destino fora da pasta do XML avulso.")
        target.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=target.parent) as temporary:
            staged = Path(temporary) / target.name
            shutil.copy2(source, staged)
            try:
                _install_new_file(staged, target)
            except FileExistsError:
                pass
        return target


def import_target(project: Project, path: Path, name: str | None = None) -> Path:
    filename = path.name if name is None else name.strip()
    if not filename or any(char in filename for char in '/\\:<>"|?*') or filename in (".", ".."):
        raise ValueError("Informe apenas o nome do arquivo XML.")
    if not filename.lower().endswith(".xml"):
        filename += ".xml"
    target = project.import_target(Path(filename))
    if not target.resolve().is_relative_to(project.ui_dir.resolve()):
        raise ValueError("Destino fora da pasta UI do projeto.")
    return target


def compare(document: UIDocument, textures: StandaloneTextures, source: str) -> str | None:
    project, game = textures.project, textures.game
    relative = document.path.name
    if project is not None:
        target = import_target(project, document.path)
        relative = project.relative_key(target)
    if source == "project":
        if project is None or not project.read_path(target).is_file():
            return None
        before = project.load_document(target).text
        label = f"Projeto/{relative}"
    elif source == "official":
        before = game_updates.official_text_for(game, relative) if game is not None else None
        if before is None and relative != document.path.name and game is not None:
            relative = document.path.name
            before = game_updates.official_text_for(game, relative)
        if before is None:
            return None
        label = f"Oficial/{relative}"
    else:
        raise ValueError("Referência de comparação inválida.")
    return unified_xml_diff(before, document.render_text(), label, str(document.path))


_import_lock = RLock()


def import_document(
    document: UIDocument, project: Project, game: Path | None, *,
    name: str | None = None, replace: bool = False, bring_textures: bool = True,
) -> dict:
    """Import current edits, staging all data before writing and never replacing textures."""
    with _import_lock:
        project.files(refresh=True)
        target = import_target(project, document.path, name)
        result = {"path": str(target), "name": target.name}
        if project.read_path(target).is_file() and not replace:
            return {**result, "conflict": True}

        text = document.render_text()
        root = ET.fromstring(text)
        textures = StandaloneTextures(document.path.parent, project, game)
        needed: dict[str, tuple[Path, Path]] = {}
        for element in root.iter() if bring_textures else ():
            relative = texture_relative(element.get("BGmap", ""))
            if relative is None:
                continue
            # BGmap paths are relative to the imported XML, which may replace a nested file.
            key = target.parent.relative_to(project.ui_dir) / relative
            if textures.project_texture(key) or (key.as_posix().lower() not in project.deleted
                    and (textures.base_texture(key) or textures.base_texture(relative))):
                continue
            source = textures.local_texture(relative)
            destination = target.parent / relative
            if source is not None and destination.resolve().is_relative_to(project.ui_dir.resolve()):
                needed.setdefault(key.as_posix().lower(), (source, destination))

        installed: list[Path] = []
        with TemporaryDirectory(prefix=".gf-ui-import-", dir=project.root) as folder:
            stage = Path(folder)
            xml = stage / "import.xml"
            xml.write_bytes(text.encode(document.encoding))
            UIDocument.load(target, source=xml, xml_encoding=True)
            for index, (source, _) in enumerate(needed.values()):
                shutil.copy2(source, stage / str(index))
            try:
                for index, (_, destination) in enumerate(needed.values()):
                    if textures.project_texture(destination.relative_to(project.ui_dir)):
                        continue
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        _install_new_file(stage / str(index), destination)
                    except FileExistsError:
                        continue
                    installed.append(destination)
                if replace or project.relative_key(target).lower() in project.deleted:
                    backup = project.write_from(project.relative_key(target), xml)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        _install_new_file(xml, target)
                    except FileExistsError:
                        for path in installed:
                            path.unlink()
                        return {**result, "conflict": True}
                    backup = None
            except Exception:
                for path in installed:
                    path.unlink(missing_ok=True)
                raise
        project.files(refresh=True)
        return {**result, "conflict": False, "backup": str(backup) if backup else None,
                "textures": [project.relative_key(path) for path in installed]}
