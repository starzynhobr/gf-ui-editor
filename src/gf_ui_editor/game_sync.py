"""Pasta UI do jogo x projeto: proteção do F5 e "Puxar arquivos da pasta do jogo".

Proteção do F5 (sem atrito: nunca pergunta nem bloqueia). O editor guarda o CRC de cada
arquivo que escreveu na pasta UI (`<pasta de projetos>/.sent-to-game.json`, por pasta do jogo,
para valer entre projetos). Antes de sobrescrever um arquivo da pasta UI, ele é considerado
"editado fora" quando não é o oficial, não é o que o editor mandou da última vez e não é
cópia de nenhuma UI de UICustom (o launcher aplica UIs copiando por cima). Só esses ganham
uma cópia no `.history` do projeto antes de serem substituídos.

Puxar: compara uma pasta (UI do jogo ou uma UI de UICustom) com o projeto e lista o que
difere; a pessoa marca o que quer trazer. O que é substituído no projeto vai para o `.history`.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path

from . import gamedata
from . import project as project_module

SENT_FILE = ".sent-to-game.json"
GAME_BACKUP_TAG = "jogo"  # sufixo das cópias que o F5 guarda no .history

# Por que o arquivo da pasta difere do projeto (para a lista do Puxar).
EDITED_OUTSIDE = "edited"  # não é oficial, nem o que o editor mandou, nem de outra UI
OFFICIAL = "official"  # é o arquivo oficial do jogo (puxar desfaz o que o projeto mudou)
FROM_UI = "ui"  # igual ao de uma UI de UICustom (aplicada pelo launcher)
SENT = "sent"  # o editor mandou (de outro projeto, ou antes de mudar este)
UNKNOWN = "unknown"  # sem lista oficial para saber


@dataclass(frozen=True)
class PullCandidate:
    relative: str  # caminho relativo a ui/, com "/"
    source: Path  # arquivo de onde viria
    new: bool  # não existe no projeto
    origin: str  # EDITED_OUTSIDE, OFFICIAL, FROM_UI, SENT ou UNKNOWN
    origin_ui: str = ""  # nome da UI de UICustom quando origin == FROM_UI


# ---- registro do que o editor escreveu na pasta UI ---------------------------------------
def _sent_path() -> Path:
    return project_module.PROJECTS_ROOT / SENT_FILE


def _game_key(game_dir: Path) -> str:
    return os.path.normcase(os.path.abspath(game_dir))


def _read_all() -> dict:
    try:
        data = json.loads(_sent_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def load_sent(game_dir: Path) -> dict[str, str]:
    """Caminho relativo a UI/ em minúsculas -> CRC do que o editor escreveu por último."""
    entries = _read_all().get(_game_key(game_dir))
    return {str(key): str(value) for key, value in entries.items()} if isinstance(entries, dict) else {}


def remember_sent(game_dir: Path, entries: dict[str, str]) -> None:
    if not entries:
        return
    data = _read_all()
    current = data.get(_game_key(game_dir))
    current = current if isinstance(current, dict) else {}
    current.update(entries)
    data[_game_key(game_dir)] = current
    path = _sent_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, path)
    except OSError:
        pass  # sem o registro a proteção só fica mais cautelosa (guarda cópia a mais)


# ---- de onde veio um arquivo da pasta UI ---------------------------------------------------
def _matching_custom_ui(game_dir: Path, relative: str, path: Path) -> str:
    """Nome da UI de UICustom que tem este mesmo arquivo (mesmo conteúdo), ou ""."""
    custom_root = game_dir / "UICustom"
    try:
        folders = [item for item in custom_root.iterdir() if item.is_dir()]
        size = path.stat().st_size
    except OSError:
        return ""
    crc = None
    for folder in sorted(folders, key=lambda item: item.name.lower()):
        candidate = folder / relative
        try:
            if not candidate.is_file() or candidate.stat().st_size != size:
                continue
            crc = crc or gamedata.file_crc(path)
            if gamedata.file_crc(candidate) == crc:
                return folder.name
        except OSError:
            continue
    return ""


def origin_of(game_dir: Path, relative: str, path: Path, official: dict, sent: dict[str, str]) -> tuple[str, str]:
    """(origem, nome da UI) de um arquivo que está na pasta do jogo."""
    key = relative.lower()
    if official and gamedata.is_official(path, relative, official):
        return OFFICIAL, ""
    try:
        if key in sent and gamedata.file_crc(path) == sent[key]:
            return SENT, ""
    except OSError:
        return UNKNOWN, ""
    ui = _matching_custom_ui(game_dir, relative, path)
    if ui:
        return FROM_UI, ui
    # Sem lista oficial e sem registro do editor não há como saber: não acusa.
    return (EDITED_OUTSIDE if official or key in sent else UNKNOWN), ""


def edited_outside(game_dir: Path, relative: str, path: Path, official: dict, sent: dict[str, str]) -> bool:
    """O arquivo da pasta UI foi mexido fora do editor (e não dá para recuperar de outro lugar)?"""
    return origin_of(game_dir, relative, path, official, sent)[0] == EDITED_OUTSIDE


def game_backup_path(project: "project_module.Project", file_path: Path) -> Path:
    """Destino no .history da cópia de um arquivo da pasta do jogo (marcada com "-jogo")."""
    plain = project.history_path_for(file_path)
    target = plain.with_name(f"{plain.stem}-{GAME_BACKUP_TAG}{plain.suffix}")
    number = 2
    while target.exists():
        target = plain.with_name(f"{plain.stem}-{GAME_BACKUP_TAG}-{number}{plain.suffix}")
        number += 1
    return target


# ---- Puxar ------------------------------------------------------------------------------
def pull_sources(game_dir: Path) -> list[tuple[str, Path]]:
    """Pastas de onde dá para puxar: a pasta UI do jogo e cada UI de UICustom."""
    sources = [("UI", game_dir / "UI")] if (game_dir / "UI").is_dir() else []
    custom_root = game_dir / "UICustom"
    if custom_root.is_dir():
        for folder in sorted((item for item in custom_root.iterdir() if item.is_dir()), key=lambda item: item.name.lower()):
            sources.append((f"UICustom/{folder.name}", folder))
    return sources


def _same(a: Path, b: Path) -> bool:
    try:
        if a.stat().st_size != b.stat().st_size:
            return False
        return gamedata.file_crc(a) == gamedata.file_crc(b)
    except OSError:
        return False


def compare(project: "project_module.Project", source_dir: Path, progress=None) -> list[PullCandidate]:
    """Arquivos de `source_dir` que diferem do projeto (ou que o projeto não tem).

    Os editados fora vêm primeiro; depois os de outras UIs, os enviados e os oficiais.
    """
    game_dir = project.game_dir
    official = gamedata.official_ui_files(game_dir) if game_dir is not None else {}
    sent = load_sent(game_dir) if game_dir is not None else {}
    is_game_ui = game_dir is not None and _game_key(source_dir) == _game_key(game_dir / "UI")
    files = []
    for folder, dirs, names in os.walk(source_dir):
        dirs[:] = [name for name in dirs if not name.startswith(".")]
        for name in names:
            if name.startswith(".") or project_module.is_backup_file(name):
                continue
            files.append(Path(folder, name))
    result = []
    for done, path in enumerate(files, 1):
        relative = path.relative_to(source_dir).as_posix()
        target = project.resolve(relative)
        if progress is not None:
            progress(done, len(files))
        exists = target.is_file()
        if exists and _same(path, target):
            continue
        if is_game_ui:
            origin, ui = origin_of(game_dir, relative, path, official, sent)
        else:
            origin, ui = (OFFICIAL, "") if official and gamedata.is_official(path, relative, official) else (FROM_UI, source_dir.name)
        # Arquivo novo e oficial (ex.: o projeto não leva ícones): não é novidade para puxar.
        if not exists and origin == OFFICIAL:
            continue
        result.append(PullCandidate(relative, path, not exists, origin, ui))
    order = {EDITED_OUTSIDE: 0, UNKNOWN: 1, FROM_UI: 2, SENT: 3, OFFICIAL: 4}
    return sorted(result, key=lambda item: (order.get(item.origin, 9), item.relative.lower()))


def pull(project: "project_module.Project", items: list[tuple[str, Path]]) -> int:
    """Traz para o projeto cada (relativo, origem). O que é substituído vai para o .history."""
    project.invalidate_changes()
    count = 0
    for relative, source in items:
        if _same(source, project.resolve(relative)):
            continue
        project.write_from(relative, source)
        count += 1
    project.files(refresh=True)
    return count


__all__ = [
    "EDITED_OUTSIDE", "FROM_UI", "OFFICIAL", "PullCandidate", "SENT", "UNKNOWN", "compare",
    "edited_outside", "game_backup_path", "load_sent", "origin_of", "pull", "pull_sources", "remember_sent",
]
