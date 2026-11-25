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
from .web_api.projects import ProjectsApi

APP_TITLE = "STZ GF UI"
DEV_URL = "http://localhost:5173"
WEB_DIST = Path(__file__).resolve().parent / "web_dist"


class WebApi(ProjectsApi, CanvasApi):
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

    # ---- infraestrutura ---------------------------------------------------------------
    def _attach(self, window: Any) -> None:
        self._window = window

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
    webview.start(debug=dev, gui="edgechromium" if sys.platform == "win32" else None)
    return 0


__all__ = ["WebApi", "run"]
