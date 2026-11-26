"""Aviso de atualização dos textos do jogo (data/Translate), sem Qt.

O launcher baixa os `.ini` de novo quando o jogo atualiza ou troca de idioma. O
`GameDataFileListT.txt` guarda o CRC oficial de cada arquivo; quando esses CRCs mudam,
houve atualização. Este serviço:

1. guarda um retrato dos textos oficiais (conteúdo por CRC, comprimido) e, por jogo, qual
   lista de CRCs o usuário já viu (`<projetos>/.official-texts/`);
2. ao notar CRCs novos, compara o retrato anterior com o arquivo novo: IDs novos, textos
   oficiais alterados e IDs que sumiram (ignorando CRLF/LF);
3. diz o que isso faz com as edições de um projeto: edições que o jogo desfez (o arquivo
   voltou ao oficial; o próximo F5 regrava — "Reenviar edições") e edições cujo texto
   oficial mudou por baixo (o original guardado na edição não é mais o do jogo).

Um arquivo só entra no retrato quando o conteúdo atual bate com o CRC oficial: depois de
um F5 o arquivo do jogo tem as edições do projeto e não serve de referência.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import gzip
import json
import os
from pathlib import Path
import zlib

from .text_data import GAME_ENCODING, TRANSLATE_DIR, TextEdit, TextFile

FILE_LIST_T = "GameDataFileListT.txt"
CACHE_FOLDER = ".official-texts"
STATE_FILE = "seen.json"


def _crc(data: bytes) -> str:
    return f"{zlib.crc32(data) & 0xFFFFFFFF:08X}"


def official_crcs(game_dir: Path) -> dict[str, str]:
    """Nome do .ini -> CRC oficial, do GameDataFileListT.txt. {} se não houver lista."""
    path = game_dir / FILE_LIST_T
    try:
        lines = path.read_text(encoding="latin-1").splitlines()
    except OSError:
        return {}
    result: dict[str, str] = {}
    for line in lines:
        parts = line.strip().split("|")
        if len(parts) >= 3 and parts[0].lower().endswith(".ini") and parts[2]:
            result[Path(parts[0].replace("\\", "/")).name] = parts[2].upper()
    return result


def _normalized(fields: list[str]) -> list[str]:
    return [value.replace("\r\n", "\n") for value in fields]


@dataclass
class FileTextChanges:
    name: str
    new_ids: list[str] = field(default_factory=list)
    removed_ids: list[str] = field(default_factory=list)
    changed: list[tuple[str, list[str], list[str]]] = field(default_factory=list)  # (id, antes, agora)

    @property
    def empty(self) -> bool:
        return not (self.new_ids or self.removed_ids or self.changed)


@dataclass
class TextUpdate:
    """CRCs oficiais mudaram desde o último retrato visto."""

    changed_files: list[str]  # .ini com CRC oficial diferente (ou novos na lista)
    files: list[FileTextChanges]  # comparação por ID, quando há retrato anterior e o novo é oficial
    unavailable: list[str]  # mudaram, mas sem retrato anterior ou o arquivo atual não é o oficial

    @property
    def new_ids(self) -> int:
        return sum(len(item.new_ids) for item in self.files)

    @property
    def changed_texts(self) -> int:
        return sum(len(item.changed) for item in self.files)


@dataclass
class ProjectImpact:
    reverted: list[tuple[str, str]] = field(default_factory=list)  # (arquivo, id): jogo voltou ao oficial
    official_changed: list[tuple[str, str, list[str], list[str]]] = field(default_factory=list)
    # (arquivo, id, original guardado na edição, oficial agora)
    missing: list[tuple[str, str]] = field(default_factory=list)  # IDs editados que sumiram do jogo


class TextSnapshots:
    """Retratos dos textos oficiais, compartilhados entre projetos (como `.official-ui`)."""

    def __init__(self, projects_root: Path):
        self.folder = projects_root / CACHE_FOLDER

    # ---- conteúdo por CRC ------------------------------------------------------------
    def _blob(self, name: str, crc: str) -> Path:
        return self.folder / f"{Path(name).stem}-{crc}.ini.gz"

    def has(self, name: str, crc: str) -> bool:
        return self._blob(name, crc).is_file()

    def store(self, name: str, crc: str, data: bytes) -> None:
        target = self._blob(name, crc)
        if target.is_file():
            return
        self.folder.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        temporary.write_bytes(gzip.compress(data, compresslevel=6))
        os.replace(temporary, target)

    def load(self, name: str, crc: str) -> TextFile | None:
        blob = self._blob(name, crc)
        try:
            data = gzip.decompress(blob.read_bytes())
        except (OSError, EOFError, gzip.BadGzipFile):
            return None
        return TextFile.from_text(Path(name), GAME_ENCODING, data.decode(GAME_ENCODING, "surrogateescape"))

    # ---- lista vista por jogo ------------------------------------------------------------
    def _state(self) -> dict[str, dict[str, str]]:
        try:
            data = json.loads((self.folder / STATE_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def seen(self, game_dir: Path) -> dict[str, str] | None:
        value = self._state().get(os.path.normcase(str(game_dir)))
        return {str(k): str(v) for k, v in value.items()} if isinstance(value, dict) else None

    def mark_seen(self, game_dir: Path, crcs: dict[str, str]) -> None:
        state = self._state()
        state[os.path.normcase(str(game_dir))] = dict(crcs)
        self.folder.mkdir(parents=True, exist_ok=True)
        temporary = self.folder / (STATE_FILE + ".tmp")
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(temporary, self.folder / STATE_FILE)

    def capture(self, game_dir: Path, crcs: dict[str, str]) -> int:
        """Guarda os arquivos atuais que batem com o CRC oficial. Devolve quantos novos."""
        stored = 0
        for name, crc in crcs.items():
            if self.has(name, crc):
                continue
            path = game_dir / TRANSLATE_DIR / name
            try:
                data = path.read_bytes()
            except OSError:
                continue
            if _crc(data) == crc:
                self.store(name, crc, data)
                stored += 1
        return stored


def compare_files(name: str, before: TextFile, after: TextFile) -> FileTextChanges:
    """IDs novos, sumidos e com texto diferente (a menos de CRLF/LF)."""
    changes = FileTextChanges(name)
    for record_id, record in after.by_id.items():
        old = before.by_id.get(record_id)
        if old is None:
            changes.new_ids.append(record_id)
        elif _normalized(old.fields) != _normalized(record.fields):
            changes.changed.append((record_id, list(old.fields), list(record.fields)))
    changes.removed_ids = [record_id for record_id in before.by_id if record_id not in after.by_id]
    return changes


def check(game_dir: Path, projects_root: Path) -> TextUpdate | None:
    """Houve atualização dos textos desde o último retrato visto? None se não (ou se é a
    primeira vez: aí só guarda o retrato inicial e marca como visto)."""
    crcs = official_crcs(game_dir)
    if not crcs:
        return None
    snapshots = TextSnapshots(projects_root)
    seen = snapshots.seen(game_dir)
    snapshots.capture(game_dir, crcs)
    if seen is None:
        snapshots.mark_seen(game_dir, crcs)
        return None
    changed = sorted(name for name, crc in crcs.items() if seen.get(name) != crc)
    if not changed:
        return None
    files: list[FileTextChanges] = []
    unavailable: list[str] = []
    for name in changed:
        old_crc, new_crc = seen.get(name), crcs[name]
        before = snapshots.load(name, old_crc) if old_crc else TextFile.from_text(Path(name), GAME_ENCODING, "")
        after = snapshots.load(name, new_crc)
        if before is None or after is None:
            unavailable.append(name)
            continue
        result = compare_files(name, before, after)
        if not result.empty:
            files.append(result)
    return TextUpdate(changed, files, unavailable)


def acknowledge(game_dir: Path, projects_root: Path) -> None:
    """O usuário viu o aviso: a lista atual passa a ser a referência."""
    crcs = official_crcs(game_dir)
    if crcs:
        snapshots = TextSnapshots(projects_root)
        snapshots.capture(game_dir, crcs)
        snapshots.mark_seen(game_dir, crcs)


def project_impact(game_dir: Path, edits: dict[str, dict[str, TextEdit]]) -> ProjectImpact:
    """O que a situação atual do jogo faz com as edições de um projeto.

    - reverted: o arquivo do jogo tem o texto oficial no lugar da edição (o launcher
      baixou de novo); o próximo envio (F5) regrava.
    - official_changed: o texto oficial agora não é mais o original guardado na edição
      (a atualização mudou o texto por baixo da edição; vale revisar antes de reenviar).
    - missing: o ID editado não existe mais no jogo.
    """
    impact = ProjectImpact()
    official = official_crcs(game_dir)
    for name, records in sorted(edits.items()):
        if not records:
            continue
        path = game_dir / TRANSLATE_DIR / name
        try:
            data = path.read_bytes()
        except OSError:
            impact.missing.extend((name, record_id) for record_id in records)
            continue
        current = TextFile.from_text(path, GAME_ENCODING, data.decode(GAME_ENCODING, "surrogateescape"))
        is_official = official.get(name) == _crc(data)
        for record_id, edit in records.items():
            record = current.by_id.get(record_id)
            if record is None:
                impact.missing.append((name, record_id))
                continue
            game_fields = _normalized(record.fields)
            if is_official and game_fields != _normalized(edit.fields):
                impact.reverted.append((name, record_id))
            if is_official and edit.original and game_fields != _normalized(edit.original):
                impact.official_changed.append((name, record_id, list(edit.original), list(record.fields)))
    return impact


__all__ = [
    "FileTextChanges",
    "ProjectImpact",
    "TextSnapshots",
    "TextUpdate",
    "acknowledge",
    "check",
    "compare_files",
    "official_crcs",
    "project_impact",
]
