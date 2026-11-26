"""Quem ajudou a construir: lista do programa, atualizável pelo repositório sem lançar versão.

O `app-manifest.json` traz ``contributors_rev`` (um número). Quando ele muda, o editor baixa
uma vez o `contributors.json` da raiz do repositório (branch main), valida e guarda nas
preferências; nas aberturas seguintes usa a cópia guardada. Sem internet, arquivo inválido ou
número igual: nada é baixado e vale a última lista boa (ou a que veio no programa).

Cada pessoa pode ter ``"anonymous": true``: o nome some (aparece "Anônimo"), mas as
contribuições e as contagens continuam.

A lista vem só deste repositório e é sempre mostrada como texto puro. Mesmo assim tudo é
validado: cores ``#RRGGBB``, etiquetas conhecidas e limites de tamanho.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import urllib.request

from . import __version__
from .updater import REPOSITORY

CONTRIBUTORS_URL = f"https://raw.githubusercontent.com/{REPOSITORY}/main/contributors.json"
BUNDLED_PATH = Path(__file__).resolve().parent / "assets" / "contributors.json"
SIZE_LIMIT = 128_000
TIMEOUT_SECONDS = 8
MAX_PEOPLE = 50
MAX_ITEMS = 60
MAX_NAME = 40
MAX_TEXT = 200
TAGS = ("ideas", "qa", "navigation")
NEUTRAL_COLOR = "#52525B"
_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
_VERSION = re.compile(r"^\d+(\.\d+){0,3}(-[0-9A-Za-z.]+)?$")
CACHE_KEY = "contributors_cache"
REV_KEY = "contributors_rev"


def _clean_text(value: object) -> str | None:
    return value.strip()[:MAX_TEXT] if isinstance(value, str) and value.strip() else None


def _clean_texts(value: object) -> dict[str, str] | str | None:
    if isinstance(value, str):
        return _clean_text(value)
    if isinstance(value, dict):
        texts = {str(code)[:8]: text for code, raw in value.items() if (text := _clean_text(raw))}
        return texts or None
    return None


def _clean_person(data: object) -> dict | None:
    if not isinstance(data, dict):
        return None
    anonymous = data.get("anonymous") is True
    name = data.get("name")
    name = name.strip()[:MAX_NAME] if isinstance(name, str) else ""
    if not name and not anonymous:
        return None
    person: dict = {
        "name": "" if anonymous else name,
        "color": NEUTRAL_COLOR if anonymous else (data["color"] if isinstance(data.get("color"), str) and _COLOR.match(data["color"]) else NEUTRAL_COLOR),
        "tags": [tag for tag in data.get("tags", []) if tag in TAGS][: len(TAGS)] if isinstance(data.get("tags"), list) else [],
    }
    if anonymous:
        person["anonymous"] = True
    items = []
    for item in data.get("items", [])[:MAX_ITEMS] if isinstance(data.get("items"), list) else []:
        if not isinstance(item, dict) or not (texts := _clean_texts(item.get("text"))):
            continue
        version = item.get("version")
        clean = {"text": texts}
        if isinstance(version, str) and _VERSION.match(version.strip()):
            clean["version"] = version.strip()
        items.append(clean)
    if items:
        person["items"] = items
    legacy = data.get("text")
    if isinstance(legacy, dict):
        texts = {
            str(code)[:8]: [text for raw in values[:MAX_ITEMS] if (text := _clean_text(raw))]
            for code, values in legacy.items()
            if isinstance(values, list)
        }
        texts = {code: values for code, values in texts.items() if values}
        if texts:
            person["text"] = texts
    elif (text := _clean_text(legacy)) is not None:
        person["text"] = text
    return person


def validate(data: object) -> list[dict] | None:
    """Lista limpa, ou None se o formato não for uma lista de pessoas."""
    if not isinstance(data, list):
        return None
    people = [person for raw in data[:MAX_PEOPLE] if (person := _clean_person(raw))]
    return people if people or not data else None


def bundled() -> list[dict]:
    try:
        return validate(json.loads(BUNDLED_PATH.read_text(encoding="utf-8"))) or []
    except (OSError, ValueError):
        return []


def cached(prefs) -> list[dict] | None:
    """A última lista baixada, se houver e for válida."""
    try:
        raw = prefs.get(CACHE_KEY)
        return validate(json.loads(raw)) if raw else None
    except (ValueError, TypeError):
        return None


def load(prefs=None) -> list[dict]:
    """A última lista baixada (se válida) ou a que veio no programa."""
    people = cached(prefs) if prefs is not None else None
    return people if people is not None else bundled()


def needs_fetch(rev: int | None, prefs) -> bool:
    return rev is not None and str(rev) != prefs.get(REV_KEY)


def fetch(url: str = CONTRIBUTORS_URL) -> list[dict] | None:
    """Baixa e valida a lista; qualquer falha devolve None."""
    request = urllib.request.Request(url, headers={"User-Agent": f"gf-ui-editor/{__version__}"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310 - URL fixa em https
            payload = response.read(SIZE_LIMIT + 1)
    except (OSError, ValueError):
        return None
    if len(payload) > SIZE_LIMIT:
        return None
    try:
        return validate(json.loads(payload.decode("utf-8-sig")))
    except (UnicodeDecodeError, ValueError):
        return None


def store(prefs, rev: int, people: list[dict]) -> None:
    prefs.set(CACHE_KEY, json.dumps(people, ensure_ascii=False))
    prefs.set(REV_KEY, str(rev))


def refresh(prefs, rev: int | None, fetcher=fetch) -> bool:
    """Baixa a lista se o número do manifesto mudou; True se uma lista nova foi guardada."""
    if not needs_fetch(rev, prefs):
        return False
    people = fetcher()
    if people is None:
        return False
    store(prefs, rev, people)
    return True
