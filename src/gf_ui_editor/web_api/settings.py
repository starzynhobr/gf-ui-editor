"""Ponte: tela de Configurações (dono: bloco 4, casca).

Só chama ``app_settings`` (as mesmas preferências da clássica). A pasta do jogo é escolhida
pelo ``pick_game_dir`` de ``projects.py`` e a captura própria pelo ``canvas_choose_background``
do canvas; aqui só se grava e se lê.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .. import app_settings
from ..project import configured_game_dir


class SettingsApi:
    """Métodos públicos viram window.pywebview.api.<nome>. Só tipos JSON."""

    def _settings_default_game_dir(self) -> Path | None:
        default_ui = getattr(self, "_default_ui_directory", None)
        return configured_game_dir("", default_ui) if default_ui is not None else None

    def settings_state(self) -> dict:
        return app_settings.snapshot(self._prefs, self._settings_default_game_dir())

    def settings_set(self, name: str, value: Any) -> dict:
        """Grava uma opção e devolve a tela atualizada. Valor inválido vira erro no front."""
        app_settings.apply(self._prefs, name, value)
        if name == "language" and hasattr(self, "_language"):
            self._language = value
        return self.settings_state()

    def settings_reset(self, what: str) -> dict:
        app_settings.reset(self._prefs, what)
        return self.settings_state()


__all__ = ["SettingsApi"]
