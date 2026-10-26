"""Aba Textos: busca em todos os arquivos de data/Translate e edição num painel flutuante."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
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

from . import text_data
from .text_data import TextEdit, TextFile, TextRecord
from .theme import COLORS

RESULT_LIMIT = 500


def _one_line(value: str) -> str:
    return value.replace("\r\n", " ⏎ ").replace("\n", " ⏎ ").replace("\t", " ")


class TextEditDialog(QDialog):
    """Editor flutuante de um registro: um campo de texto por coluna do arquivo."""

    def __init__(self, text_file: TextFile, record: TextRecord, current: list[str], edited: bool, parent=None):
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
        if edited:
            restore = QPushButton(self.tr("Voltar ao texto do jogo"))
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
    """Busca em todos os textos do jogo; as edições ficam no projeto (data/text-edits.json)."""

    edits_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.game_dir: Path | None = None
        self.project_root: Path | None = None
        self.files: list[TextFile] | None = None
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
        self.set_context(None, None)

    def set_context(self, game_dir: Path | None, project_root: Path | None) -> None:
        if game_dir != self.game_dir:
            self.files = None  # relê na próxima busca
        self.game_dir = game_dir
        self.project_root = project_root
        self.edits = text_data.load_edits(project_root) if project_root is not None else {}
        self.search_edit.setEnabled(game_dir is not None)
        self.refresh_results()

    def _ensure_loaded(self) -> list[TextFile]:
        if self.files is None:
            self.files = []
            if self.game_dir is not None:
                for path in text_data.translate_files(self.game_dir):
                    try:
                        self.files.append(TextFile.load(path))
                    except OSError:
                        continue
        return self.files

    def reload(self) -> None:
        self.files = None
        self.refresh_results()

    def _current_fields(self, text_file: TextFile, record: TextRecord) -> tuple[list[str], bool]:
        edit = self.edits.get(text_file.name, {}).get(record.record_id)
        return (list(edit.fields), True) if edit is not None else (list(record.fields), False)

    def refresh_results(self) -> None:
        self.results.clear()
        if self.game_dir is None:
            self.summary.setText(self.tr("Defina a pasta do jogo no projeto para ver os textos."))
            return
        query = self.search_edit.text().strip()
        edited_only = self.edited_only.isChecked()
        if not query and not edited_only:
            count = sum(len(records) for records in self.edits.values())
            self.summary.setText(
                self.tr("Digite para buscar em data/Translate. {count} texto(s) editado(s) neste projeto.").format(count=count)
            )
            return
        matches: list[tuple[TextFile, TextRecord]] = []
        for text_file in self._ensure_loaded():
            edited = self.edits.get(text_file.name, {})
            if edited_only:
                candidates = [text_file.by_id[record_id] for record_id in edited if record_id in text_file.by_id]
                if query:
                    lowered = query.lower()
                    candidates = [
                        record for record in candidates
                        if any(lowered in value.lower() for value in self._current_fields(text_file, record)[0])
                    ]
            else:
                candidates = text_file.find(query)
                # Texto editado que agora casa com a busca também aparece.
                lowered = query.lower()
                for record_id, edit in edited.items():
                    record = text_file.by_id.get(record_id)
                    if record is not None and record not in candidates and any(lowered in value.lower() for value in edit.fields):
                        candidates.append(record)
            matches.extend((text_file, record) for record in candidates)
        shown = matches[:RESULT_LIMIT]
        for text_file, record in shown:
            fields, edited = self._current_fields(text_file, record)
            item = QTreeWidgetItem([_one_line(" | ".join(fields)), text_file.name, record.record_id])
            item.setData(0, Qt.ItemDataRole.UserRole, (text_file.name, record.record_id))
            item.setToolTip(0, "\n".join(fields))
            if edited:
                item.setText(0, "● " + item.text(0))
                item.setForeground(0, QColor(COLORS["ACCENT_TEXT"]))
            self.results.addTopLevelItem(item)
        if len(matches) > RESULT_LIMIT:
            self.summary.setText(self.tr("{total} resultados; mostrando os primeiros {shown}.").format(total=len(matches), shown=RESULT_LIMIT))
        else:
            self.summary.setText(self.tr("{total} resultado(s).").format(total=len(matches)))

    def _open_item(self, item: QTreeWidgetItem, _column: int = 0) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data or self.project_root is None:
            return
        name, record_id = data
        text_file = next((loaded for loaded in self._ensure_loaded() if loaded.name == name), None)
        record = text_file.by_id.get(record_id) if text_file is not None else None
        if text_file is None or record is None:
            return
        fields, edited = self._current_fields(text_file, record)
        dialog = TextEditDialog(text_file, record, fields, edited, self)
        dialog.move(QCursor.pos() + QPoint(12, 12))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        records = self.edits.setdefault(name, {})
        if dialog.restore_requested or dialog.values() == record.fields:
            records.pop(record_id, None)
        else:
            records[record_id] = TextEdit(dialog.values(), list(record.fields))
        text_data.save_edits(self.project_root, self.edits)
        self.refresh_results()
        self.edits_changed.emit()
