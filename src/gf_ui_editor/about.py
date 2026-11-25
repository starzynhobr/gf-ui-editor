from __future__ import annotations

import json
import os
from pathlib import Path
import sys

from . import updater


CONTRIBUTORS_PATH = Path(__file__).resolve().parent / "assets" / "contributors.json"

GAME_RESOLUTIONS = (
    (800, 600),
    (1024, 768),
    (1280, 720),
    (1280, 1024),
    (1366, 768),
    (1600, 900),
    (1920, 1080),
    (2560, 1440),
)


def parse_resolution(text: str) -> tuple[int, int] | None:
    """Aceita "1920x1080", "1920×1080" ou "1920 1080"."""
    parts = text.lower().replace("×", "x").replace(" ", "x").split("x")
    numbers = [part for part in parts if part]
    if len(numbers) != 2:
        return None
    try:
        width, height = int(numbers[0]), int(numbers[1])
    except ValueError:
        return None
    if not (100 <= width <= 10000 and 100 <= height <= 10000):
        return None
    return width, height


def text_editor_command() -> tuple[str, str]:
    """Programa para abrir XML como texto: Notepad++ se instalado, senão o Bloco de Notas.

    Devolve (executável, nome para o menu).
    """
    candidates = []
    if sys.platform == "win32":
        try:
            import winreg

            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                for view in (0, getattr(winreg, "KEY_WOW64_32KEY", 0)):
                    try:
                        with winreg.OpenKey(hive, r"SOFTWARE\Notepad++", 0, winreg.KEY_READ | view) as key:
                            folder = winreg.QueryValueEx(key, "")[0]
                    except OSError:
                        continue
                    candidates.append(Path(folder) / "notepad++.exe")
        except ImportError:
            pass
    for variable in ("ProgramFiles", "ProgramFiles(x86)"):
        if os.environ.get(variable):
            candidates.append(Path(os.environ[variable]) / "Notepad++" / "notepad++.exe")
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate), "Notepad++"
    return "notepad.exe", "Bloco de Notas"


def load_contributors() -> list[dict]:
    try:
        return json.loads(CONTRIBUTORS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def contributor_items(person: dict, language: str) -> list[tuple[str, str | None]]:
    """Contribuições de uma pessoa como (texto, versão), das mais recentes para as mais antigas.

    Formato novo: "items": [{"version": "0.7.0", "text": {"pt_BR": "…", …}}, …].
    Formato antigo (sem versão): "text": {"pt_BR": ["…", …]} ou um texto só; mantém a ordem.
    """
    def pick(texts: object) -> object:
        if not isinstance(texts, dict):
            return texts
        return texts.get(language) or texts.get("pt_BR") or next(iter(texts.values()), "")

    items: list[tuple[str, str | None]] = []
    for item in person.get("items", []) if isinstance(person.get("items"), list) else []:
        if isinstance(item, dict) and isinstance(text := pick(item.get("text")), str) and text:
            version = item.get("version")
            items.append((text, str(version) if version else None))
    if items:
        # Estável: dentro da mesma versão, vale a ordem escrita no arquivo.
        return sorted(items, key=lambda entry: updater.parse_version(entry[1] or "0"), reverse=True)
    legacy = pick(person.get("text", {}))
    if isinstance(legacy, str):
        legacy = [legacy]
    return [(text, None) for text in legacy if isinstance(text, str) and text]
