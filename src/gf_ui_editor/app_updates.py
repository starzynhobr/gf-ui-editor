"""Atualizações e manifesto remoto vistos por uma interface, sem Qt.

A clássica faz isto dentro da janela (``EditorWindow.check_for_updates``, ``_offer_update``,
``apply_remote_manifest``); aqui fica a mesma regra em funções que devolvem dados, para a
interface nova mostrar as janelas dela:

- ``UpdateSession.check``: consulta a release (``updater``), decide se oferece
  (``should_offer``) e guarda o resultado para ``install``/``skip``;
- ``UpdateSession.automatic``: a verificação ao abrir (opção ligada e uma vez por dia);
- ``offer_payload``: versão nova com as notas no idioma da interface, inclusive as das
  versões puladas (como o ``WhatsNewDialog``);
- ``startup_notices``/``mark_message_seen``: avisos do manifesto (no máximo 3) e versão mínima.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import time

from . import __version__, remote_manifest, updater
from .app_settings import beta_enabled
from .preferences import Preferences
from .release_notes import SECTIONS, ReleaseNotes


def notes_payload(notes: ReleaseNotes | None, language: str, current: str | None) -> dict:
    """Notas agrupadas por versão: só a oferecida, ou também as que a pessoa pulou."""
    if notes is None:
        releases: list[ReleaseNotes] = []
    elif current is not None:
        releases = notes.since(current)
    else:
        releases = [notes]
    rows = []
    for release in releases:
        sections = release.for_language(language)
        if not sections:
            continue
        rows.append({
            "version": release.version,
            "date": release.date,
            "sections": {name: [list(entry) for entry in sections.get(name, [])] for name in SECTIONS},
        })
    return {"grouped": len(releases) > 1, "releases": rows}


def offer_payload(info: updater.UpdateInfo, language: str, current: str = __version__) -> dict:
    return {
        "version": info.version,
        "current": current,
        "page_url": info.page_url,
        "fallback_text": info.notes,
        "verified": info.sha256 is not None,
        "can_install": updater.is_installed_build(),
        **notes_payload(info.structured_notes, language, current),
    }


@dataclass
class CheckResult:
    status: str  # "offer", "latest", "skipped", "error" ou "not_due"
    info: updater.UpdateInfo | None = None
    error: str = ""
    include_betas: bool = False


class UpdateSession:
    """Uma verificação por vez; a última oferta fica guardada para instalar ou pular."""

    def __init__(
        self,
        prefs: Preferences,
        check: Callable[..., updater.UpdateInfo | None] | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.prefs = prefs
        self._check = check
        self._clock = clock
        self.offered: updater.UpdateInfo | None = None

    def check(self, manual: bool) -> CheckResult:
        include_betas = beta_enabled(self.prefs)
        check = self._check or updater.check_for_update
        try:
            info = check(include_prereleases=include_betas)
        except updater.UpdateError as exc:
            return CheckResult("error", error=str(exc), include_betas=include_betas)
        if info is None:
            return CheckResult("latest", include_betas=include_betas)
        if not updater.should_offer(info.version, self.prefs.skipped_update_version, manual):
            return CheckResult("skipped", info, include_betas=include_betas)
        self.offered = info
        return CheckResult("offer", info, include_betas=include_betas)

    def automatic(self) -> CheckResult:
        """Verificação ao abrir: só com a opção ligada e se já passou um dia."""
        if not self.prefs.auto_update_check:
            return CheckResult("not_due")
        now = self._clock()
        if not updater.due_for_check(self.prefs.last_update_check, now):
            return CheckResult("not_due")
        self.prefs.last_update_check = now
        return self.check(manual=False)

    def skip(self, version: str) -> None:
        self.prefs.skipped_update_version = version

    def install(self, version: str, progress: Callable[[int, int], None] | None = None) -> Path:
        """Baixa (conferindo o SHA-256) e roda o instalador da versão oferecida.

        O instalador fecha o editor e o reabre ao terminar; quem chamou fecha a janela.
        """
        info = self.offered
        if info is None or info.version != version:
            raise updater.UpdateError(f"A versão {version} não foi oferecida nesta sessão.")
        installer = updater.download_installer(info, progress=progress)
        updater.launch_installer(installer)
        return installer


# ---- manifesto remoto ---------------------------------------------------------------------

def startup_notices(manifest: remote_manifest.Manifest, prefs: Preferences, language: str, version: str = __version__) -> dict:
    """Versão mínima e avisos a mostrar ao abrir (no máximo ``MESSAGES_PER_START``)."""
    messages = remote_manifest.pending_messages(manifest, beta_enabled(prefs), prefs.manifest_seen, version)
    return {
        "needs_update": manifest.needs_update(version),
        "version": version,
        "min_version": manifest.min_version,
        "messages": [
            {"id": message.id, "level": message.level, "text": message.text(language), "url": message.url}
            for message in messages
        ],
        "disabled": sorted(manifest.disabled_features),
    }


def mark_message_seen(manifest: remote_manifest.Manifest, prefs: Preferences, message_id: str) -> None:
    """Guarda logo que o aviso foi visto (não repete se o editor fechar no meio)."""
    message = next((item for item in manifest.messages if item.id == message_id), None)
    if message is not None:
        prefs.manifest_seen = remote_manifest.mark_seen(prefs.manifest_seen, message)


__all__ = ["CheckResult", "UpdateSession", "mark_message_seen", "notes_payload", "offer_payload", "startup_notices"]
