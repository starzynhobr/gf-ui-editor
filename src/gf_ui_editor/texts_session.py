"""Aba Textos sem Qt: contexto, índice, busca, estado de cada resultado, editar e importar.

A interface clássica (texts_panel.TextsPanel) e a nova (web_api/texts.py) só desenham o que
este serviço devolve. Textos visíveis ficam na interface: aqui saem chaves e números.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from threading import Thread

from . import project as project_module
from . import storage, text_data
from .text_data import TextEdit, TextFile, TextImport, TextRecord

RESULT_LIMIT = 500

# Estado de um resultado (marcador na lista).
EDITED = "edited"  # ● edição guardada no projeto
UPDATED = "updated"  # ⚠ o jogo trouxe outro texto depois da edição
CHANGED = "changed"  # ◐ o jogo difere do original (envio antigo) sem edição guardada


def one_line(value: str) -> str:
    return value.replace("\r\n", " ⏎ ").replace("\n", " ⏎ ").replace("\t", " ")


@dataclass
class ResultRow:
    name: str
    record_id: str
    fields: list[str]  # o texto atual: a edição ou, sem ela, o do jogo
    state: str = ""  # "", EDITED, UPDATED ou CHANGED
    game_fields: list[str] = field(default_factory=list)  # o que está no jogo agora
    original: list[str] = field(default_factory=list)  # original guardado na edição (UPDATED)


@dataclass
class Results:
    rows: list[ResultRow]
    total: int
    # Chave do resumo para a interface traduzir: "no_game", "type_to_search", "nothing_edited",
    # "changed" {total}, "limited" {total, shown} ou "count" {total}.
    summary: str
    values: dict[str, int] = field(default_factory=dict)
    updates: int = 0  # ⚠: mudaram no jogo depois da edição


@dataclass
class OpenRecord:
    text_file: TextFile
    record: TextRecord
    fields: list[str]
    original: list[str] | None  # None quando o jogo nunca recebeu edição deste texto

    @property
    def newline(self) -> str:
        return "\r\n" if "\r\n" in self.text_file.text else "\n"

    @property
    def can_restore(self) -> bool:
        return self.original is not None and self.original != self.fields


def validate(values: list[str], encoding: str) -> str | None:
    """None se o registro pode ser gravado; senão "pipe" ou "encoding"."""
    if any("|" in value for value in values):
        return "pipe"
    try:
        for value in values:
            value.encode(encoding)
    except UnicodeEncodeError:
        return "encoding"
    return None


class TextsSession:
    """Busca em todos os textos do jogo; as edições ficam no project.db do projeto."""

    def __init__(self) -> None:
        self.game_dir: Path | None = None
        self.project_root: Path | None = None
        self.files: list[TextFile] | None = None
        self._by_name: dict[str, TextFile] = {}
        self._indexing: Path | None = None
        self.index_game_dir: Path | None = None  # jogo cujo índice FTS5 está pronto
        self.edits: dict[str, dict[str, TextEdit]] = {}
        self._baseline: dict[str, TextFile] | None = None

    # ---- contexto e índice -----------------------------------------------------------------
    def set_context(self, game_dir: Path | None, project_root: Path | None) -> None:
        if game_dir != self.game_dir:
            self.files = None  # relê na próxima busca
            self._by_name = {}
        self.game_dir = game_dir
        self.project_root = project_root
        self._baseline = None
        self.edits = text_data.load_edits(project_root) if project_root is not None else {}

    def start_indexing(self, on_done: Callable[[Path], None]) -> None:
        """Atualiza o índice FTS5 em segundo plano; até ficar pronto, a busca é em memória.

        `on_done(game_dir)` é chamado na thread do índice; quem chama repassa para
        index_finished na sua própria thread.
        """
        game_dir = self.game_dir
        if game_dir is None or self._indexing == game_dir:
            return
        self._indexing = game_dir
        projects_root = project_module.PROJECTS_ROOT

        def work() -> None:
            try:
                text_data.sync_text_index(game_dir, projects_root)
            except Exception:  # noqa: BLE001 - sem índice a busca continua em memória
                return
            on_done(game_dir)

        Thread(target=work, name="gf-ui-text-index", daemon=True).start()

    def index_finished(self, game_dir: Path) -> bool:
        """Marca o índice pronto. True se ele é do jogo atual (vale refazer a busca)."""
        self._indexing = None
        if game_dir == self.game_dir:
            self.index_game_dir = game_dir
            return True
        return False

    @property
    def index_ready(self) -> bool:
        return self.index_game_dir == self.game_dir

    def reload(self) -> None:
        """Os arquivos do jogo mudaram (F5 enviou textos): relê tudo e refaz o índice."""
        self.files = None
        self._by_name = {}
        self._baseline = None
        self.index_game_dir = None

    # ---- arquivos ------------------------------------------------------------------------
    def ensure_loaded(self) -> list[TextFile]:
        if self.files is None:
            self.files = []
            if self.game_dir is not None:
                for path in text_data.translate_files(self.game_dir):
                    try:
                        self.files.append(TextFile.load(path))
                    except OSError:
                        continue
            self._by_name.update({text_file.name: text_file for text_file in self.files})
        return self.files

    def file(self, name: str) -> TextFile | None:
        """Um arquivo do jogo, lido só quando preciso (abrir para editar, marcar alterados)."""
        if name not in self._by_name and self.game_dir is not None:
            path = self.game_dir / text_data.TRANSLATE_DIR / name
            if path.is_file():
                self._by_name[name] = TextFile.load(path)
        return self._by_name.get(name)

    def history(self) -> dict[str, TextFile]:
        if self._baseline is None:
            self._baseline = (
                text_data.history_baseline(self.project_root, self.language())
                if self.project_root is not None else {}
            )
        return self._baseline

    def language(self) -> str | None:
        """Idioma do jogo agora: o do launcher ou, sem ele, o do T_TextIndex.ini."""
        if self.game_dir is None:
            return None
        language = text_data.game_language(self.game_dir)
        if language is None:
            index = self.file("T_TextIndex.ini")
            language = text_data.detect_language(index) if index is not None else None
        return language

    # ---- estado de cada registro ------------------------------------------------------------
    def changed_in_game(self, name: str) -> set[str]:
        """IDs cujo texto no jogo difere do backup original (enviados antes, sem edição guardada)."""
        original = self.history().get(name)
        text_file = self.file(name) if original is not None else None
        if original is None or text_file is None:
            return set()
        return {
            record_id for record_id, record in original.by_id.items()
            if record_id in text_file.by_id and text_file.by_id[record_id].fields != record.fields
        }

    def original_fields(self, name: str, record: TextRecord) -> list[str] | None:
        """Texto antes de qualquer edição: o guardado na edição ou, se não houver, o do
        backup mais antigo do envio. None quando o jogo nunca recebeu edição deste texto."""
        edit = self.edits.get(name, {}).get(record.record_id)
        if edit is not None and edit.original:
            return list(edit.original)
        original = self.history().get(name)
        backup = original.by_id.get(record.record_id) if original is not None else None
        return list(backup.fields) if backup is not None else None

    def updated_by_game(self, name: str, record: TextRecord) -> bool:
        """O jogo trouxe outro texto para um registro editado: nem o original guardado
        nem a edição. Reenviar sobrescreveria a novidade da atualização."""
        edit = self.edits.get(name, {}).get(record.record_id)
        return bool(edit is not None and edit.original and record.fields not in (edit.original, edit.fields))

    def current_fields(self, name: str, record: TextRecord) -> tuple[list[str], bool]:
        edit = self.edits.get(name, {}).get(record.record_id)
        return (list(edit.fields), True) if edit is not None else (list(record.fields), False)

    # ---- busca -------------------------------------------------------------------------------
    def search(self, query: str) -> tuple[list[tuple[str, TextRecord]], int]:
        """Registros do jogo que contêm `query`: pelo índice quando pronto, senão em memória."""
        if self.index_game_dir == self.game_dir and len(query) >= 3:
            rows, total = storage.TextIndexStore(project_module.PROJECTS_ROOT).search(
                self.game_dir, query, RESULT_LIMIT
            )
            return [(name, TextRecord(record_id, 0, 0, fields)) for name, record_id, fields in rows], total
        entries = [(text_file.name, record) for text_file in self.ensure_loaded() for record in text_file.find(query)]
        return entries, len(entries)

    def results(self, query: str, edited_only: bool) -> Results:
        """Linhas da lista, total e resumo. Sem busca, mostra o que este projeto já mudou."""
        if self.game_dir is None:
            return Results([], 0, "no_game")
        query = query.strip()
        lowered = query.lower()
        edited_only = edited_only or not query
        if not query and not self.edits and not self.history():
            return Results([], 0, "type_to_search")
        changed = {name: self.changed_in_game(name) for name in self.history()}
        entries: list[tuple[str, TextRecord]] = []
        if edited_only:
            for name in sorted(set(self.edits) | set(changed)):
                text_file = self.file(name)
                if text_file is None:
                    continue
                edited = self.edits.get(name, {})
                ids = list(edited) + sorted(changed.get(name, set()) - set(edited), key=int)
                for record_id in ids:
                    record = text_file.by_id.get(record_id)
                    if record is None:
                        continue
                    if query and not any(lowered in value.lower() for value in self.current_fields(name, record)[0]):
                        continue
                    entries.append((name, record))
            total = len(entries)
        else:
            entries, total = self.search(query)
            # Texto editado que agora casa com a busca também aparece.
            seen = {(name, record.record_id) for name, record in entries}
            for name, records in self.edits.items():
                for record_id, edit in records.items():
                    if (name, record_id) in seen or not any(lowered in value.lower() for value in edit.fields):
                        continue
                    text_file = self.file(name)
                    record = text_file.by_id.get(record_id) if text_file is not None else None
                    if record is not None:
                        entries.append((name, record))
                        total += 1
        rows: list[ResultRow] = []
        updates = 0
        for name, record in entries[:RESULT_LIMIT]:
            fields, edited = self.current_fields(name, record)
            row = ResultRow(name, record.record_id, fields, game_fields=list(record.fields))
            if edited and self.updated_by_game(name, record):
                updates += 1
                row.state = UPDATED
                row.original = list(self.edits[name][record.record_id].original)
            elif edited:
                row.state = EDITED
            elif record.record_id in changed.get(name, set()):
                row.state = CHANGED
            rows.append(row)
        if not query and not entries:
            summary, values = "nothing_edited", {}
        elif not query:
            summary, values = "changed", {"total": total}
        elif total > RESULT_LIMIT:
            summary, values = "limited", {"total": total, "shown": RESULT_LIMIT}
        else:
            summary, values = "count", {"total": total}
        return Results(rows, total, summary, values, updates)

    # ---- editar ------------------------------------------------------------------------------
    def open_record(self, name: str, record_id: str) -> OpenRecord | None:
        """O registro para o editor flutuante; None sem projeto ou se não existe no jogo."""
        if self.project_root is None:
            return None
        text_file = self.file(name)
        record = text_file.by_id.get(record_id) if text_file is not None else None
        if text_file is None or record is None:
            return None
        fields, _edited = self.current_fields(name, record)
        return OpenRecord(text_file, record, fields, self.original_fields(name, record))

    def save_record(self, opened: OpenRecord, values: list[str] | None) -> None:
        """Grava a edição (`values`) ou volta ao original (`values` None) no project.db."""
        assert self.project_root is not None
        name, record = opened.text_file.name, opened.record
        records = self.edits.setdefault(name, {})
        original = opened.original if opened.original is not None else list(record.fields)
        values = list(original) if values is None else values
        if values == record.fields and values == original:
            records.pop(record.record_id, None)  # jogo e original iguais: não há o que guardar
        else:
            # Mesmo voltando ao original, a edição fica: o jogo pode estar com o texto
            # enviado antes, e o próximo envio precisa gravar o original de volta.
            records[record.record_id] = TextEdit(values, list(original))
        text_data.save_edits(self.project_root, self.edits)

    # ---- importar ----------------------------------------------------------------------------
    @property
    def can_import(self) -> bool:
        return self.game_dir is not None and self.project_root is not None

    def plan_import(self, folder: Path) -> TextImport:
        assert self.game_dir is not None
        return text_data.plan_text_import(folder, self.game_dir, self.edits)

    def apply_import(self, plan: TextImport) -> None:
        assert self.project_root is not None
        for name, records in plan.edits.items():
            self.edits.setdefault(name, {}).update(records)
        text_data.save_edits(self.project_root, self.edits)
