"""Manifesto remoto: avisos e ajustes que mudam sem lançar uma versão nova.

O editor lê ao abrir um JSON pequeno no repositório (`app-manifest.json`, branch main).
Editar esse arquivo e dar push basta para, em todas as instalações a partir da 0.6.0:

- mostrar avisos (uma vez cada), filtrados por versão, canal e data;
- pedir para atualizar quem está abaixo de uma versão mínima;
- desligar uma função que deu problema, até sair a correção.

Sem internet, arquivo ausente ou inválido: nada acontece. Campos desconhecidos são
ignorados, então versões antigas convivem com manifestos mais novos.

Formato (versão 1):

    {
      "schema": 1,
      "min_version": "0.5.0",
      "disabled_features": ["export_texts"],
      "messages": [
        {
          "id": "2026-11-jogo-atualizou",
          "level": "info",
          "text": {"pt_BR": "…", "en_US": "…", "es_ES": "…", "fr_FR": "…"},
          "url": "https://stzlabs.com/…",      (só stzlabs.com, github.com/starzynhobr, Discord)
          "min_version": "0.6.0", "max_version": "0.6.9",
          "channel": "all",
          "until": "2026-12-31"
        }
      ]
    }
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import json
import urllib.parse
import urllib.request

from . import __version__
from .updater import REPOSITORY, parse_version

MANIFEST_URL = f"https://raw.githubusercontent.com/{REPOSITORY}/main/app-manifest.json"
SCHEMA = 1
SIZE_LIMIT = 64_000
TIMEOUT_SECONDS = 8
LEVELS = ("info", "warning")
CHANNELS = ("all", "stable", "beta")

# Links que um aviso pode abrir: só os canais oficiais. Mesmo que alguém altere o
# manifesto indevidamente, o botão não leva para um site qualquer.
ALLOWED_LINKS = (
    ("stzlabs.com", ""),
    ("www.stzlabs.com", ""),
    ("github.com", "/starzynhobr/"),
    ("discord.com", "/invite/"),
    ("discord.gg", "/"),
)


def allowed_link(url: str | None) -> str | None:
    """O próprio link se for https para um dos canais oficiais; senão None."""
    if not url:
        return None
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return None
    if parts.scheme != "https" or parts.username or parts.password or parts.port:
        return None
    host = (parts.hostname or "").lower()
    path = parts.path or "/"
    if any(host == allowed and path.startswith(prefix) for allowed, prefix in ALLOWED_LINKS):
        return url
    return None


# Funções que o manifesto pode desligar (nomes estáveis: o manifesto os cita).
EXPORT_TEXTS = "export_texts"
PUBLISH_TEXTS = "publish_texts"


@dataclass(frozen=True)
class Message:
    id: str
    texts: dict[str, str]
    level: str = "info"
    url: str | None = None
    min_version: str | None = None
    max_version: str | None = None
    channel: str = "all"
    until: date | None = None

    def text(self, language: str) -> str:
        """Texto no idioma da interface; senão português, inglês ou o primeiro que houver."""
        for code in (language, "pt_BR", "en_US"):
            if self.texts.get(code):
                return self.texts[code]
        return next(iter(self.texts.values()), "")


@dataclass(frozen=True)
class Manifest:
    min_version: str | None = None
    messages: tuple[Message, ...] = ()
    disabled_features: frozenset[str] = field(default_factory=frozenset)

    def needs_update(self, version: str = __version__) -> bool:
        return self.min_version is not None and parse_version(version) < parse_version(self.min_version)

    def is_disabled(self, feature: str) -> bool:
        return feature in self.disabled_features

    def messages_for(
        self, version: str = __version__, beta: bool = False, today: date | None = None, seen: set[str] | frozenset[str] = frozenset()
    ) -> list[Message]:
        """Avisos que valem para esta instalação e ainda não foram mostrados."""
        today = today or date.today()
        key = parse_version(version)
        result = []
        for message in self.messages:
            if message.id in seen:
                continue
            if message.until is not None and today > message.until:
                continue
            if message.channel == "beta" and not beta or message.channel == "stable" and beta:
                continue
            if message.min_version and key < parse_version(message.min_version):
                continue
            if message.max_version and key > parse_version(message.max_version):
                continue
            result.append(message)
        return result


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _message(data: object) -> Message | None:
    if not isinstance(data, dict):
        return None
    message_id = _text(data.get("id"))
    raw_texts = data.get("text")
    if isinstance(raw_texts, str):
        raw_texts = {"pt_BR": raw_texts}
    if message_id is None or not isinstance(raw_texts, dict):
        return None
    texts = {str(code): text for code, value in raw_texts.items() if (text := _text(value))}
    if not texts:
        return None
    url = _text(data.get("url"))
    until = None
    if _text(data.get("until")):
        try:
            until = date.fromisoformat(data["until"].strip())
        except ValueError:
            return None  # data errada: melhor não mostrar do que mostrar para sempre
    level = data.get("level") if data.get("level") in LEVELS else "info"
    channel = data.get("channel") if data.get("channel") in CHANNELS else "all"
    return Message(
        id=message_id,
        texts=texts,
        level=level,
        url=allowed_link(url),
        min_version=_text(data.get("min_version")),
        max_version=_text(data.get("max_version")),
        channel=channel,
        until=until,
    )


def parse(payload: bytes) -> Manifest | None:
    """Manifesto lido do JSON; None se for inválido ou de um formato mais novo que este."""
    try:
        data = json.loads(payload.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        return None
    messages = data.get("messages")
    disabled = data.get("disabled_features")
    return Manifest(
        min_version=_text(data.get("min_version")),
        messages=tuple(
            message for item in (messages if isinstance(messages, list) else []) if (message := _message(item))
        ),
        disabled_features=frozenset(
            item for item in (disabled if isinstance(disabled, list) else []) if isinstance(item, str)
        ),
    )


def fetch(url: str = MANIFEST_URL) -> Manifest | None:
    """Baixa e lê o manifesto; qualquer falha (rede, 404, JSON ruim) devolve None."""
    request = urllib.request.Request(url, headers={"User-Agent": f"gf-ui-editor/{__version__}"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310 - URL fixa em https
            payload = response.read(SIZE_LIMIT + 1)
    except (OSError, ValueError):
        return None
    if len(payload) > SIZE_LIMIT:
        return None
    return parse(payload)
