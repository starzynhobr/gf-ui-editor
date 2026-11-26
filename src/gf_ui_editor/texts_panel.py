"""Aba Textos: busca em todos os arquivos de data/Translate e edição num painel flutuante."""

from __future__ import annotations

from pathlib import Path

import time

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

from . import text_data, texts_session
from .text_data import TextFile, TextRecord
from .texts_session import RESULT_LIMIT, one_line as _one_line  # noqa: F401 - RESULT_LIMIT continua exportado daqui
from .theme import COLORS


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
        problem = texts_session.validate(self.values(), self.text_file.encoding)
        if problem == "pipe":
            QMessageBox.warning(self, self.tr("Texto inválido"), self.tr("Tire o \"|\" do texto: o jogo o usa para separar colunas."))
            return
        if problem == "encoding":
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
    """Busca em todos os textos do jogo; as edições ficam no project.db do projeto.

    A lógica (contexto, índice, busca, estado dos resultados, gravar, importar) é do
    serviço texts_session; aqui só ficam os widgets, os textos traduzidos e os diálogos.
    """

    edits_changed = Signal()
    _index_done = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.session = texts_session.TextsSession()
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

    # Estado do serviço, com os nomes de antes (o app e os testes leem estes atributos).
    @property
    def game_dir(self) -> Path | None:
        return self.session.game_dir

    @property
    def project_root(self) -> Path | None:
        return self.session.project_root

    @property
    def files(self) -> list[TextFile] | None:
        return self.session.files

    @property
    def edits(self):
        return self.session.edits

    @property
    def index_game_dir(self) -> Path | None:
        return self.session.index_game_dir

    def set_context(self, game_dir: Path | None, project_root: Path | None) -> None:
        self.session.set_context(game_dir, project_root)
        self.search_edit.setEnabled(game_dir is not None)
        self.import_button.setEnabled(game_dir is not None and project_root is not None)
        self._start_indexing()
        self.refresh_results()

    def _start_indexing(self) -> None:
        """Atualiza o índice FTS5 em segundo plano; até ficar pronto, a busca é em memória."""
        self.session.start_indexing(self._index_done.emit)

    def _index_finished(self, game_dir: Path) -> None:
        if self.session.index_finished(game_dir):
            if self.search_edit.text().strip():
                self.refresh_results()

    def wait_for_index(self, timeout: float = 30.0) -> bool:
        """Para testes e scripts: espera o índice ficar pronto."""
        deadline = time.monotonic() + timeout
        while not self.session.index_ready and time.monotonic() < deadline:
            QCoreApplication.processEvents()
            time.sleep(0.01)
        return self.session.index_ready

    def _file(self, name: str) -> TextFile | None:
        return self.session.file(name)

    def reload(self) -> None:
        self.session.reload()
        self._start_indexing()
        self.refresh_results()

    def refresh_results(self) -> None:
        self.results.clear()
        found = self.session.results(self.search_edit.text(), self.edited_only.isChecked())
        if found.summary == "no_game":
            self.summary.setText(self.tr("Defina a pasta do jogo no projeto para ver os textos."))
            return
        if found.summary == "type_to_search":
            self.summary.setText(self.tr("Digite para buscar em data/Translate."))
            return
        for row in found.rows:
            item = QTreeWidgetItem([_one_line(" | ".join(row.fields)), row.name, row.record_id])
            item.setData(0, Qt.ItemDataRole.UserRole, (row.name, row.record_id))
            item.setToolTip(0, "\n".join(row.fields))
            if row.state == texts_session.UPDATED:
                item.setText(0, "⚠ " + item.text(0))
                item.setForeground(0, QColor(COLORS["WARNING_TEXT"]))
                item.setToolTip(0, self.tr(
                    "Uma atualização do jogo mudou este texto depois da sua edição.\n"
                    "Original quando você editou: {original}\nNo jogo agora: {game}\nSua edição: {mine}"
                ).format(
                    original=_one_line(" | ".join(row.original)),
                    game=_one_line(" | ".join(row.game_fields)),
                    mine=_one_line(" | ".join(row.fields)),
                ))
            elif row.state == texts_session.EDITED:
                item.setText(0, "● " + item.text(0))
                item.setForeground(0, QColor(COLORS["ACCENT_TEXT"]))
            elif row.state == texts_session.CHANGED:
                item.setText(0, "◐ " + item.text(0))
                item.setForeground(0, QColor(COLORS["WARNING_TEXT"]))
                item.setToolTip(0, self.tr(
                    "O jogo está com um texto diferente do original (backup do primeiro envio), "
                    "mas não há edição guardada neste projeto. Abra para voltar ao original."
                ) + "\n\n" + "\n".join(row.fields))
            self.results.addTopLevelItem(item)
        if found.summary == "nothing_edited":
            summary = self.tr("Digite para buscar em data/Translate. Nenhum texto editado neste projeto.")
        elif found.summary == "changed":
            summary = self.tr("{total} texto(s) mudado(s) neste projeto. Digite para buscar em todos.").format(**found.values)
        elif found.summary == "limited":
            summary = self.tr("{total} resultados; mostrando os primeiros {shown}.").format(**found.values)
        else:
            summary = self.tr("{total} resultado(s).").format(**found.values)
        if found.updates:
            summary += " " + self.tr("⚠ {count} mudou(aram) no jogo depois da edição: confira antes de enviar.").format(count=found.updates)
        self.summary.setText(summary)

    def import_texts(self, folder: Path | None = None) -> None:
        """Importa T_*.ini já alterados como edições do projeto (ID por ID, sem trocar o arquivo)."""
        if not self.session.can_import:
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
            plan = self.session.plan_import(folder)
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
        self.session.apply_import(plan)
        self.search_edit.clear()
        self.refresh_results()
        self.edits_changed.emit()

    def _open_item(self, item: QTreeWidgetItem, _column: int = 0) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data:
            self.edit_record(*data)

    def edit_record(self, name: str, record_id: str) -> bool:
        """Abre o editor flutuante de um registro (também usado pelo duplo clique no canvas)."""
        opened = self.session.open_record(name, record_id)
        if opened is None:
            return False
        dialog = TextEditDialog(opened.text_file, opened.record, opened.fields, opened.original, self)
        dialog.move(QCursor.pos() + QPoint(12, 12))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return True
        self.session.save_record(opened, None if dialog.restore_requested else dialog.values())
        self.refresh_results()
        self.edits_changed.emit()
        return True
