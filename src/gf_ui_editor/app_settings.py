"""Tela de Configurações, sem Qt: o que ela mostra, o que aceita gravar e o que dá para rever.

Usa as mesmas preferências da clássica (``preferences.Preferences``): o que se muda numa
interface vale na outra. A interface nova chama isto pela ponte (``web_api/settings.py``).

- ``snapshot``: valores atuais e os dados para montar a tela (resoluções, versões…);
- ``apply``: grava uma opção depois de conferir o valor (``ValueError`` se inválido);
- ``review``/``reset``: o que foi lembrado ao longo do uso e pode ser esquecido (versão
  pulada, avisos já vistos, larguras dos painéis…).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import __version__, updater
from .about import GAME_RESOLUTIONS, parse_resolution
from .game_layout import looks_like_game_dir, normalize_game_dir
from .preferences import KEYS, UI_LANGUAGES, UI_MODES, Preferences

THEMES = ("dark", "midnight", "light", "cappuccino", "rosa")  # os mesmos de web_api/ui_state.py
NAVIGATION_STYLES = ("corel", "paintnet", "photoshop")  # os mesmos de EditorView.NAVIGATION_STYLES
BACKGROUND_MODES = ("builtin", "custom", "none")

# Opções liga/desliga que a tela grava direto.
FLAGS = (
    "auto_update_check",
    "beta_updates",
    "publish_on_save",
    "publish_confirmed",
    "offer_project_on_open",
    "canvas_saved_positions",
    "canvas_character",
)
CHOICES: dict[str, tuple[str, ...]] = {
    "language": UI_LANGUAGES,
    "ui_mode": UI_MODES,
    "web_theme": THEMES,
    "navigation_style": NAVIGATION_STYLES,
}
SETTABLE = (*FLAGS, *CHOICES, "game_dir", "game_resolution", "background_mode")

# O que dá para rever/esquecer (botões "Limpar" da seção Geral).
RESETS = ("skipped_update", "manifest_seen", "layout")


def beta_enabled(prefs: Preferences) -> bool:
    """Canal beta: a escolha salva; sem escolha, uma versão beta instalada já fica nele."""
    return prefs.get("beta_updates", updater.beta_default(__version__))


def _choice(prefs: Preferences, name: str) -> str:
    value = prefs.get(name)
    allowed = CHOICES[name]
    return value if value in allowed else str(KEYS[name].default if KEYS[name].default in allowed else allowed[0])


def _resolution(prefs: Preferences) -> str:
    value = prefs.game_resolution
    return value if value == "off" or parse_resolution(value) else "game"


def _background(prefs: Preferences) -> str:
    background = prefs.game_background
    mode = prefs.get("background_mode", "custom" if background else "builtin")
    return mode if mode in BACKGROUND_MODES else "builtin"


def review(prefs: Preferences) -> dict:
    """O que o editor guardou ao longo do uso e a tela oferece esquecer."""
    layout = prefs.get("web_layout")
    return {
        "skipped_update": prefs.skipped_update_version,
        "manifest_seen": len(prefs.manifest_seen),
        "layout": bool(layout)
        or prefs.files_section_order != ""
        or prefs.files_section_heights not in ("", "{}")
        or prefs.get("tree_hidden_columns") != KEYS["tree_hidden_columns"].default,
    }


def snapshot(prefs: Preferences, default_game_dir: Path | None = None) -> dict:
    """Tudo que a tela de Configurações mostra (só tipos JSON)."""
    game_dir = prefs.game_dir
    return {
        "version": __version__,
        "beta_build": updater.is_prerelease(__version__),
        "can_install": updater.is_installed_build(),
        "values": {
            **{name: bool(prefs.get(name)) for name in FLAGS if name != "beta_updates"},
            "beta_updates": beta_enabled(prefs),
            **{name: _choice(prefs, name) for name in CHOICES},
            "game_dir": game_dir,
            "game_resolution": _resolution(prefs),
            "background_mode": _background(prefs),
        },
        "game_dir_valid": bool(game_dir) and looks_like_game_dir(Path(game_dir)),
        # Sem pasta escolhida, o editor usa a que encontra sozinho (a padrão do jogo).
        "game_dir_default": str(default_game_dir) if default_game_dir is not None else None,
        "game_background": prefs.game_background,
        "has_custom_background": bool(prefs.game_background) and Path(prefs.game_background).is_file(),
        "resolutions": [f"{width}x{height}" for width, height in GAME_RESOLUTIONS],
        "review": review(prefs),
    }


def apply(prefs: Preferences, name: str, value: Any) -> Any:
    """Grava a opção ``name`` (valor já normalizado é devolvido). ``ValueError`` se não vale."""
    if name in FLAGS:
        if type(value) is not bool:
            raise ValueError(f"{name}: esperado verdadeiro/falso")
        prefs.set(name, value)
        return value
    if name in CHOICES:
        if value not in CHOICES[name]:
            raise ValueError(f"{name}: valor desconhecido {value!r}")
        prefs.set(name, value)
        return value
    if name == "game_dir":
        if not isinstance(value, str):
            raise ValueError("game_dir: esperado um caminho")
        if not value.strip():
            prefs.game_dir = ""
            return ""
        folder = Path(value.strip())
        if not folder.is_dir():
            raise ValueError(f"Pasta não encontrada: {folder}")
        folder = normalize_game_dir(folder)
        prefs.game_dir = str(folder)
        return str(folder)
    if name == "game_resolution":
        if not isinstance(value, str):
            raise ValueError("game_resolution: esperado texto")
        if value in ("game", "off"):
            prefs.game_resolution = value
            return value
        size = parse_resolution(value)
        if size is None:
            raise ValueError("Use o formato largura x altura, por exemplo 1366x768.")
        prefs.game_resolution = f"{size[0]}x{size[1]}"
        return prefs.game_resolution
    if name == "background_mode":
        if value not in BACKGROUND_MODES:
            raise ValueError(f"background_mode: valor desconhecido {value!r}")
        if value == "custom" and not Path(prefs.game_background or "").is_file():
            raise ValueError("Nenhuma captura própria escolhida.")
        prefs.background_mode = value
        return value
    raise ValueError(f"Opção desconhecida: {name}")


def reset(prefs: Preferences, what: str) -> dict:
    """Esquece o que foi lembrado: versão pulada, avisos vistos ou o arranjo dos painéis."""
    if what == "skipped_update":
        prefs.skipped_update_version = ""
    elif what == "manifest_seen":
        prefs.manifest_seen = set()
    elif what == "layout":
        prefs.remove("web_layout")
        prefs.remove("files_section_order")
        prefs.remove("files_section_heights")
        prefs.remove("tree_hidden_columns")
    else:
        raise ValueError(f"Nada a limpar com o nome {what!r}")
    return review(prefs)


__all__ = [
    "BACKGROUND_MODES", "CHOICES", "FLAGS", "NAVIGATION_STYLES", "RESETS", "SETTABLE", "THEMES",
    "apply", "beta_enabled", "reset", "review", "snapshot",
]
