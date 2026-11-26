"""Proteção da inicialização da web e comando de reinício, sem Qt."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from .preferences import Preferences

WEB_START_TIMEOUT = 20.0


@dataclass(frozen=True)
class Restart:
    path: Path | None


def restart_command(
    executable: str, *, frozen: bool, dev: bool, path: Path | None, language: str | None = None,
    classic_fallback: bool = False,
) -> list[str]:
    command = [executable] if frozen else [executable, "-m", "gf_ui_editor"]
    if dev:
        command.append("--dev")
    if language:
        command.extend(("--lang", language))
    if classic_fallback:
        command.extend(("--ui", "classic", "--web-start-failed"))
    if path is not None:
        command.extend(("--", str(path.resolve())))
    return command


def recover_web_start(requested: str | None, prefs: Preferences) -> bool:
    marker = prefs.get("web_starting")
    return requested is None and prefs.ui_mode == "web" and bool(marker) and not marker.get("retry")


def allow_web_retry(prefs: Preferences) -> None:
    marker = prefs.get("web_starting")
    if marker:
        prefs.set("web_starting", {**marker, "retry": True})


class WebStartup:
    def __init__(self, prefs: Preferences, version: str) -> None:
        self._prefs = prefs
        self._lock = Lock()
        self._pending = True
        self._timed_out = False
        prefs.set("web_starting", {"time": datetime.now(timezone.utc).isoformat(), "version": version})

    def ready(self) -> None:
        with self._lock:
            if self._pending:
                self._prefs.remove("web_starting")
                self._pending = False

    def expire(self) -> bool:
        with self._lock:
            if not self._pending:
                return False
            self._pending = False
            self._timed_out = True
            return True

    def finish(self) -> bool:
        """Encerra a tentativa e devolve se o timeout venceu a confirmação."""
        with self._lock:
            self._pending = False
            return self._timed_out
