"""Read-only file access for the WebView2 canvas."""

from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any
import os


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
        self._watched: dict[Path, tuple[str, dict[str, tuple[int, int]]]] = {}
        self._thread: Thread | None = None

    def close(self) -> None:
        self._stop.set()

    def base(self, directory: Path, *, watch: bool = False) -> str:
        directory = directory.resolve(strict=True)
        if not directory.is_dir():
            raise NotADirectoryError(directory)

        from Microsoft.Web.WebView2.Core import CoreWebView2HostResourceAccessKind
        from System import Action

        host = "gfui-assets-" + sha256(os.fsencode(os.path.normcase(directory))).hexdigest()[:24] + ".local"
        native = self._window.native

        def map_folder() -> None:
            if host in self._mapped:
                return
            core = native.webview.CoreWebView2
            if core is None:
                raise RuntimeError("WebView2 is not ready")
            core.SetVirtualHostNameToFolderMapping(host, str(directory), CoreWebView2HostResourceAccessKind.Allow)
            self._mapped.add(host)

        if native.InvokeRequired:
            native.Invoke(Action(map_folder))
        else:
            map_folder()

        base = f"https://{host}/"
        if watch:
            with self._lock:
                if directory not in self._watched:
                    self._watched[directory] = (base, _texture_signatures(directory))
                if self._thread is None:
                    self._thread = Thread(target=self._watch, name="web-canvas-textures", daemon=True)
                    self._thread.start()
        return base

    def _watch(self) -> None:
        while not self._stop.wait(1):
            with self._lock:
                watched = list(self._watched.items())
            for directory, (base, previous) in watched:
                current = _texture_signatures(directory)
                names = [name for name in previous.keys() | current.keys() if previous.get(name) != current.get(name)]
                if names and not self._stop.is_set():
                    with self._lock:
                        self._watched[directory] = (base, current)
                    self._emit("canvas_textures_changed", {"base": base, "names": sorted(names)})
