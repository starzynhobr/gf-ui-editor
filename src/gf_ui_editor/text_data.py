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
from collections import Counter
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
        return cls.from_text(path, encoding, path.read_bytes().decode(encoding, "surrogateescape"))

    @classmethod
    def from_text(cls, path: Path, encoding: str, text: str) -> "TextFile":
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


# Palavras curtas e frequentes de cada idioma que o launcher oferece; bastam para dizer em
# que idioma está um arquivo de texto inteiro.
_LANGUAGE_WORDS = {
    "pt": ("você", "não", "para", "com", "uma", "seu", "sua", "ção", "ões", "do", "da"),
    "en": ("the", "you", "your", "with", "and", "not", "this", "of", "is", "to"),
    "es": ("el", "los", "las", "usted", "tu", "con", "una", "para", "ción", "del"),
    "fr": ("le", "les", "vous", "votre", "avec", "une", "des", "est", "pas", "du"),
    "de": ("der", "die", "das", "und", "nicht", "sie", "mit", "ist", "ein", "zu"),
    "it": ("il", "gli", "della", "con", "una", "non", "per", "è", "di", "che"),
}
_WORD = re.compile(r"[^\W\d_]+")


_LANGUAGE_SAMPLE = 200_000  # caracteres: sobra para decidir, e arquivos de 10 MB não travam
_language_cache: dict[tuple[str, int, int], str | None] = {}


def detect_language(text_file: TextFile) -> str | None:
    """Idioma do arquivo pelas palavras mais comuns; None se não der para dizer."""
    try:
        stat = text_file.path.stat()
        key = (str(text_file.path), stat.st_mtime_ns, stat.st_size)
    except OSError:
        key = None
    if key is not None and key in _language_cache:
        return _language_cache[key]
    sample = (text_file._lowered or text_file.text.lower())[:_LANGUAGE_SAMPLE]
    frequency = Counter(_WORD.findall(sample))
    counts = {}
    for language, words in _LANGUAGE_WORDS.items():
        suffixes = tuple(word for word in words if len(word) == 3 and not word.isascii())
        total = sum(frequency[word] for word in words)
        if suffixes:
            total += sum(count for word, count in frequency.items() if len(word) > 4 and word.endswith(suffixes))
        counts[language] = total
    best = max(counts, key=counts.get)
    ranked = sorted(counts.values(), reverse=True)
    result = best if ranked[0] >= 20 and ranked[0] >= ranked[1] * 1.5 else None
    if key is not None:
        _language_cache[key] = result
    return result


def game_language(game_dir: Path) -> str | None:
    """Idioma escolhido no launcher (Launcher.ini, [Config] Language)."""
    try:
        text = (game_dir / "Launcher.ini").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = re.search(r"(?im)^\s*Language\s*=\s*([a-z]{2})", text)
    return match.group(1).lower() if match else None


def history_baseline(project_root: Path, language: str | None = None) -> dict[str, TextFile]:
    """Arquivos do jogo como estavam antes do primeiro envio (backup mais antigo de cada um).

    Cada envio guarda em .history/data/<data-hora> o arquivo do jogo de antes de aplicar as
    edições; o mais antigo de cada arquivo tem o texto original, mesmo que a edição tenha
    sido desfeita no meio do caminho. Com `language`, pula backups de outro idioma: o
    launcher troca todos os textos ao mudar o idioma, e comparar com eles marcaria tudo.
    """
    folder = project_root / ".history" / "data"
    baseline: dict[str, TextFile] = {}
    if not folder.is_dir():
        return baseline
    for snapshot in sorted(path for path in folder.iterdir() if path.is_dir()):
        for candidate in snapshot.glob("*.ini"):
            if candidate.name in baseline:
                continue
            text_file = TextFile.load(candidate)
            detected = detect_language(text_file) if language else None
            if language and detected and detected != language:
                continue
            baseline[candidate.name] = text_file
    return baseline


def history_original(project_root: Path, file_name: str, record_id: str) -> list[str] | None:
    """Campos do registro no backup mais antigo em .history/data, se houver."""
    text_file = history_baseline(project_root).get(file_name)
    record = text_file.by_id.get(record_id) if text_file is not None else None
    return list(record.fields) if record is not None else None


