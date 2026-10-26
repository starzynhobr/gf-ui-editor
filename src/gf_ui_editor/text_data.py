"""Textos do jogo em data/Translate: leitura, busca e edição sem estragar o arquivo.

Cada arquivo é uma sequência de registros ``ID|campo|campo|``; um campo pode quebrar
linha (descrições do T_Item.ini), então o registro vai até a próxima linha que começa
com ``número|``. As edições trocam só o trecho do registro e regravam na codificação
original, com as mesmas quebras de linha.

O launcher baixa estes arquivos de novo ao atualizar ou trocar o idioma
(GameDataFileListT.txt guarda o CRC de cada um), então o projeto guarda só as
mudanças (arquivo -> ID -> campos, no project.db) e as reaplica ao enviar para o jogo.
"""

from __future__ import annotations

import bisect
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import storage

TRANSLATE_DIR = Path("data") / "Translate"
GAME_ENCODING = "cp1252"
_RECORD_START = re.compile(r"(?m)^(\d+)\|")


@dataclass
class TextRecord:
    record_id: str
    start: int  # posição do ID no texto do arquivo
    end: int  # fim do registro, antes da quebra de linha final
    fields: list[str]


@dataclass
class TextFile:
    path: Path
    encoding: str
    text: str
    records: list[TextRecord]
    by_id: dict[str, TextRecord] = field(default_factory=dict)
    _lowered: str = ""
    _starts: list[int] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.path.name

    @classmethod
    def load(cls, path: Path) -> "TextFile":
        # O cliente lê estes arquivos na página de código do Windows (cp1252): os acentos
        # de T_Item, T_TextIndex etc. estão nela. Bytes sem caractere voltam iguais ao gravar.
        encoding = GAME_ENCODING
        text = path.read_bytes().decode(encoding, "surrogateescape")
        records = parse_records(text)
        loaded = cls(path, encoding, text, records)
        for record in records:
            loaded.by_id.setdefault(record.record_id, record)
        loaded._lowered = text.lower()
        loaded._starts = [record.start for record in records]
        return loaded

    def find(self, needle: str) -> list[TextRecord]:
        """Registros cujo texto contém `needle` (sem diferenciar maiúsculas)."""
        found: list[TextRecord] = []
        needle = needle.lower()
        position = self._lowered.find(needle)
        while position != -1:
            slot = bisect.bisect_right(self._starts, position) - 1
            if slot >= 0:
                record = self.records[slot]
                if position >= record.start + len(record.record_id) + 1:  # achou nos campos, não no ID
                    found.append(record)
                    position = self._lowered.find(needle, record.end)
                    continue
            position = self._lowered.find(needle, position + 1)
        return found


def parse_records(text: str) -> list[TextRecord]:
    matches = list(_RECORD_START.finditer(text))
    records: list[TextRecord] = []
    for number, match in enumerate(matches):
        start = match.start()
        end = matches[number + 1].start() if number + 1 < len(matches) else len(text)
        while end > start and text[end - 1] in "\r\n":
            end -= 1
        body = text[match.end():end]
        fields = body.split("|")
        if fields and fields[-1] == "":
            fields.pop()
        records.append(TextRecord(match.group(1), start, end, fields))
    return records


def record_text(record_id: str, fields: list[str]) -> str:
    return record_id + "|" + "".join(value + "|" for value in fields)


def apply_edits(text_file: TextFile, edits: dict[str, list[str]]) -> tuple[bytes, list[str]]:
    """Novo conteúdo do arquivo com as edições; devolve também os IDs que não existem mais."""
    pieces: list[str] = []
    cursor = 0
    missing = [record_id for record_id in edits if record_id not in text_file.by_id]
    for record in text_file.records:
        fields = edits.get(record.record_id)
        if fields is None or text_file.by_id.get(record.record_id) is not record:
            continue
        pieces.append(text_file.text[cursor:record.start])
        pieces.append(record_text(record.record_id, fields))
        cursor = record.end
    pieces.append(text_file.text[cursor:])
    return "".join(pieces).encode(text_file.encoding, "surrogateescape"), missing


