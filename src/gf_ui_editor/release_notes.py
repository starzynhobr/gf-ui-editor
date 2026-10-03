"""Notas de versão estruturadas e traduzidas (`release-notes.json`).

O mesmo arquivo vai embutido no aplicativo (novidades da versão instalada) e é
anexado a cada release do GitHub (novidades da versão oferecida na atualização).

Formato:

    {
      "version": "0.2.5",
      "date": "2026-10-03",
      "notes": {
        "pt_BR": {"new": [["Título.", "Texto."]], "improved": [...], "fixed": [...]},
        "en_US": {...}
      }
    }
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

SECTIONS = ("new", "improved", "fixed")
FALLBACK_LANGUAGES = ("en_US", "pt_BR")
BUNDLED_PATH = Path(__file__).resolve().parent / "assets" / "release-notes.json"

Entry = tuple[str, str]


@dataclass(frozen=True)
class ReleaseNotes:
    version: str
    date: str
    notes: dict[str, dict[str, list[Entry]]]

    def for_language(self, language: str) -> dict[str, list[Entry]]:
        """Seções no idioma pedido; se faltar, inglês e depois português."""
        for candidate in (language, *FALLBACK_LANGUAGES):
            sections = self.notes.get(candidate)
            if sections and any(sections.get(name) for name in SECTIONS):
                return sections
        return {}


def parse(text: str | bytes) -> ReleaseNotes | None:
    """Lê e valida o JSON; qualquer coisa fora do formato vira None (dado externo)."""
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("notes"), dict):
        return None
    notes: dict[str, dict[str, list[Entry]]] = {}
    for language, sections in data["notes"].items():
        if not isinstance(language, str) or not isinstance(sections, dict):
            continue
        cleaned: dict[str, list[Entry]] = {}
        for name in SECTIONS:
            entries = sections.get(name, [])
            if not isinstance(entries, list):
                continue
            items = [
                (str(entry[0])[:200], str(entry[1])[:1000])
                for entry in entries[:20]
                if isinstance(entry, (list, tuple)) and len(entry) == 2
            ]
            if items:
                cleaned[name] = items
        if cleaned:
            notes[language] = cleaned
    if not notes:
        return None
    return ReleaseNotes(str(data.get("version", ""))[:20], str(data.get("date", ""))[:20], notes)


def bundled() -> ReleaseNotes | None:
    try:
        return parse(BUNDLED_PATH.read_bytes())
    except OSError:
        return None
