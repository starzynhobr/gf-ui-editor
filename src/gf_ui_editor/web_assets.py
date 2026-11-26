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
from .textures import find_texture, ui_texture_names


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
        self._watched: dict[Path, tuple[str, Project | None, dict[str, tuple]]] = {}
        self._layered: dict[str, tuple[Path, Project]] = {}
        self._thread: Thread | None = None

    def close(self) -> None:
        self._stop.set()

    def base(self, directory: Path, *, watch: bool = False, project: Project | None = None) -> str:
        directory = directory.resolve()
        if project is None and not directory.is_dir():
            raise NotADirectoryError(directory)

        from Microsoft.Web.WebView2.Core import CoreWebView2HostResourceAccessKind
        from System import Action

        # Folder mappings and layered streams need separate hosts even for the same logical folder.
        kind = "layered" if project is not None else "assets"
        digest = sha256(os.fsencode(os.path.normcase(directory))).hexdigest()[:24]
        host = f"gfui-{kind}-{digest}.local"
        native = self._window.native

        def map_folder() -> None:
            core = native.webview.CoreWebView2
            if core is None:
                raise RuntimeError("WebView2 is not ready")
            if project is not None:
                if not self._layered:
                    core.WebResourceRequested += self._serve_texture
                self._layered[host] = (directory, project)
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
                previous = self._watched.get(directory)
                if previous is None or previous[1] is not project:
                    self._watched[directory] = (base, project, self._signatures(directory, project))
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
        directory, project = mapping
        relative = Path(unquote(uri.path.removeprefix("/")))
        stream = None
        if (
            not relative.anchor and ".." not in relative.parts
            and relative.suffix.lower() in (".dds", ".tga") and event.Request.Method == "GET"
        ):
            try:
                logical = directory / relative
                path = project.read_path(logical)
                if not path.is_file():
                    logical = find_texture(logical.parent, logical.name, project)
                    path = project.read_path(logical) if logical is not None else None
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
            for directory, (base, project, previous) in watched:
                current = self._signatures(directory, project)
                names = [name for name in previous.keys() | current.keys() if previous.get(name) != current.get(name)]
                if names and not self._stop.is_set():
                    with self._lock:
                        if self._watched[directory][1] is not project:
                            continue
                        self._watched[directory] = (base, project, current)
                    self._emit("canvas_textures_changed", {"base": base, "names": sorted(names)})
