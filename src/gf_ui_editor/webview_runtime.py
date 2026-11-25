"""Qual interface abrir (clássica ou nova) e se a nova tem como rodar, sem Qt.

A interface nova usa o Edge WebView2. Sem ele (Windows "lite": Tiny11, AtlasOS…) o
pywebview cairia no motor do IE e abriria em branco; então o editor abre a clássica e
avisa. A escolha salva (`ui_mode`) vale ao reiniciar; `--ui` na linha de comando manda.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import sys

from .preferences import UI_MODES

# Cliente do WebView2 Runtime no EdgeUpdate (o mesmo que o instalador oficial registra).
WEBVIEW2_CLIENT = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
_REGISTRY_PATHS = (
    ("HKLM", rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_CLIENT}"),
    ("HKLM", rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_CLIENT}"),
    ("HKCU", rf"Software\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_CLIENT}"),
)

RegistryReader = Callable[[str, str, str], "str | None"]


def _read_registry(hive: str, path: str, name: str) -> str | None:
    if sys.platform != "win32":
        return None
    import winreg

    root = winreg.HKEY_LOCAL_MACHINE if hive == "HKLM" else winreg.HKEY_CURRENT_USER
    try:
        with winreg.OpenKey(root, path, 0, winreg.KEY_READ) as key:
            value = winreg.QueryValueEx(key, name)[0]
    except OSError:
        return None
    return str(value) if value else None


def webview2_version(read: RegistryReader = _read_registry) -> str | None:
    """Versão instalada do WebView2 Runtime, ou None se não houver."""
    for hive, path in _REGISTRY_PATHS:
        version = read(hive, path, "pv")
        if version and version.strip() not in ("", "0.0.0.0"):
            return version.strip()
    return None


def web_build_ready(web_dist: Path) -> bool:
    """O build do front (npm run build) está no pacote."""
    return (web_dist / "index.html").is_file()


def resolve_ui(requested: str | None, saved: str, web_available: Callable[[], bool]) -> tuple[str, bool]:
    """Interface a abrir e se a nova foi pedida mas não pode abrir (cai na clássica).

    `requested` vem de `--ui` (None = usar a preferência salva). `web_available` só é
    chamada quando a nova foi pedida.
    """
    mode = requested or (saved if saved in UI_MODES else "classic")
    if mode == "web" and not web_available():
        return "classic", True
    return mode, False
