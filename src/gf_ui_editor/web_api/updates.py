"""Ponte: atualizador, manifesto remoto e a instância única (dono: bloco 4, casca).

Só chama ``app_updates`` (regras do atualizador e do manifesto, as mesmas da clássica) e
``updater`` (download e instalador). O pywebview roda cada chamada numa thread própria,
então a consulta à rede pode bloquear aqui sem travar a janela.

Eventos para o front:
- ``progress`` ({label: "update", done, total}) durante o download;
- ``open_external`` ({path}) quando um segundo .exe manda um arquivo para esta janela.
"""

from __future__ import annotations

import sys
import threading
from typing import Any

from .. import __version__, app_updates, desktop, updater

MANIFEST_WAIT_SECONDS = 10.0


class UpdatesApi:
    """Métodos públicos viram window.pywebview.api.<nome>. Só tipos JSON."""

    def _updates(self) -> app_updates.UpdateSession:
        session = getattr(self, "_update_session", None)
        if session is None:
            session = self._update_session = app_updates.UpdateSession(self._prefs)
        return session

    def _update_result(self, result: app_updates.CheckResult) -> dict:
        language = getattr(self, "_language", "pt_BR")
        payload: dict[str, Any] = {
            "status": result.status,
            "current": __version__,
            "include_betas": result.include_betas,
            "error": result.error,
        }
        if result.status == "offer" and result.info is not None:
            payload["offer"] = app_updates.offer_payload(result.info, language)
        return payload

    # ---- atualizações ----------------------------------------------------------------------
    def update_check(self, manual: bool = True) -> dict:
        """Verificar atualizações… (manual) ou a de quem liga o canal beta."""
        return self._update_result(self._updates().check(bool(manual)))

    def update_auto_check(self) -> dict:
        """Verificação ao abrir: só com a opção ligada e uma vez por dia (status "not_due")."""
        return self._update_result(self._updates().automatic())

    def update_skip(self, version: str) -> None:
        self._updates().skip(str(version))

    def update_install(self, version: str) -> dict:
        """Baixa e instala; rodando pelo código-fonte, abre a página da release."""
        session = self._updates()
        info = session.offered
        if info is None or info.version != version:
            raise ValueError(f"A versão {version} não foi oferecida nesta sessão.")
        if not updater.is_installed_build():
            desktop.open_url(info.page_url)
            return {"opened_page": True}
        session.install(version, self._progress("update"))
        # O instalador fecha o que restar e reabre o editor: a janela fecha logo depois de
        # o front receber a resposta (o usuário já salvou ou descartou).
        threading.Timer(0.4, self._close_for_update).start()
        return {"installing": True}

    def _close_for_update(self) -> None:
        self._force_close = True
        window = getattr(self, "_window", None)
        if window is not None:
            window.destroy()

    # ---- manifesto remoto -------------------------------------------------------------------
    def manifest_notices(self) -> dict | None:
        """Versão mínima e avisos (no máximo 3) do manifesto lido ao abrir; None sem manifesto."""
        ready = getattr(self, "_manifest_ready", None)
        if ready is not None:
            ready.wait(MANIFEST_WAIT_SECONDS)
        manifest = getattr(self, "_manifest", None)
        if manifest is None:
            return None
        return app_updates.startup_notices(manifest, self._prefs, getattr(self, "_language", "pt_BR"))

    def manifest_mark_seen(self, message_id: str) -> None:
        app_updates.mark_message_seen(self._manifest, self._prefs, str(message_id))

    # ---- instância única ---------------------------------------------------------------------
    def _on_instance_message(self, message: dict) -> None:
        """Outro .exe abriu: traz esta janela para a frente e abre o arquivo que ele mandou."""
        self._bring_to_front()
        path = message.get("open")
        if isinstance(path, str) and path:
            self._emit("open_external", {"path": path})

    def _bring_to_front(self) -> None:
        window = getattr(self, "_window", None)
        if window is None:
            return
        try:
            window.restore()
            window.show()
        except Exception:  # noqa: BLE001 - só conforto; o arquivo abre mesmo assim
            pass
        if sys.platform == "win32":
            try:
                import ctypes

                hwnd = int(window.native.Handle.ToInt64())
                ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                ctypes.windll.user32.SetForegroundWindow(hwnd)
            except Exception:  # noqa: BLE001
                pass

    def _progress(self, label: str):  # ProjectsApi implementa
        return None

    def _emit(self, event: str, payload: Any = None) -> None:  # o WebApi sobrescreve
        pass


__all__ = ["UpdatesApi"]
