"""Read-only file access for the WebView2 canvas."""

from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any
import os
from urllib.parse import unquote, urlsplit

from .project import Project
from .standalone_document import StandaloneTextures
from .textures import ui_texture_names


def _texture_signatures(directory: Path) -> dict[str, tuple[int, int]]:
    signatures = {}
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                if not entry.name.lower().endswith((".dds", ".tga")):
                    continue
                try:
                    if entry.is_file():
                        stat = entry.stat()
                        signatures[entry.name.lower()] = (stat.st_mtime_ns, stat.st_size)
                except OSError:
                    continue
    except OSError:
        pass
    return signatures


class WebAssets:
    def __init__(self, window: Any, emit: Callable[..., None]) -> None:
        self._window = window
        self._emit = emit
        self._stop = Event()
        self._lock = Lock()
        self._mapped: set[str] = set()
        self._watched: dict[str, tuple[Path, Project | StandaloneTextures | None, dict[str, tuple]]] = {}
        self._layered: dict[str, tuple[Path, Project | StandaloneTextures]] = {}
        self._requested: dict[str, set[str]] = {}
        self._thread: Thread | None = None

    def close(self) -> None:
        self._stop.set()

    def base(self, directory: Path, *, watch: bool = False, project: Project | None = None,
             standalone: StandaloneTextures | None = None) -> str:
        directory = directory.resolve()
        source = standalone or project
        if source is None and not directory.is_dir():
            raise NotADirectoryError(directory)

        from Microsoft.Web.WebView2.Core import CoreWebView2HostResourceAccessKind
        from System import Action

        # Folder mappings and layered streams need separate hosts even for the same logical folder.
        kind = "standalone" if standalone is not None else "layered" if project is not None else "assets"
        identity = [directory]
        if standalone is not None:
            identity.extend((standalone.project.root if standalone.project else Path(), standalone.game or Path()))
        digest = sha256(b"\0".join(os.fsencode(os.path.normcase(path)) for path in identity)).hexdigest()[:24]
        host = f"gfui-{kind}-{digest}.local"
        native = self._window.native

        def map_folder() -> None:
            core = native.webview.CoreWebView2
            if core is None:
                raise RuntimeError("WebView2 is not ready")
            if source is not None:
                if not self._layered:
                    core.WebResourceRequested += self._serve_texture
                self._layered[host] = (directory, source)
                if host not in self._mapped:
                    from Microsoft.Web.WebView2.Core import CoreWebView2WebResourceContext

                    core.AddWebResourceRequestedFilter(f"https://{host}/*", CoreWebView2WebResourceContext.All)
            elif host not in self._mapped:
                core.SetVirtualHostNameToFolderMapping(host, str(directory), CoreWebView2HostResourceAccessKind.Allow)
            self._mapped.add(host)

        if native.InvokeRequired:
            native.Invoke(Action(map_folder))
        else:
            map_folder()

        base = f"https://{host}/"
        if watch:
            with self._lock:
                previous = self._watched.get(host)
                if isinstance(source, StandaloneTextures):
                    self._requested.setdefault(host, set())
                    self._watched[host] = (directory, source, previous[2] if previous else {})
                elif previous is None or previous[1] is not source:
                    self._watched[host] = (directory, source, self._signatures(directory, source))
                if self._thread is None:
                    self._thread = Thread(target=self._watch, name="web-canvas-textures", daemon=True)
                    self._thread.start()
        return base

    def _serve_texture(self, core, event) -> None:
        from System.IO import File, FileAccess, FileMode, FileShare

        uri = urlsplit(event.Request.Uri)
        mapping = self._layered.get(uri.hostname)
        if mapping is None:
            return
        directory, source = mapping
        relative = Path(unquote(uri.path.removeprefix("/")))
        stream = None
        if (
            not relative.anchor and ".." not in relative.parts
            and relative.suffix.lower() in (".dds", ".tga") and event.Request.Method == "GET"
        ):
            try:
                if isinstance(source, StandaloneTextures):
                    name = relative.as_posix()
                    path = source.resolve(name)
                    with self._lock:
                        self._requested.setdefault(uri.hostname, set()).add(name)
                else:
                    logical = directory / relative
                    path = source.read_path(logical)
                    if not path.is_file():
                        key = logical.relative_to(source.ui_dir)
                        lookup = StandaloneTextures(directory, source, source.game_dir)
                        path = lookup.project_texture(key)
                        if path is None and key.as_posix().lower() not in source.deleted:
                            path = lookup.fallback_texture(key) or lookup.fallback_texture(relative)
                if path is not None and path.is_file():
                    stream = File.Open(str(path), FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete)
            except Exception:
                # An external image editor can replace the file between lookup and open.
                pass
        headers = "Access-Control-Allow-Origin: *\r\nContent-Type: application/octet-stream\r\nCache-Control: no-store"
        event.Response = core.Environment.CreateWebResourceResponse(
            stream, 200 if stream is not None else 404, "OK" if stream is not None else "Not Found", headers,
        )

    @staticmethod
    def _signatures(directory: Path, project: Project | None) -> dict[str, tuple]:
        if project is None:
            return _texture_signatures(directory)
        if not project.light:
            return {name: (directory / name, *sig) for name, sig in _texture_signatures(directory).items()}
        signatures = {}
        for name in ui_texture_names(directory, project):
            path = project.read_path(directory / name)
            try:
                stat = path.stat()
                signatures[name.lower()] = (path, stat.st_mtime_ns, stat.st_size)
            except OSError:
                continue
        return signatures

    def _watch(self) -> None:
        while not self._stop.wait(1):
            with self._lock:
                watched = list(self._watched.items())
            for host, (directory, source, previous) in watched:
                if isinstance(source, StandaloneTextures):
                    with self._lock:
                        requested = self._requested[host].copy()
                    current = {}
                    for name in requested:
                        signature = ()
                        try:
                            path = source.resolve(name)
                            if path is not None:
                                stat = path.stat()
                                signature = (path, stat.st_mtime_ns, stat.st_size)
                        except (OSError, ValueError):
                            pass
                        current[name] = signature
                    known = previous.keys()
                else:
                    current = self._signatures(directory, source)
                    known = previous.keys() | current.keys()
                names = [name.lower() for name in known if previous.get(name) != current.get(name)]
                with self._lock:
                    if self._watched[host][1] is not source:
                        continue
                    self._watched[host] = (directory, source, current)
                if names and not self._stop.is_set():
                    self._emit("canvas_textures_changed", {"base": f"https://{host}/", "names": sorted(set(names))})
