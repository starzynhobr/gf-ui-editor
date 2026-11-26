"""Preferências do usuário, sem Qt.

Cada chave é declarada uma vez (nome, tipo, padrão) em ``KEYS``/``PREFIXES``. O
armazenamento fica atrás de ``Store`` (``get``, ``set``, ``remove``): a interface Qt usa
um adaptador do ``QSettings("Local", "GF UI Editor")`` (Registro no Windows) que grava
os mesmos valores, no mesmo formato de sempre; os testes usam ``MemoryStore``.

Formato gravado por tipo (igual ao das versões até a 0.7.0):

- ``flag``: texto ``"true"``/``"false"``;
- ``bool``: bool de verdade (o ``QSettings`` guarda e lê com ``type=bool``);
- ``float``: número;
- ``json``: texto JSON;
- ``str``: texto.

Leitura: chave ausente, ou valor corrompido / de tipo errado, cai no padrão.

Passo 2 (etapa 2 da migração, ainda não feito): um ``Store`` em ``settings.json`` próprio,
com migração única do Registro, para a interface clássica e a nova lerem o mesmo arquivo.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Generic, Protocol, TypeVar

T = TypeVar("T")

UI_MODES = ("classic", "web")  # interface clássica (Qt) e nova (web)
UI_LANGUAGES = ("pt_BR", "en_US", "es_ES", "fr_FR")  # os mesmos de i18n.LANGUAGES (que importa o Qt)

_MISSING: Any = object()


class Store(Protocol):
    """Onde as preferências moram. ``get`` devolve None quando a chave não existe."""

    def get(self, key: str) -> object | None: ...

    def set(self, key: str, value: object) -> None: ...

    def remove(self, key: str) -> None: ...


class MemoryStore:
    """Armazenamento em memória (testes, ou uma interface sem persistência)."""

    def __init__(self, values: dict[str, object] | None = None):
        self.values: dict[str, object] = dict(values or {})

    def get(self, key: str) -> object | None:
        return self.values.get(key)

    def set(self, key: str, value: object) -> None:
        self.values[key] = value

    def remove(self, key: str) -> None:
        self.values.pop(key, None)


@dataclass(frozen=True)
class Key:
    kind: str  # "str", "flag", "bool", "float" ou "json"
    default: Any


KEYS: dict[str, Key] = {
    # Interface
    "language": Key("str", "pt_BR"),
    "ui_mode": Key("str", "classic"),  # "classic" (Qt) ou "web" (nova, beta); vale ao reiniciar
    "navigation_style": Key("str", "corel"),
    "text_mode": Key("str", "off"),
    "tree_hidden_columns": Key("str", "2"),  # colunas da árvore de elementos, "0,2"
    "files_section_order": Key("str", ""),  # "layers,changed,all"; vazio = ordem padrão
    "files_section_heights": Key("str", "{}"),  # JSON {"layers": 150}; lido por file_list
    "brand_seen": Key("bool", False),
    "web_layout": Key("json", {}),  # interface nova: larguras dos painéis etc. {"left": 310, "right": 320}
    "web_theme": Key("str", "dark"),  # interface nova: tema (data-theme)
    # Projeto e jogo
    "last_project": Key("str", ""),
    "game_dir": Key("str", ""),
    "game_resolution": Key("str", "game"),  # "game", "off" ou "1920x1080"
    "game_background": Key("str", ""),
    "background_mode": Key("str", "builtin"),  # o app passa "custom" como padrão se há fundo próprio
    # Confirmações e envio
    "publish_on_save": Key("flag", False),
    "publish_confirmed": Key("flag", False),
    "offer_project_on_open": Key("flag", True),
    # Atualizações
    "auto_update_check": Key("flag", True),
    "beta_updates": Key("flag", False),  # o app passa True como padrão numa versão beta
    "last_update_check": Key("float", 0.0),
    "skipped_update_version": Key("str", ""),
    "manifest_seen": Key("json", []),
}

# Chaves com sufixo: "last_file/<pasta do projeto>", "root_mode/<arquivo>".
PREFIXES: dict[str, Key] = {
    "last_file": Key("str", ""),
    "root_mode": Key("str", "auto"),
}


def _declared(name: str) -> Key:
    prefix, slash, _suffix = name.partition("/")
    if slash:
        return PREFIXES[prefix]
    return KEYS[name]


def _read(kind: str, raw: object, default: Any) -> Any:
    if raw is None:
        return default
    if kind == "str":
        return str(raw)
    if kind == "flag":
        if raw == "true" or raw is True:
            return True
        if raw == "false" or raw is False:
            return False
        return default
    if kind == "bool":
        # Mesma conversão do QSettings com type=bool.
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            return raw.strip().lower() not in ("", "0", "false")
        if isinstance(raw, (int, float)):
            return raw != 0
        return default
    if kind == "float":
        try:
            return float(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return default
    if kind == "json":
        try:
            value = json.loads(str(raw))
        except ValueError:
            return default
        return value if isinstance(value, type(default)) else default
    raise ValueError(f"tipo desconhecido: {kind}")


def _write(kind: str, value: Any) -> object:
    if kind == "flag":
        return "true" if value else "false"
    if kind == "bool":
        return bool(value)
    if kind == "float":
        return float(value)
    if kind == "json":
        return json.dumps(value)
    return str(value)


class _Field(Generic[T]):
    """Acesso tipado a uma chave sem sufixo: ``prefs.publish_on_save = True``."""

    def __init__(self, name: str):
        self.name = name

    def __get__(self, obj: "Preferences", owner: type | None = None) -> T:
        return obj.get(self.name)

    def __set__(self, obj: "Preferences", value: T) -> None:
        obj.set(self.name, value)


class Preferences:
    def __init__(self, store: Store):
        self.store = store

    # ---- acesso genérico ---------------------------------------------------------------
    def get(self, name: str, default: Any = _MISSING) -> Any:
        """Valor tipado; ``default`` troca o padrão declarado (quando depende do contexto)."""
        key = _declared(name)
        return _read(key.kind, self.store.get(name), key.default if default is _MISSING else default)

    def set(self, name: str, value: Any) -> None:
        self.store.set(name, _write(_declared(name).kind, value))

    def remove(self, name: str) -> None:
        _declared(name)
        self.store.remove(name)

    # ---- chaves sem sufixo -------------------------------------------------------------
    language: _Field[str] = _Field("language")
    ui_mode: _Field[str] = _Field("ui_mode")
    navigation_style: _Field[str] = _Field("navigation_style")
    text_mode: _Field[str] = _Field("text_mode")
    files_section_order: _Field[str] = _Field("files_section_order")
    files_section_heights: _Field[str] = _Field("files_section_heights")
    brand_seen: _Field[bool] = _Field("brand_seen")
    last_project: _Field[str] = _Field("last_project")
    game_dir: _Field[str] = _Field("game_dir")
    game_resolution: _Field[str] = _Field("game_resolution")
    game_background: _Field[str] = _Field("game_background")
    background_mode: _Field[str] = _Field("background_mode")
    publish_on_save: _Field[bool] = _Field("publish_on_save")
    publish_confirmed: _Field[bool] = _Field("publish_confirmed")
    offer_project_on_open: _Field[bool] = _Field("offer_project_on_open")
    auto_update_check: _Field[bool] = _Field("auto_update_check")
    beta_updates: _Field[bool] = _Field("beta_updates")
    last_update_check: _Field[float] = _Field("last_update_check")
    skipped_update_version: _Field[str] = _Field("skipped_update_version")

    @property
    def tree_hidden_columns(self) -> list[str]:
        return self.get("tree_hidden_columns").split(",")

    @tree_hidden_columns.setter
    def tree_hidden_columns(self, columns: list[str]) -> None:
        self.set("tree_hidden_columns", ",".join(columns))

    @property
    def manifest_seen(self) -> set[str]:
        """IDs dos avisos do manifesto remoto já mostrados."""
        return {item for item in self.get("manifest_seen") if isinstance(item, str)}

    @manifest_seen.setter
    def manifest_seen(self, ids: set[str]) -> None:
        self.set("manifest_seen", sorted(ids))

    # ---- chaves com sufixo -------------------------------------------------------------
    def last_file(self, folder: str) -> str:
        """Último XML aberto no projeto que publica em ``folder`` (relativo a ui/)."""
        return self.get(f"last_file/{folder}")

    def set_last_file(self, folder: str, relative: str) -> None:
        self.set(f"last_file/{folder}", relative)

    def remove_last_file(self, folder: str) -> None:
        self.remove(f"last_file/{folder}")

    def move_last_file(self, old_folder: str, new_folder: str) -> None:
        """O projeto passou a publicar em outra pasta (renomeado): o último XML vai junto."""
        last = self.last_file(old_folder)
        if last and old_folder != new_folder:
            self.set_last_file(new_folder, last)
            self.remove_last_file(old_folder)

    def root_mode(self, xml_name: str) -> str:
        """Como a raiz de um XML solto é posicionada ("auto" ou o modo escolhido)."""
        return self.get(f"root_mode/{xml_name}")

    def set_root_mode(self, xml_name: str, mode: str) -> None:
        self.set(f"root_mode/{xml_name}", mode)