def translate_files(game_dir: Path) -> list[Path]:
    """Arquivos de texto em uso: ignora cópias como T_Item.before-algo.ini."""
    folder = game_dir / TRANSLATE_DIR
    if not folder.is_dir():
        return []
    return sorted(path for path in folder.glob("*.ini") if path.name.count(".") == 1)


@dataclass
class TextEdit:
    fields: list[str]
    original: list[str]  # campos do jogo quando a edição foi feita, para notar se mudaram


def load_edits(project_root: Path) -> dict[str, dict[str, TextEdit]]:
    """Edições guardadas no project.db do projeto."""
    if not (project_root / storage.PROJECT_DB).is_file():
        return {}
    return {
        name: {record_id: TextEdit(fields, original) for record_id, (fields, original) in records.items()}
        for name, records in storage.ProjectStore(project_root).text_edits().items()
    }


def save_edits(project_root: Path, edits: dict[str, dict[str, TextEdit]]) -> None:
    storage.ProjectStore(project_root).replace_text_edits({
        name: {record_id: (edit.fields, edit.original) for record_id, edit in records.items()}
        for name, records in edits.items() if records
    })


def sync_text_index(game_dir: Path, projects_root: Path) -> int:
    """Atualiza o índice de busca (banco compartilhado) com os arquivos que mudaram.

    Só relê os arquivos cuja data ou tamanho mudou desde a última vez (o launcher troca
    arquivos ao atualizar ou mudar o idioma). Devolve quantos arquivos foram reindexados.
    """
    store = storage.TextIndexStore(projects_root)
    indexed = store.indexed_files(game_dir)
    current: dict[str, tuple[int, int]] = {}
    for path in translate_files(game_dir):
        stat = path.stat()
        current[path.name] = (stat.st_mtime_ns, stat.st_size)
    rebuilt = 0
    for name, signature in current.items():
        if indexed.get(name) == signature:
            continue
        text_file = TextFile.load(game_dir / TRANSLATE_DIR / name)
        store.replace_file(game_dir, name, signature, ((record.record_id, record.fields) for record in text_file.records))
        rebuilt += 1
    for name in set(indexed) - set(current):
        store.replace_file(game_dir, name, None, ())
    return rebuilt


def history_baseline(project_root: Path) -> dict[str, TextFile]:
    """Arquivos do jogo como estavam antes do primeiro envio (backup mais antigo de cada um).

    Cada envio guarda em .history/data/<data-hora> o arquivo do jogo de antes de aplicar as
    edições; o mais antigo de cada arquivo tem o texto original, mesmo que a edição tenha
    sido desfeita no meio do caminho.
    """
    folder = project_root / ".history" / "data"
    baseline: dict[str, TextFile] = {}
    if not folder.is_dir():
        return baseline
    for snapshot in sorted(path for path in folder.iterdir() if path.is_dir()):
        for candidate in snapshot.glob("*.ini"):
            if candidate.name not in baseline:
                baseline[candidate.name] = TextFile.load(candidate)
    return baseline


def history_original(project_root: Path, file_name: str, record_id: str) -> list[str] | None:
    """Campos do registro no backup mais antigo em .history/data, se houver."""
    text_file = history_baseline(project_root).get(file_name)
    record = text_file.by_id.get(record_id) if text_file is not None else None
    return list(record.fields) if record is not None else None


def publish_edits(
    game_dir: Path, edits: dict[str, dict[str, TextEdit]], backup_dir: Path | None = None
) -> tuple[int, list[str]]:
    """Grava as edições nos arquivos do jogo. Devolve (arquivos alterados, avisos)."""
    changed = 0
    warnings: list[str] = []
    for name, records in edits.items():
        if not records:
            continue
        path = game_dir / TRANSLATE_DIR / name
        if not path.is_file():
            warnings.append(name)
            continue
        text_file = TextFile.load(path)
        content, missing = apply_edits(text_file, {record_id: edit.fields for record_id, edit in records.items()})
        warnings.extend(f"{name} #{record_id}" for record_id in missing)
        if content == path.read_bytes():
            continue
        if backup_dir is not None:
            backup_dir.mkdir(parents=True, exist_ok=True)
            (backup_dir / name).write_bytes(path.read_bytes())
        path.write_bytes(content)
        changed += 1
    return changed, warnings
