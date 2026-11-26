"""Estado das Novidades compartilhado pelas duas interfaces, sem Qt."""

from typing import TypedDict

from .preferences import Preferences
from .updater import is_newer


class WhatsNewState(TypedDict):
    version: str
    auto_open: bool
    pill: bool


def notes_need_showing(prefs: Preferences, version: str) -> bool:
    seen = prefs.get("notes_seen_version")
    return not seen or is_newer(version, seen)


def whats_new_state(prefs: Preferences, version: str) -> WhatsNewState:
    return {
        "version": version,
        "auto_open": notes_need_showing(prefs, version),
        "pill": prefs.get("notes_pill_version") == version,
    }