@dataclass
class TextImport:
    """O que importar de uma pasta com T_*.ini já alterados, comparado ID a ID com o jogo."""

    edits: dict[str, dict[str, TextEdit]] = field(default_factory=dict)  # só o que muda no projeto
    replaced: int = 0  # já havia outra edição guardada para o ID
    missing_ids: int = 0  # IDs que o jogo não tem mais
    unsupported: int = 0  # texto com caractere fora da página de código do jogo
    unknown_files: list[str] = field(default_factory=list)  # arquivos que o jogo não tem

    @property
    def count(self) -> int:
        return sum(len(records) for records in self.edits.values())


def import_source_folder(folder: Path) -> Path:
    """Aceita a própria pasta Translate, a pasta data ou a pasta do jogo."""
    for candidate in (folder / TRANSLATE_DIR, folder / TRANSLATE_DIR.name):
        if candidate.is_dir():
            return candidate
    return folder


def _load_external(path: Path) -> TextFile:
    """Arquivo trazido de fora: pode ter sido salvo em UTF-8 por um editor de texto."""
    data = path.read_bytes()
    if data.startswith(b"\xef\xbb\xbf"):
        return TextFile.from_text(path, "utf-8", data[3:].decode("utf-8", "surrogateescape"))
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return TextFile.load(path)
    return TextFile.from_text(path, "utf-8" if not text.isascii() else GAME_ENCODING, text)


def _same_text(first: list[str], second: list[str]) -> bool:
    """Iguais a menos do tipo de quebra de linha."""
    return [value.replace("\r\n", "\n") for value in first] == [value.replace("\r\n", "\n") for value in second]


def plan_text_import(
    source: Path,
    game_dir: Path,
    edits: dict[str, dict[str, TextEdit]],
) -> TextImport:
    """Compara os T_*.ini de `source` com os do jogo, ID por ID.

    Os arquivos importados só fornecem textos: o que muda vira edição do projeto, e o
    envio a aplica sobre o arquivo atual do jogo, então IDs que uma atualização trouxe
    depois continuam com o texto oficial. Texto igual ao do jogo não gera edição.
    """
    result = TextImport()
    folder = import_source_folder(source)
    for path in sorted(folder.glob("*.ini")):
        if path.name.count(".") != 1:
            continue
        game_path = game_dir / TRANSLATE_DIR / path.name
        if not game_path.is_file():
            result.unknown_files.append(path.name)
            continue
        game_file = TextFile.load(game_path)
        imported = _load_external(path)
        # Arquivos do jogo misturam CRLF e LF (T_Npc quebra o nome em LF); segue o do registro.
        crlf = game_file.text.count("\r\n")
        file_newline = "\r\n" if crlf * 2 >= game_file.text.count("\n") else "\n"
        current = edits.get(path.name, {})
        for record_id, record in imported.by_id.items():
            game_record = game_file.by_id.get(record_id)
            if game_record is None:
                result.missing_ids += 1
                continue
            game_text = "|".join(game_record.fields)
            newline = "\r\n" if "\r\n" in game_text else "\n" if "\n" in game_text else file_newline
            fields = [value.replace("\r\n", "\n").replace("\n", newline) for value in record.fields]
            try:
                for value in fields:
                    value.encode(game_file.encoding, "surrogateescape")
            except UnicodeEncodeError:
                result.unsupported += 1
                continue
            existing = current.get(record_id)
            if existing is not None:
                if _same_text(existing.fields, fields):
                    continue
            elif _same_text(fields, game_record.fields):
                # Já está assim no jogo. Não compara com o backup em .history: ele pode ser
                # de antes de o launcher trocar o idioma, e tudo pareceria diferente.
                continue
            original = list(existing.original) if existing is not None and existing.original else list(game_record.fields)
            if existing is not None:
                result.replaced += 1
            result.edits.setdefault(path.name, {})[record_id] = TextEdit(fields, original)
    return result


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
