"""Aba Textos: busca em todos os arquivos de data/Translate e edição num painel flutuante."""

from __future__ import annotations

from pathlib import Path

import time
from threading import Thread

from PySide6.QtCore import QCoreApplication, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import project as project_module
from . import storage, text_data
from .text_data import TextEdit, TextFile, TextRecord
from .theme import COLORS

RESULT_LIMIT = 500


def _one_line(value: str) -> str:
    return value.replace("\r\n", " ⏎ ").replace("\n", " ⏎ ").replace("\t", " ")


class TextEditDialog(QDialog):
    """Editor flutuante de um registro: um campo de texto por coluna do arquivo."""

    def __init__(
        self, text_file: TextFile, record: TextRecord, current: list[str], original: list[str] | None, parent=None
    ):
        super().__init__(parent)
        self.setWindowTitle(self.tr("{file} · ID {id}").format(file=text_file.name, id=record.record_id))
        self.text_file = text_file
        self.record = record
        self.restore_requested = False
        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        self.editors: list[QPlainTextEdit] = []
        for number, value in enumerate(current, 1):
            if len(current) > 1:
                layout.addWidget(QLabel(self.tr("Coluna {number}").format(number=number)))
            editor = QPlainTextEdit(value.replace("\r\n", "\n"))
            lines = max(1, value.count("\n") + 1)
            editor.setMinimumHeight(min(220, 28 + lines * 18))
            layout.addWidget(editor)
            self.editors.append(editor)
        hint = QLabel(self.tr("O jogo usa \"|\" para separar as colunas, então ele não pode aparecer no texto."))
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {COLORS['TEXT_MUTED']};")
        layout.addWidget(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        if original is not None and original != current:
            restore = QPushButton(self.tr("Voltar ao texto original"))
            restore.setToolTip(_one_line(" | ".join(original)))
            restore.clicked.connect(self._restore)
            buttons.addButton(restore, QDialogButtonBox.ButtonRole.ResetRole)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(520, self.sizeHint().height())

    def values(self) -> list[str]:
        newline = "\r\n" if "\r\n" in self.text_file.text else "\n"
        return [editor.toPlainText().replace("\n", newline) for editor in self.editors]

    def _restore(self) -> None:
        self.restore_requested = True
        self.accept()

    def _save(self) -> None:
        values = self.values()
        if any("|" in value for value in values):
            QMessageBox.warning(self, self.tr("Texto inválido"), self.tr("Tire o \"|\" do texto: o jogo o usa para separar colunas."))
            return
        try:
            for value in values:
                value.encode(self.text_file.encoding)
        except UnicodeEncodeError:
            QMessageBox.warning(
                self,
                self.tr("Caractere não suportado"),
                self.tr("Este arquivo está em {encoding} e não aceita algum caractere digitado.").format(
                    encoding=self.text_file.encoding
                ),
            )
            return
        self.accept()


class TextsPanel(QWidget):
    """Busca em todos os textos do jogo; as edições ficam no project.db do projeto."""

    edits_changed = Signal()
    _index_done = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.game_dir: Path | None = None
        self.project_root: Path | None = None
        self.files: list[TextFile] | None = None
        self._by_name: dict[str, TextFile] = {}
        self._indexing: Path | None = None
        self.index_game_dir: Path | None = None  # jogo cujo índice FTS5 está pronto
        self.edits: dict[str, dict[str, TextEdit]] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(self.tr("Buscar em todos os textos do jogo…"))
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(lambda _text: self._timer.start())
        layout.addWidget(self.search_edit)
        options = QHBoxLayout()
        self.edited_only = QCheckBox(self.tr("Só editados"))
        self.edited_only.toggled.connect(lambda _checked: self.refresh_results())
        options.addWidget(self.edited_only)
        options.addStretch(1)
        self.import_button = QPushButton(self.tr("Importar textos…"))
        self.import_button.setToolTip(self.tr(
            "Traz alterações de arquivos T_*.ini que você já tinha editado. Compara ID por ID com o jogo:\n"
            "só o que mudou vira edição do projeto, e IDs novos de atualizações continuam com o texto oficial."
        ))
        self.import_button.clicked.connect(lambda _checked: self.import_texts())
        options.addWidget(self.import_button)
        layout.addLayout(options)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setStyleSheet(f"color: {COLORS['TEXT_MUTED']};")
        layout.addWidget(self.summary)
        self.results = QTreeWidget()
        self.results.setObjectName("textResults")
        self.results.setHeaderLabels([self.tr("Texto"), self.tr("Arquivo"), "ID"])
        self.results.setRootIsDecorated(False)
        self.results.setUniformRowHeights(True)
        self.results.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.results.itemClicked.connect(self._open_item)
        header = self.results.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.results, 1)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self.refresh_results)
        self._index_done.connect(self._index_finished)
        self.set_context(None, None)

    def set_context(self, game_dir: Path | None, project_root: Path | None) -> None:
        if game_dir != self.game_dir:
            self.files = None  # relê na próxima busca
            self._by_name = {}
        self.game_dir = game_dir
        self.project_root = project_root
        self._baseline = None
        self.edits = text_data.load_edits(project_root) if project_root is not None else {}
        self.search_edit.setEnabled(game_dir is not None)
        self.import_button.setEnabled(game_dir is not None and project_root is not None)
        self._start_indexing()
        self.refresh_results()

    def _start_indexing(self) -> None:
        """Atualiza o índice FTS5 em segundo plano; até ficar pronto, a busca é em memória."""
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
            self._index_done.emit(game_dir)

        Thread(target=work, name="gf-ui-text-index", daemon=True).start()

    def _index_finished(self, game_dir: Path) -> None:
        self._indexing = None
        if game_dir == self.game_dir:
            self.index_game_dir = game_dir
            if self.search_edit.text().strip():
                self.refresh_results()

    def wait_for_index(self, timeout: float = 30.0) -> bool:
        """Para testes e scripts: espera o índice ficar pronto."""
        deadline = time.monotonic() + timeout
        while self.index_game_dir != self.game_dir and time.monotonic() < deadline:
            QCoreApplication.processEvents()
            time.sleep(0.01)
        return self.index_game_dir == self.game_dir

    def _ensure_loaded(self) -> list[TextFile]:
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

    def _file(self, name: str) -> TextFile | None:
        """Um arquivo do jogo, lido só quando preciso (abrir para editar, marcar alterados)."""
        if name not in self._by_name and self.game_dir is not None:
            path = self.game_dir / text_data.TRANSLATE_DIR / name
            if path.is_file():
                self._by_name[name] = TextFile.load(path)
        return self._by_name.get(name)

    def reload(self) -> None:
        self.files = None
        self._by_name = {}
        self._baseline = None
        self.index_game_dir = None
        self._start_indexing()
        self.refresh_results()

    def _history(self) -> dict[str, TextFile]:
        if self._baseline is None:
            self._baseline = (
                text_data.history_baseline(self.project_root, self._language())
                if self.project_root is not None else {}
            )
        return self._baseline

    def _language(self) -> str | None:
        """Idioma do jogo agora: o do launcher ou, sem ele, o do T_TextIndex.ini."""
        if self.game_dir is None:
            return None
        language = text_data.game_language(self.game_dir)
        if language is None:
            index = self._file("T_TextIndex.ini")
            language = text_data.detect_language(index) if index is not None else None
        return language

    def _changed_in_game(self, name: str) -> set[str]:
        """IDs cujo texto no jogo difere do backup original (enviados antes, sem edição guardada)."""
        original = self._history().get(name)
        text_file = self._file(name) if original is not None else None
        if original is None or text_file is None:
            return set()
        changed = {
            record_id for record_id, record in original.by_id.items()
            if record_id in text_file.by_id and text_file.by_id[record_id].fields != record.fields
        }
        return changed

    def _original_fields(self, name: str, record: TextRecord) -> list[str] | None:
        """Texto antes de qualquer edição: o guardado na edição ou, se não houver, o do
        backup mais antigo do envio. None quando o jogo nunca recebeu edição deste texto."""
        edit = self.edits.get(name, {}).get(record.record_id)
        if edit is not None and edit.original:
            return list(edit.original)
        original = self._history().get(name)
        backup = original.by_id.get(record.record_id) if original is not None else None
        return list(backup.fields) if backup is not None else None

    def _updated_by_game(self, name: str, record: TextRecord) -> bool:
        """O jogo trouxe outro texto para um registro editado: nem o original guardado
        nem a edição. Reenviar sobrescreveria a novidade da atualização."""
        edit = self.edits.get(name, {}).get(record.record_id)
        return bool(edit is not None and edit.original and record.fields not in (edit.original, edit.fields))

    def _current_fields(self, name: str, record: TextRecord) -> tuple[list[str], bool]:
        edit = self.edits.get(name, {}).get(record.record_id)
        return (list(edit.fields), True) if edit is not None else (list(record.fields), False)

    def _search(self, query: str) -> tuple[list[tuple[str, TextRecord]], int]:
        """Registros do jogo que contêm `query`: pelo índice quando pronto, senão em memória."""
        if self.index_game_dir == self.game_dir and len(query) >= 3:
            rows, total = storage.TextIndexStore(project_module.PROJECTS_ROOT).search(
                self.game_dir, query, RESULT_LIMIT
            )
            return [(name, TextRecord(record_id, 0, 0, fields)) for name, record_id, fields in rows], total
        entries = [(text_file.name, record) for text_file in self._ensure_loaded() for record in text_file.find(query)]
        return entries, len(entries)

    def refresh_results(self) -> None:
        self.results.clear()
        if self.game_dir is None:
            self.summary.setText(self.tr("Defina a pasta do jogo no projeto para ver os textos."))
            return
        query = self.search_edit.text().strip()
        lowered = query.lower()
        # Sem busca, a aba mostra o que este projeto já mudou (editado ou já enviado).
        edited_only = self.edited_only.isChecked() or not query
        if not query and not self.edits and not self._history():
            self.summary.setText(self.tr("Digite para buscar em data/Translate."))
            return
        changed = {name: self._changed_in_game(name) for name in self._history()}
        entries: list[tuple[str, TextRecord]] = []
        if edited_only:
            for name in sorted(set(self.edits) | set(changed)):
                text_file = self._file(name)
                if text_file is None:
                    continue
                edited = self.edits.get(name, {})
                ids = list(edited) + sorted(changed.get(name, set()) - set(edited), key=int)
                for record_id in ids:
                    record = text_file.by_id.get(record_id)
                    if record is None:
                        continue
                    if query and not any(lowered in value.lower() for value in self._current_fields(name, record)[0]):
                        continue
                    entries.append((name, record))
            total = len(entries)
        else:
            entries, total = self._search(query)
            # Texto editado que agora casa com a busca também aparece.
            seen = {(name, record.record_id) for name, record in entries}
            for name, records in self.edits.items():
                for record_id, edit in records.items():
                    if (name, record_id) in seen or not any(lowered in value.lower() for value in edit.fields):
                        continue
                    text_file = self._file(name)
                    record = text_file.by_id.get(record_id) if text_file is not None else None
                    if record is not None:
                        entries.append((name, record))
                        total += 1
        updates = 0
        for name, record in entries[:RESULT_LIMIT]:
            fields, edited = self._current_fields(name, record)
            item = QTreeWidgetItem([_one_line(" | ".join(fields)), name, record.record_id])
            item.setData(0, Qt.ItemDataRole.UserRole, (name, record.record_id))
            item.setToolTip(0, "\n".join(fields))
            if edited and self._updated_by_game(name, record):
                updates += 1
                item.setText(0, "⚠ " + item.text(0))
                item.setForeground(0, QColor(COLORS["WARNING_TEXT"]))
                item.setToolTip(0, self.tr(
                    "Uma atualização do jogo mudou este texto depois da sua edição.\n"
                    "Original quando você editou: {original}\nNo jogo agora: {game}\nSua edição: {mine}"
                ).format(
                    original=_one_line(" | ".join(self.edits[name][record.record_id].original)),
                    game=_one_line(" | ".join(record.fields)),
                    mine=_one_line(" | ".join(fields)),
                ))
            elif edited:
                item.setText(0, "● " + item.text(0))
                item.setForeground(0, QColor(COLORS["ACCENT_TEXT"]))
            elif record.record_id in changed.get(name, set()):
                item.setText(0, "◐ " + item.text(0))
                item.setForeground(0, QColor(COLORS["WARNING_TEXT"]))
                item.setToolTip(0, self.tr(
                    "O jogo está com um texto diferente do original (backup do primeiro envio), "
                    "mas não há edição guardada neste projeto. Abra para voltar ao original."
                ) + "\n\n" + "\n".join(fields))
            self.results.addTopLevelItem(item)
        if not query and not entries:
            summary = self.tr("Digite para buscar em data/Translate. Nenhum texto editado neste projeto.")
        elif not query:
            summary = self.tr("{total} texto(s) mudado(s) neste projeto. Digite para buscar em todos.").format(total=total)
        elif total > RESULT_LIMIT:
            summary = self.tr("{total} resultados; mostrando os primeiros {shown}.").format(total=total, shown=RESULT_LIMIT)
        else:
            summary = self.tr("{total} resultado(s).").format(total=total)
        if updates:
            summary += " " + self.tr("⚠ {count} mudou(aram) no jogo depois da edição: confira antes de enviar.").format(count=updates)
        self.summary.setText(summary)

    def import_texts(self, folder: Path | None = None) -> None:
        """Importa T_*.ini já alterados como edições do projeto (ID por ID, sem trocar o arquivo)."""
        if self.game_dir is None or self.project_root is None:
            return
        if folder is None:
            chosen = QFileDialog.getExistingDirectory(
                self, self.tr("Pasta com os arquivos de texto alterados (T_*.ini)"), str(self.game_dir.parent)
            )
            if not chosen:
                return
            folder = Path(chosen)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            plan = text_data.plan_text_import(folder, self.game_dir, self.edits)
        finally:
            QApplication.restoreOverrideCursor()
        notes = []
        if plan.missing_ids:
            notes.append(self.tr("{count} ID(s) não existem mais no jogo e foram ignorados.").format(count=plan.missing_ids))
        if plan.unsupported:
            notes.append(self.tr("{count} texto(s) têm caracteres que o jogo não aceita e foram ignorados.").format(count=plan.unsupported))
        if plan.unknown_files:
            notes.append(self.tr("Arquivos que o jogo não tem: {files}.").format(files=", ".join(plan.unknown_files)))
        if not plan.count:
            message = self.tr(
                "Nenhum texto diferente do jogo foi encontrado em {folder}.\n\n"
                "Se a pasta do jogo já está com esses arquivos copiados, deixe o launcher baixar os "
                "originais de novo e importe depois."
            ).format(folder=text_data.import_source_folder(folder))
            QMessageBox.information(self, self.tr("Importar textos"), "\n\n".join([message, *notes]))
            return
        per_file = "\n".join(f"{name}: {len(records)}" for name, records in sorted(plan.edits.items()))
        message = self.tr(
            "{count} texto(s) diferentes do jogo serão guardados como edições deste projeto:\n\n{files}\n\n"
            "IDs que não estão nos arquivos importados continuam com o texto do jogo."
        ).format(count=plan.count, files=per_file)
        if plan.replaced:
            notes.insert(0, self.tr("{count} substituem edições que você já tinha.").format(count=plan.replaced))
        answer = QMessageBox.question(self, self.tr("Importar textos"), "\n\n".join([message, *notes]))
        if answer != QMessageBox.StandardButton.Yes:
            return
        for name, records in plan.edits.items():
            self.edits.setdefault(name, {}).update(records)
        text_data.save_edits(self.project_root, self.edits)
        self.search_edit.clear()
        self.refresh_results()
        self.edits_changed.emit()

    def _open_item(self, item: QTreeWidgetItem, _column: int = 0) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data:
            self.edit_record(*data)

    def edit_record(self, name: str, record_id: str) -> bool:
        """Abre o editor flutuante de um registro (também usado pelo duplo clique no canvas)."""
        if self.project_root is None:
            return False
        text_file = self._file(name)
        record = text_file.by_id.get(record_id) if text_file is not None else None
        if text_file is None or record is None:
            return False
        fields, _edited = self._current_fields(name, record)
        original = self._original_fields(name, record)
        dialog = TextEditDialog(text_file, record, fields, original, self)
        dialog.move(QCursor.pos() + QPoint(12, 12))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return True
        records = self.edits.setdefault(name, {})
        original = original if original is not None else list(record.fields)
        values = list(original) if dialog.restore_requested else dialog.values()
        if values == record.fields and values == original:
            records.pop(record_id, None)  # jogo e original iguais: não há o que guardar
        else:
            # Mesmo voltando ao original, a edição fica: o jogo pode estar com o texto
            # enviado antes, e o próximo envio precisa gravar o original de volta.
            records[record_id] = TextEdit(values, list(original))
        text_data.save_edits(self.project_root, self.edits)
        self.refresh_results()
        self.edits_changed.emit()
        return True
