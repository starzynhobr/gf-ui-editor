"""Interface nova (web): janela pywebview + ponte para os serviços sem Qt.

`python -m gf_ui_editor --ui web` abre a interface nova; `--dev` usa o servidor do Vite
(http://localhost:5173, com hot reload) em vez do build em `web_dist/`.

Regras (vault/migracao-web.md, vault/web-bridge.md):
- Pela ponte só vão comandos e dados pequenos (JSON). Imagens nunca: o front lê os .dds
  direto do disco.
- O build abre por file:// (o servidor HTTP embutido do pywebview trava a janela no Windows).
- Python -> front: `emit(evento, dados)` chama window.__gf.emit no JavaScript.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .web_api.canvas import CanvasApi
from .web_api.document import DocumentApi
from .web_api.projects import ProjectsApi
from .web_api.maintenance import MaintenanceApi
from .web_api.texts import TextsApi
from .web_api.text_updates import TextUpdatesApi

APP_TITLE = "STZ GF UI"
DEV_URL = "http://localhost:5173"
WEB_DIST = Path(__file__).resolve().parent / "web_dist"


class WebApi(ProjectsApi, CanvasApi, DocumentApi, TextsApi, TextUpdatesApi, MaintenanceApi):
    """Métodos chamáveis pelo front (`call("nome", ...)` em web/src/bridge.ts).

    Cada método público vira `window.pywebview.api.nome`. Devolvem só tipos JSON.
    Atributos que não são da API começam com `_` (o pywebview expõe os públicos).
    Cada área fica no seu módulo em `web_api/` (um dono por arquivo).
    """

    def __init__(
        self, language: str, dev: bool, prefs: Any = None, default_ui_directory: Path | None = None,
        xml: Path | None = None,
    ) -> None:
        self._language = language
        self._dev = dev
        self._window: Any = None
        self._setup_projects(prefs, default_ui_directory, xml)
        self._setup_document()

    # ---- infraestrutura ---------------------------------------------------------------
    def _attach(self, window: Any) -> None:
        """Liga a janela: cada área prepara o que precisa dela (ex.: pastas mapeadas do canvas)."""
        self._window = window
        self._attach_canvas_assets()
        self._attach_projects(window)

    def _emit(self, event: str, payload: Any = None) -> None:
        if self._window is not None:
            self._window.evaluate_js(f"window.__gf && window.__gf.emit({json.dumps(event)}, {json.dumps(payload)})")

    # ---- API ------------------------------------------------------------------------
    def app_info(self) -> dict:
        return {"version": __version__, "language": self._language, "dev": self._dev}


def _start_url(dev: bool) -> str:
    if dev:
        return DEV_URL
    index = WEB_DIST / "index.html"
    if not index.is_file():
        raise SystemExit(f"Interface web não compilada: rode `npm run build` em web/ ({index} não existe).")
    return index.as_uri()


def run(
    language: str = "pt_BR", dev: bool = False, xml: Path | None = None, prefs: Any = None,
    default_ui_directory: Path | None = None,
) -> int:
    """`prefs`: as mesmas preferências da clássica (o app.py passa o objeto global)."""
    import webview

    api = WebApi(language, dev, prefs, default_ui_directory, xml)
    window = webview.create_window(
        APP_TITLE, _start_url(dev), js_api=api, width=1440, height=900, min_size=(1024, 680),
        background_color="#111318",
    )
    api._attach(window)
    window.events.shown += lambda: apply_window_chrome(window)
    webview.start(debug=dev, gui="edgechromium" if sys.platform == "win32" else None)
    return 0


def apply_window_chrome(window: Any) -> None:
    """Barra de título escura (DWM) e ícone do app na janela nativa do Windows."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        hwnd = int(window.native.Handle.ToInt64())
        dark = ctypes.c_int(1)
        # DWMWA_USE_IMMERSIVE_DARK_MODE: 20 (Windows 10 20H1+ e 11); 19 nas versões anteriores.
        for attribute in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(dark), ctypes.sizeof(dark)) == 0:
                break
        icon = Path(__file__).resolve().parent / "assets" / "app-icon.ico"
        if icon.is_file():
            from System.Drawing import Icon  # type: ignore[import-not-found]

            def set_icon() -> None:
                window.native.Icon = Icon(str(icon))

            if getattr(window.native, "InvokeRequired", False):
                window.native.Invoke(set_icon)
            else:
                set_icon()
    except Exception:  # noqa: BLE001 - só aparência; a janela segue sem isso
        pass


__all__ = ["WebApi", "run"]
