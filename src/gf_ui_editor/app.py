from __future__ import annotations

import argparse
from datetime import datetime
import difflib
import hashlib
from html import escape
import os
from pathlib import Path
from queue import Empty, SimpleQueue
import re
import shutil
import sys
from threading import Thread
import tempfile
import time
import zipfile

from PySide6.QtCore import QCoreApplication, QEvent, QFileSystemWatcher, QObject, QPointF, QRectF, QSize, QSettings, QSignalBlocker, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QCloseEvent,
    QColor,
    QDesktopServices,
    QFontDatabase,
    QIcon,
    QKeySequence,
    QPixmap,
    QUndoCommand,
    QUndoStack,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGraphicsScene,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QGridLayout,
    QTabWidget,
    QStyle,
    QTreeWidget,
    QTreeWidgetItem,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from . import game_texts
from .editor_widgets import (
    EditorView,
    ElementItem,
    GameDrawnItem,
    GameScreenItem,
    STATE_ROLE,
    ElementStateDelegate,
    GhostAreaItem,
    ReferenceLayerItem,
    state_slot_at,
)
from .game_layout import (
    client_resolution,
    load_user_positions,
    menu_shortcut_preview_y,
    root_screen_position,
    is_centered,
    looks_like_game_dir,
    normalize_game_dir,
    placement,
    rule_for,
    saved_position_applies,
    saved_section_for,
)
from .i18n import LANGUAGE_NAMES, LANGUAGES, document_error_text, kind_label, switch_language
from .icons import MONO_FONT, UI_FONT, icon, load_fonts
from .interaction import install_pointer_cursors
from . import backgrounds
from .controls import ControlError, delete_control, duplicate_control, free_window_id, new_image_control, owner_of
from .game_updates import (
    FileDiff,
    control_info,
    error_candidates,
    files_missing_id,
    file_diff,
    insert_controls,
    missing_controls,
    official_text_for,
    parse_game_error,
    cached_count,
    reference_ready,
    scan as scan_official,
    snapshot_official_ui,
    window_ids,
)
from . import release_notes, updater
from .update_dialog import SKIP, UPDATE, WhatsNewDialog
from .project import (
    PROJECTS_ROOT,
    Project,
    custom_ui_sources,
    extract_ui_zip,
    is_backup_file,
    list_projects,
    selected_ui,
    projects_publishing_to,
    safe_name,
)
from .atlas_dialog import AtlasDialog
from .texture_cache import TextureCache
from .theme import COLORS, stylesheet
GAME_RESOLUTIONS = (
    (800, 600),
    (1024, 768),
    (1280, 720),
    (1280, 1024),
    (1366, 768),
    (1600, 900),
    (1920, 1080),
    (2560, 1440),
)


def parse_resolution(text: str) -> tuple[int, int] | None:
    """Aceita "1920x1080", "1920×1080" ou "1920 1080"."""
    parts = text.lower().replace("×", "x").replace(" ", "x").split("x")
    numbers = [part for part in parts if part]
    if len(numbers) != 2:
        return None
    try:
        width, height = int(numbers[0]), int(numbers[1])
    except ValueError:
        return None
    if not (100 <= width <= 10000 and 100 <= height <= 10000):
        return None
    return width, height


from .xml_document import (
    DocumentError,
    ExternalModificationError,
    UIDocument,
    UIElement,
    UVRect,
    convert_utf8_file_to_big5,
)


# Áreas que o jogo desenha por código, sem textura no XML: arquivo -> x, y, largura, altura na
# tela do jogo. A foto do BasicChar fica sempre no canto da tela, mesmo movendo a janela
# (medida em prints do jogo, aproximada).
# Janelas sempre visíveis no jogo, para "Montar HUD padrão".
DEFAULT_HUD = (
    "BasicChar.xml", "Target.xml", "Radar.xml", "TinyClock.xml", "QuestTraceWnd.xml",
    "Channel.xml", "ShortcutBar.xml", "Menu.xml",
)
GAME_DRAWN_AREAS = {"basicchar.xml": (23, 7, 76, 76)}
TEXTURE_SUFFIXES = (".dds", ".tga")
DEFAULT_UI_DIRECTORY = Path(r"C:\Violet Games\Grand Fantasia Violet\UI")
APP_ICON_PATH = Path(__file__).resolve().parent / "assets" / "app-icon.png"
GITHUB_REPOSITORIES_URL = "https://github.com/starzynhobr?tab=repositories"


class AboutDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Sobre o GF UI Editor"))
        self.setMinimumWidth(360)

        icon = QLabel()
        icon.setPixmap(
            QPixmap(str(APP_ICON_PATH)).scaled(
                56,
                56,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        title = QLabel("GF UI Editor")
        title.setObjectName("panelTitle")
        version = QLabel(self.tr("Versão {version}").format(version=__version__))
        version.setObjectName("panelSubtitle")
        description = QLabel(self.tr("Editor visual de interfaces XML do Grand Fantasia Violet."))
        description.setWordWrap(True)

        github_button = QPushButton(self.tr("Ver outros projetos no GitHub"))
        github_button.setObjectName("githubButton")
        github_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(GITHUB_REPOSITORIES_URL))
        )
        close_button = QPushButton(self.tr("Fechar"))
        close_button.clicked.connect(self.accept)

        header = QHBoxLayout()
        header.setSpacing(12)
        header.addWidget(icon)
        heading = QVBoxLayout()
        heading.setSpacing(2)
        heading.addWidget(title)
        heading.addWidget(version)
        header.addLayout(heading)
        header.addStretch(1)

        actions = QHBoxLayout()
        actions.addWidget(github_button)
        actions.addStretch(1)
        actions.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        layout.addLayout(header)
        layout.addWidget(description)
        layout.addLayout(actions)
        install_pointer_cursors(self)


class NewProjectDialog(QDialog):
    """Nome do projeto e a UI que servirá de ponto de partida."""

    def __init__(self, game_dir: Path | None, parent: QWidget | None = None, loose_dir: Path | None = None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Novo projeto de UI"))
        self.setMinimumWidth(460)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(self.tr("Ex.: UI-Hero ajustada"))
        self.game_dir = game_dir
        self.game_dir_edit = QLineEdit()
        self.game_dir_edit.setReadOnly(True)
        self.game_dir_edit.setPlaceholderText(self.tr("Não definida"))
        game_dir_button = QPushButton(self.tr("Alterar…"))
        game_dir_button.clicked.connect(self._choose_game_dir)
        game_dir_row = QHBoxLayout()
        game_dir_row.setContentsMargins(0, 0, 0, 0)
        game_dir_row.addWidget(self.game_dir_edit, 1)
        game_dir_row.addWidget(game_dir_button)
        self.game_dir_warning = QLabel(
            self.tr("Esta pasta não parece ser a do jogo: escolha a pasta que tem o client.ini e as pastas UI e UICustom.")
        )
        self.game_dir_warning.setWordWrap(True)
        self.game_dir_warning.setObjectName("warningHint")
        self.source_combo = QComboBox()
        self.publish_combo = QComboBox()
        self.publish_combo.setToolTip(
            self.tr("Pasta de UICustom que Enviar para o jogo atualiza; é a UI que você escolhe no launcher.")
        )
        self.publish_warning = QLabel()
        self.publish_warning.setWordWrap(True)
        self.publish_warning.setObjectName("warningHint")
        self.publish_warning.setVisible(False)
        self._fill_sources()
        self.assets_check = QCheckBox(
            self.tr("Incluir ícones de itens, skills e telas de carregamento (~18 mil arquivos)")
        )
        self.assets_check.setToolTip(
            self.tr("Pastas itemicon, skillicon, uiicon e loadingframe. Marque só se for editar esses ícones; deixa a cópia e o teste mais lentos.")
        )
        explanation = QLabel(
            self.tr(
                "Os arquivos serão copiados para {root}. Backups e cópias antigas ficam de fora; "
                "a pasta do jogo não é alterada até você usar Enviar para o jogo."
            ).format(root=PROJECTS_ROOT)
        )
        explanation.setWordWrap(True)
        explanation.setObjectName("panelSubtitle")
        form = QFormLayout()
        form.addRow(self.tr("Nome"), self.name_edit)
        form.addRow(self.tr("Pasta do jogo"), game_dir_row)
        form.addRow("", self.game_dir_warning)
        form.addRow(self.tr("Começar a partir de"), self.source_combo)
        form.addRow(self.tr("Enviar para"), self.publish_combo)
        form.addRow("", self.publish_warning)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(self.tr("Criar projeto"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(self.tr("Cancelar"))
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.assets_check)
        # XML editados fora de projeto: entram por cima da UI de partida.
        self.loose_files: list[Path] = []
        self.loose_check = QCheckBox()
        self.loose_check.setChecked(True)
        self.loose_check.setVisible(False)
        layout.addWidget(self.loose_check)
        if loose_dir is not None:
            self._offer_loose_files(loose_dir)
        layout.addWidget(explanation)
        layout.addWidget(buttons)
        self.source_dir: Path | None = None
        self.publish_folder = ""
        self._last_index = 0
        self.source_combo.currentIndexChanged.connect(self._suggest_name)
        self.source_combo.activated.connect(self._source_activated)
        self.source_combo.currentIndexChanged.connect(self._fill_publish_targets)
        self.name_edit.textChanged.connect(self._fill_publish_targets)
        self.publish_combo.currentIndexChanged.connect(self._check_publish_target)
        self._fill_publish_targets()

    PICK_FOLDER = "?folder"
    PICK_ZIP = "?zip"

    def _offer_loose_files(self, loose_dir: Path) -> None:
        """Pasta da UI do jogo vira a origem; qualquer outra pasta tem seus XML copiados por cima."""
        index = next(
            (i for i in range(self.source_combo.count())
             if os.path.normcase(str(self.source_combo.itemData(i))) == os.path.normcase(str(loose_dir))),
            -1,
        )
        if index >= 0:
            self.source_combo.setCurrentIndex(index)
            self._last_index = index
            return
        self.loose_files = sorted(
            (path for path in loose_dir.glob("*.xml") if not is_backup_file(path.name)),
            key=lambda path: path.name.lower(),
        )
        if not self.loose_files:
            return
        self.loose_check.setText(
            self.tr("Trazer os {count} XML de {folder} (substituem os de mesmo nome)").format(
                count=len(self.loose_files), folder=loose_dir
            )
        )
        self.loose_check.setToolTip("\n".join(path.name for path in self.loose_files))
        self.loose_check.setVisible(True)

    def _fill_publish_targets(self, *_args) -> None:
        """Pasta própria do projeto, ou a UI de UICustom de onde ele partiu."""
        current = self.publish_combo.currentData()
        name = safe_name(self.name_edit.text().strip()) if self.name_edit.text().strip() else ""
        with QSignalBlocker(self.publish_combo):
            self.publish_combo.clear()
            self.publish_combo.addItem(
                self.tr("UICustom/{name} (pasta própria do projeto)").format(name=name or self.tr("nome do projeto")), ""
            )
            text = self.source_combo.currentText()
            if text.startswith("UICustom/"):
                origin = text.split("/", 1)[1]
                self.publish_combo.addItem(
                    self.tr("UICustom/{name} (atualiza a UI de origem)").format(name=origin), origin
                )
            index = self.publish_combo.findData(current)
            self.publish_combo.setCurrentIndex(max(index, 0))
        self._check_publish_target()

    def _check_publish_target(self, *_args) -> None:
        folder = self.publish_combo.currentData() or (
            safe_name(self.name_edit.text().strip()) if self.name_edit.text().strip() else ""
        )
        message = ""
        if folder:
            others = projects_publishing_to(folder)
            if others:
                message = self.tr(
                    "O projeto {projects} também envia para UICustom/{folder}: um vai sobrescrever o outro no jogo."
                ).format(projects=", ".join(others), folder=folder)
            elif (
                not self.publish_combo.currentData()
                and self.game_dir is not None
                and (self.game_dir / "UICustom" / folder).is_dir()
            ):
                message = self.tr(
                    "UICustom/{folder} já existe: Enviar para o jogo vai atualizar os arquivos dela."
                ).format(folder=folder)
        self.publish_warning.setText(message)
        self.publish_warning.setVisible(bool(message))

    def _fill_sources(self) -> None:
        """Fontes da UI: as da pasta do jogo (UI e UICustom) mais "Outra pasta…" e ".zip…"."""
        self.game_dir_edit.setText(str(self.game_dir) if self.game_dir is not None else "")
        self.game_dir_warning.setVisible(self.game_dir is not None and not looks_like_game_dir(self.game_dir))
        self.source_combo.clear()
        if self.game_dir is not None:
            for label, path in custom_ui_sources(self.game_dir):
                text = self.tr("UI em uso no jogo (pasta UI)") if label == "UI" else label
                self.source_combo.addItem(text, str(path))
        self.source_combo.addItem(self.tr("Outra pasta…"), self.PICK_FOLDER)
        self.source_combo.addItem(self.tr("Arquivo .zip…"), self.PICK_ZIP)
        self._last_index = 0

    def _choose_game_dir(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, self.tr("Pasta do Grand Fantasia Violet"), str(self.game_dir or "")
        )
        if chosen:
            self.game_dir = normalize_game_dir(Path(chosen))
            self._fill_sources()
            self._fill_publish_targets()

    def _suggest_name(self, _index: int = 0) -> None:
        text = self.source_combo.currentText()
        if text.startswith("UICustom/") and not self.name_edit.text().strip():
            self.name_edit.setText(text.split("/", 1)[1])

    def _source_activated(self, index: int) -> None:
        """"Outra pasta…" e "Arquivo .zip…" abrem o seletor na hora e viram um item da lista."""
        data = self.source_combo.itemData(index)
        if data not in (self.PICK_FOLDER, self.PICK_ZIP):
            self._last_index = index
            return
        if data == self.PICK_FOLDER:
            chosen = QFileDialog.getExistingDirectory(self, self.tr("Pasta com os arquivos da UI"))
        else:
            chosen, _filter = QFileDialog.getOpenFileName(
                self, self.tr("Arquivo .zip da UI"), "", self.tr("Arquivos .zip (*.zip)")
            )
        if not chosen:
            self.source_combo.setCurrentIndex(self._last_index)
            return
        position = self.source_combo.findData(self.PICK_FOLDER)
        self.source_combo.insertItem(position, str(Path(chosen)), chosen)
        self.source_combo.setCurrentIndex(position)
        self._last_index = position
        if not self.name_edit.text().strip():
            self.name_edit.setText(Path(chosen).stem if data == self.PICK_ZIP else Path(chosen).name)

    def _accept(self) -> None:
        if self.source_combo.currentData() in (self.PICK_FOLDER, self.PICK_ZIP):
            self._source_activated(self.source_combo.currentIndex())
            if self.source_combo.currentData() in (self.PICK_FOLDER, self.PICK_ZIP):
                return
        if not self.name_edit.text().strip():
            self.name_edit.setPlaceholderText(self.tr("Dê um nome ao projeto"))
            self.name_edit.setFocus()
            return
        data = self.source_combo.currentData()
        self.source_dir = Path(data)
        self.publish_folder = self.publish_combo.currentData() or ""
        if not self.loose_check.isChecked():
            self.loose_files = []
        self.accept()


class OfficialUIDialog(QDialog):
    """Guarda uma cópia da UI oficial para comparar; ensina a deixá-la na pasta UI pelo launcher."""

    # O launcher mostra "UI Padrão" em todos os idiomas; no Launcher.ini ela é "padrao".
    LAUNCHER_NAME = "UI Padrão"

    def __init__(self, game_dir: Path, parent: QWidget | None = None):
        super().__init__(parent)
        self.game_dir = game_dir
        self.setWindowTitle(self.tr("UI oficial de referência"))
        self.setMinimumWidth(520)
        intro = QLabel(
            self.tr(
                "O editor guarda uma cópia da UI oficial do jogo para comparar com a sua: é assim que ele "
                "sabe quais controles faltam e quais vieram de uma atualização. Basta guardar uma vez por "
                "atualização do jogo."
            )
        )
        intro.setWordWrap(True)
        self.status = QLabel()
        self.status.setObjectName("panelTitle")
        self.status.setWordWrap(True)
        self.save_button = QPushButton(self.tr("Guardar UI oficial agora"))
        self.save_button.setObjectName("accentPush")
        self.save_button.clicked.connect(self.try_snapshot)
        self.tutorial = QFrame()
        self.tutorial.setObjectName("card")
        tutorial_layout = QVBoxLayout(self.tutorial)
        tutorial_layout.setContentsMargins(14, 12, 14, 12)
        tutorial_layout.setSpacing(8)
        heading = QLabel(self.tr("A pasta UI do jogo está com outra UI"))
        heading.setObjectName("cardHeading")
        steps = QLabel(
            self.tr(
                "1. No launcher, escolha \"{name}\" na lista de UIs.\n"
                "2. Clique em Jogar uma vez (pode fechar o jogo logo depois).\n"
                "3. Volte aqui: o editor tenta de novo sozinho a cada poucos segundos.\n\n"
                "Depois você pode voltar a escolher a sua UI no launcher."
            ).format(name=self.LAUNCHER_NAME)
        )
        steps.setWordWrap(True)
        self.launcher_state = QLabel()
        self.launcher_state.setObjectName("panelSubtitle")
        retry = QPushButton(self.tr("Já fiz, tentar de novo"))
        retry.clicked.connect(self.try_snapshot)
        tutorial_layout.addWidget(heading)
        tutorial_layout.addWidget(steps)
        tutorial_layout.addWidget(self.launcher_state)
        tutorial_layout.addWidget(retry, 0, Qt.AlignmentFlag.AlignLeft)
        self.tutorial.setVisible(False)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText(self.tr("Fechar"))
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.addWidget(intro)
        layout.addWidget(self.status)
        layout.addWidget(self.save_button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.tutorial)
        layout.addWidget(buttons)
        self.timer = QTimer(self)
        self.timer.setInterval(3000)
        self.timer.timeout.connect(lambda: self.try_snapshot(automatic=True))
        self._refresh_status()

    def _refresh_status(self) -> None:
        cached, total = cached_count(self.game_dir)
        if total == 0:
            self.status.setText(self.tr("Não encontrei o GameDataFileList.txt do launcher nesta pasta do jogo."))
            self.save_button.setEnabled(False)
        elif reference_ready(self.game_dir):
            self.status.setText(
                self.tr("Guardada: {cached} de {total} arquivos da UI oficial atual.").format(cached=cached, total=total)
            )
        else:
            self.status.setText(
                self.tr("Ainda não guardada: {cached} de {total} arquivos da UI oficial atual.").format(cached=cached, total=total)
            )
        current = selected_ui(self.game_dir / "Launcher.ini")
        name = self.LAUNCHER_NAME if current.lower() in ("", "padrao") else current.split(":", 1)[-1]
        self.launcher_state.setText(self.tr("No launcher agora: {name}").format(name=name))

    def try_snapshot(self, automatic: bool = False) -> None:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            snapshot_official_ui(self.game_dir)
        finally:
            QApplication.restoreOverrideCursor()
        self._refresh_status()
        ready = reference_ready(self.game_dir)
        self.tutorial.setVisible(not ready)
        if ready:
            self.timer.stop()
            self.save_button.setText(self.tr("Pronto"))
            self.save_button.setEnabled(False)
        elif not self.timer.isActive():
            self.timer.start()

    def done(self, result: int) -> None:
        self.timer.stop()
        super().done(result)


class _PickRow(QFrame):
    """Linha da tabela de controles: clicar em qualquer ponto marca ou desmarca."""

    COLUMNS = (70, 120, 0, 110)  # ID, tipo, textura (estica), posição

    def __init__(self, cells: list[str], checked: bool, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("pickRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(10)
        self.check = QCheckBox()
        self.check.setObjectName("pickCheck")
        self.check.setFixedWidth(20)
        self.check.toggled.connect(self._sync)
        layout.addWidget(self.check)
        for text, width in zip(cells, self.COLUMNS, strict=True):
            label = QLabel(text)
            label.setObjectName("pickCell")
            if width:
                label.setFixedWidth(width)
                layout.addWidget(label)
            else:
                label.setMinimumWidth(80)
                layout.addWidget(label, 1)
        self.check.setChecked(checked)
        self._sync(checked)

    def _sync(self, checked: bool) -> None:
        self.setProperty("checked", checked)
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.check.toggle()
            event.accept()
            return
        super().mousePressEvent(event)

    @staticmethod
    def header(titles: list[str]) -> QWidget:
        header = QWidget()
        layout = QHBoxLayout(header)
        layout.setContentsMargins(11, 0, 11, 0)  # mesma margem das linhas, mais a borda delas
        layout.setSpacing(10)
        spacer = QWidget()
        spacer.setFixedWidth(20)
        layout.addWidget(spacer)
        for text, width in zip(titles, _PickRow.COLUMNS, strict=True):
            label = QLabel(text)
            label.setObjectName("sectionLabel")
            if width:
                label.setFixedWidth(width)
                layout.addWidget(label)
            else:
                layout.addWidget(label, 1)
        return header


class OfficialControlsDialog(QDialog):
    """Controles da UI oficial que o arquivo aberto não tem; a pessoa escolhe quais entram."""

    def __init__(
        self,
        file_name: str,
        new_ids: list[str],
        other_ids: list[str],
        infos: dict,
        focus_id: str | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Controles da UI oficial"))
        self.setMinimumSize(560, 520)
        title = QLabel(self.tr("Controles do oficial que {file} não tem").format(file=file_name))
        title.setObjectName("panelTitle")
        title.setWordWrap(True)
        self.search = QLineEdit()
        self.search.setPlaceholderText(self.tr("Buscar WindowID, ex.: 8301"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        self.checks: list[tuple[str, QCheckBox]] = []
        rows = QWidget()
        rows_layout = QVBoxLayout(rows)
        rows_layout.setContentsMargins(0, 0, 0, 0)
        rows_layout.setSpacing(6)
        rows_layout.addWidget(
            _PickRow.header([self.tr("ID"), self.tr("TIPO"), self.tr("TEXTURA DO OFICIAL"), self.tr("POSIÇÃO")])
        )
        self.sections: list[tuple[QLabel, list[_PickRow]]] = []
        for heading, ids, checked in (
            (self.tr("NOVOS NA ATUALIZAÇÃO DO JOGO"), new_ids, True),
            (self.tr("OUTROS QUE O OFICIAL TEM (PODEM TER SIDO REMOVIDOS DE PROPÓSITO)"), other_ids, False),
        ):
            if not ids:
                continue
            label = QLabel(heading)
            label.setObjectName("sectionLabel")
            label.setWordWrap(True)
            rows_layout.addWidget(label)
            members = []
            for window_id in ids:
                info = infos.get(window_id)
                cells = [
                    window_id,
                    kind_label(info.kind) if info is not None else "—",
                    (info.texture or "—") if info is not None else "—",
                    f"{info.position[0]}, {info.position[1]}" if info is not None else "—",
                ]
                row = _PickRow(cells, checked if focus_id is None else window_id == focus_id)
                row.setProperty("window_id", window_id)
                row.check.toggled.connect(self._update_button)
                rows_layout.addWidget(row)
                members.append(row)
                self.checks.append((window_id, row.check))
            self.sections.append((label, members))
        rows_layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(rows)
        note = QLabel(
            self.tr(
                "Entram na mesma posição do arquivo oficial e o resto do arquivo não muda. "
                "Dá para desfazer (Ctrl+Z); nada é gravado até você salvar."
            )
        )
        note.setWordWrap(True)
        note.setObjectName("panelSubtitle")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(self.tr("Cancelar"))
        self.add_button = buttons.addButton("", QDialogButtonBox.ButtonRole.AcceptRole)
        self.add_button.setObjectName("accentPush")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(self.search)
        layout.addWidget(scroll, 1)
        layout.addWidget(note)
        layout.addWidget(buttons)
        if focus_id is not None:
            self.search.setText(focus_id)
        self._update_button()

    def _filter(self, text: str) -> None:
        needle = text.strip()
        for label, members in self.sections:
            visible = 0
            for row in members:
                shown = not needle or str(row.property("window_id")).startswith(needle)
                row.setVisible(shown)
                visible += shown
            label.setVisible(visible > 0)

    def _update_button(self, *_args) -> None:
        count = len(self.selected_ids())
        self.add_button.setText(self.tr("Adicionar {count}").format(count=count))
        self.add_button.setEnabled(count > 0)

    def selected_ids(self) -> list[str]:
        return [window_id for window_id, check in self.checks if check.isChecked()]


class AttributeCommand(QUndoCommand):
    def __init__(self, window: "EditorWindow", index: int, name: str, old: str | None, new: str | None):
        super().__init__(f"{name} = {new}")
        self.window, self.index, self.name, self.old, self.new = window, index, name, old, new

    def redo(self) -> None:
        self.window.apply_attribute(self.index, self.name, self.new)

    def undo(self) -> None:
        self.window.apply_attribute(self.index, self.name, self.old)


class TextureCommand(QUndoCommand):
    def __init__(self, window: "EditorWindow", changes: dict[int, tuple[str, str]]):
        super().__init__(QCoreApplication.translate("EditorWindow", "Trocar textura de {count} controle(s)").format(count=len(changes)))
        self.window, self.changes = window, changes

    def redo(self) -> None:
        for index, (_old, new) in self.changes.items():
            self.window.apply_texture(index, new)

    def undo(self) -> None:
        for index, (old, _new) in self.changes.items():
            self.window.apply_texture(index, old)


class _ScanSignals(QObject):
    """Entrega à thread da interface o resultado da comparação feita em segundo plano."""

    done = Signal(object)


class StructureCommand(QUndoCommand):
    """Troca o documento inteiro (controles inseridos); desfazer volta ao anterior."""

    def __init__(self, window: "EditorWindow", old, new, inserted: list[str]):
        super().__init__(
            QCoreApplication.translate("EditorWindow", "Adicionar {count} controle(s) do oficial").format(count=len(inserted))
        )
        self.window, self.old, self.new, self.inserted = window, old, new, inserted

    def redo(self) -> None:
        self.window._swap_document(self.new, self.inserted)

    def undo(self) -> None:
        self.window._swap_document(self.old, [])


class PropertyPanel(QWidget):
    geometry_edited = Signal(tuple)
    ghost_fix_requested = Signal()
    atlas_requested = Signal()
    texture_change_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("propertiesPanel")
        self._loading = False
        self.selection_title = QLabel(self.tr("Nenhum elemento selecionado"))
        self.selection_title.setObjectName("panelTitle")
        self.selection_subtitle = QLabel(
            self.tr("Selecione um item no canvas ou na lista para editar sua geometria.")
        )
        self.selection_subtitle.setObjectName("panelSubtitle")
        self.selection_subtitle.setWordWrap(True)
        self.id_value = QLabel("—")
        self.kind_value = QLabel("—")
        self.parent_value = QLabel("—")
        self.ctrl_value = QLabel("—")
        for value in (self.id_value, self.kind_value, self.parent_value, self.ctrl_value):
            value.setObjectName("fieldValue")
        self.text_value = QLineEdit()
        self.text_value.setReadOnly(True)
        self.text_value.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.texture_value = QLineEdit()
        self.texture_value.setReadOnly(True)
        self.texture_value.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.atlas_button = QPushButton(self.tr("Abrir atlas DDS…"))
        self.atlas_button.setEnabled(False)
        self.atlas_button.clicked.connect(self.atlas_requested.emit)
        self.change_texture_button = QPushButton(self.tr("Trocar .dds…"))
        self.change_texture_button.setToolTip(
            self.tr("Usa outro .dds neste controle: um da UI, uma cópia para editar ou um de outra pasta")
        )
        self.change_texture_button.setEnabled(False)
        self.change_texture_button.clicked.connect(self.texture_change_requested.emit)
        self.uv_value = QLabel("—")
        self.font_value = QLabel("—")
        self.visible_value = QCheckBox()
        self.visible_value.setEnabled(False)

        self.lock_button = QToolButton()
        self.hide_button = QToolButton()
        self.isolate_button = QToolButton()
        self.actions_row = QWidget()
        actions_layout = QHBoxLayout(self.actions_row)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(6)
        for button in (self.lock_button, self.hide_button, self.isolate_button):
            button.setObjectName("inspectorAction")
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            actions_layout.addWidget(button)
        self.actions_row.setVisible(False)

        self.x_spin = self._spinbox()
        self.y_spin = self._spinbox()
        self.width_spin = self._spinbox(minimum=0)
        self.height_spin = self._spinbox(minimum=0)
        for spin in (self.x_spin, self.y_spin, self.width_spin, self.height_spin):
            spin.valueChanged.connect(self._emit_geometry)

        details_form = QFormLayout()
        geometry_form = QFormLayout()
        appearance_form = QFormLayout()
        for form in (details_form, geometry_form, appearance_form):
            form.setHorizontalSpacing(12)
            form.setVerticalSpacing(8)

        self._add_field(details_form, "WindowID", self.id_value)
        self._add_field(details_form, self.tr("Tipo"), self.kind_value)
        self._add_field(details_form, "ParentNode", self.parent_value)
        self._add_field(details_form, "CtrlType", self.ctrl_value)
        self._add_field(geometry_form, self.tr("Posição X"), self.x_spin)
        self._add_field(geometry_form, self.tr("Posição Y"), self.y_spin)
        self._add_field(geometry_form, self.tr("Largura"), self.width_spin)
        self._add_field(geometry_form, self.tr("Altura"), self.height_spin)
        self._add_field(appearance_form, self.tr("Visível no XML"), self.visible_value)
        self._add_field(appearance_form, self.tr("Texto"), self.text_value)
        self._add_field(appearance_form, self.tr("Fonte"), self.font_value)
        self.x_spin.setToolTip(self.tr("WindowLeft no XML"))
        self.y_spin.setToolTip(self.tr("WindowTop no XML"))
        self.width_spin.setToolTip(self.tr("WindowHeight no XML"))
        self.height_spin.setToolTip(self.tr("WindowWidth no XML"))

        explanation = QLabel(
            self.tr("O formato do jogo usa WindowHeight como largura visual e WindowWidth como altura visual.")
        )
        explanation.setWordWrap(True)
        explanation.setObjectName("panelSubtitle")

        self.kind_badge = QLabel()
        self.kind_badge.setObjectName("badge")
        self.id_caption = QLabel()
        self.id_caption.setObjectName("monoCaption")
        badge_row = QWidget()
        badge_layout = QHBoxLayout(badge_row)
        badge_layout.setContentsMargins(0, 0, 0, 0)
        badge_layout.setSpacing(8)
        badge_layout.addWidget(self.kind_badge)
        badge_layout.addWidget(self.id_caption)
        badge_layout.addStretch(1)
        self.badge_row = badge_row
        self.badge_row.setVisible(False)

        for spin, prefix in (
            (self.x_spin, "X   "),
            (self.y_spin, "Y   "),
            (self.width_spin, self.tr("L   ")),
            (self.height_spin, self.tr("A   ")),
        ):
            spin.setPrefix(prefix)
            spin.setObjectName("monoSpin")
            spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
            spin.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            spin.setMinimumWidth(64)
        geometry_grid = QGridLayout()
        geometry_grid.setHorizontalSpacing(8)
        geometry_grid.setVerticalSpacing(8)
        geometry_grid.addWidget(self.x_spin, 0, 0)
        geometry_grid.addWidget(self.y_spin, 0, 1)
        geometry_grid.addWidget(self.width_spin, 1, 0)
        geometry_grid.addWidget(self.height_spin, 1, 1)
        self.ghost_hint = QLabel(
            self.tr(
                "A área em vermelho é a janela principal: o jogo a mantém ali, invisível, "
                "e ela continua recebendo cliques e arraste."
            )
        )
        self.ghost_hint.setObjectName("hintBox")
        self.ghost_hint.setWordWrap(True)
        self.ghost_hint.setVisible(False)
        self.ghost_button = QPushButton(self.tr("Remover área invisível"))
        self.ghost_button.setToolTip(
            self.tr("Reduz a janela principal a 1 × 1 e ajusta o X/Y para o conteúdo continuar no mesmo lugar.")
        )
        self.ghost_button.setVisible(False)
        self.ghost_button.clicked.connect(self.ghost_fix_requested.emit)
        self.anchor_hint = QLabel()
        self.anchor_hint.setObjectName("hintBox")
        self.anchor_hint.setWordWrap(True)
        self.anchor_hint.setVisible(False)
        self.screen_position_label = QLabel()
        self.screen_position_label.setObjectName("monoCaption")
        self.screen_position_label.setToolTip(
            self.tr("Posição real na tela do jogo. Os campos acima são as coordenadas do XML, relativas à janela.")
        )
        self.screen_position_label.setVisible(False)

        self.atlas_button.setIcon(icon("image", "#ffffff"))
        self.atlas_button.setObjectName("accentPush")
        texture_form = QFormLayout()
        texture_form.setHorizontalSpacing(12)
        texture_form.setVerticalSpacing(8)
        self._add_field(texture_form, self.tr("Arquivo"), self.texture_value)
        self._add_field(texture_form, self.tr("Recorte DDS"), self.uv_value)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(self.badge_row)
        layout.addWidget(self.selection_title)
        layout.addWidget(self.selection_subtitle)
        # Bloquear/ocultar/isolar no topo: no fim do painel ninguém os encontrava.
        layout.addWidget(self.actions_row)
        self.details_container = QWidget()
        details_layout = QVBoxLayout(self.details_container)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(12)
        details_layout.addWidget(
            self._card(self.tr("POSIÇÃO E TAMANHO"), geometry_grid, self.screen_position_label, self.anchor_hint,
                self.ghost_hint, self.ghost_button,
            )
        )
        details_layout.addWidget(
            self._card(self.tr("TEXTURA"), texture_form, self.atlas_button, self.change_texture_button)
        )
        details_layout.addWidget(self._card(self.tr("IDENTIFICAÇÃO"), details_form))
        details_layout.addWidget(self._card(self.tr("APARÊNCIA"), appearance_form, explanation))
        layout.addWidget(self.details_container)
        layout.addStretch(1)
        self.details_container.setVisible(False)
        self.set_enabled(False)

    @staticmethod
    def _card(title: str, inner_layout, *widgets: QWidget) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 12, 12, 12)
        card_layout.setSpacing(10)
        label = QLabel(title)
        label.setObjectName("sectionLabel")
        card_layout.addWidget(label)
        if inner_layout is not None:
            card_layout.addLayout(inner_layout)
        for widget in widgets:
            card_layout.addWidget(widget)
        return card

    def set_ghost_warning(self, visible: bool) -> None:
        self.ghost_hint.setVisible(visible)
        self.ghost_button.setVisible(visible)

    def set_screen_position(self, position: tuple[int, int] | None) -> None:
        self.screen_position_label.setVisible(position is not None)
        if position is not None:
            self.screen_position_label.setText(self.tr("No jogo: X {x} · Y {y}").format(x=position[0], y=position[1]))

    def show_window_position(self, screen: tuple[int, int], xml: tuple[int, int]) -> None:
        """Janela posicionada pelo jogo: X/Y mostram onde ela aparece; o do XML vai na legenda."""
        for spin, value in zip((self.x_spin, self.y_spin), screen, strict=True):
            with QSignalBlocker(spin):
                spin.setValue(value)
        self.screen_position_label.setVisible(True)
        self.screen_position_label.setText(self.tr("No XML: X {x} · Y {y}").format(x=xml[0], y=xml[1]))

    def set_anchor_hint(self, text: str | None) -> None:
        self.anchor_hint.setText(text or "")
        self.anchor_hint.setVisible(bool(text))

    @staticmethod
    def _add_field(form: QFormLayout, label: str, value: QWidget) -> None:
        form.addRow(label, value)
        form.labelForField(value).setObjectName("fieldLabel")

    def set_context_actions(
        self, lock_action: QAction, hide_action: QAction, isolate_action: QAction, *structure_actions: QAction
    ) -> None:
        for button, action in zip(
            (self.lock_button, self.hide_button, self.isolate_button),
            (lock_action, hide_action, isolate_action),
            strict=True,
        ):
            button.setDefaultAction(action)
        # Duplicar/apagar numa segunda fileira, logo abaixo: cinco botões não cabem numa só.
        self.structure_row = QWidget()
        layout = QHBoxLayout(self.structure_row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        parent_layout = self.actions_row.parentWidget().layout()
        parent_layout.insertWidget(parent_layout.indexOf(self.actions_row) + 1, self.structure_row)
        self.structure_row.setVisible(self.actions_row.isVisibleTo(self))
        for action in structure_actions:
            button = QToolButton()
            button.setObjectName("inspectorAction")
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            button.setDefaultAction(action)
            layout.addWidget(button)

    @staticmethod
    def _spinbox(minimum: int = -100000) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(minimum, 100000)
        spin.setKeyboardTracking(True)
        return spin

    def set_enabled(self, enabled: bool) -> None:
        for spin in (self.x_spin, self.y_spin, self.width_spin, self.height_spin):
            spin.setEnabled(enabled)

    def set_element(self, element: UIElement | None) -> None:
        self._loading = True
        try:
            if element is None:
                self.screen_position_label.setVisible(False)
                self.actions_row.setVisible(False)
                getattr(self, "structure_row", self.actions_row).setVisible(False)
                self.badge_row.setVisible(False)
                self.selection_subtitle.setVisible(True)
                self.details_container.setVisible(False)
                self.selection_title.setText(self.tr("Nenhum elemento selecionado"))
                self.selection_subtitle.setText(
                    self.tr("Selecione um item no canvas ou na lista para editar sua geometria.")
                )
                self.id_value.setText("—")
                self.kind_value.setText("—")
                self.parent_value.setText("—")
                self.ctrl_value.setText("—")
                self.text_value.clear()
                self.texture_value.clear()
                self.uv_value.setText("—")
                self.atlas_button.setEnabled(False)
                self.change_texture_button.setEnabled(False)
                self.font_value.setText("—")
                self.visible_value.setChecked(False)
                self.set_enabled(False)
                return
            self.selection_title.setText(element.window_text or f"WindowID {element.window_id}")
            self.kind_badge.setText(kind_label(element.kind, element.ctrl_type))
            self.id_caption.setText(
                self.tr("dentro de {parent}").format(parent=element.parent_id) if element.parent_id else self.tr("raiz")
            )
            self.badge_row.setVisible(True)
            self.selection_subtitle.setVisible(False)
            self.actions_row.setVisible(True)
            getattr(self, "structure_row", self.actions_row).setVisible(True)
            self.details_container.setVisible(True)
            self.selection_subtitle.setText(kind_label(element.kind, element.ctrl_type))
            self.id_value.setText(element.window_id)
            self.kind_value.setText(kind_label(element.kind, element.ctrl_type))
            self.parent_value.setText(element.parent_id or "—")
            self.ctrl_value.setText(element.ctrl_type or "—")
            self.text_value.setText(element.window_text)
            self.texture_value.setText(element.texture_name or "")
            self.atlas_button.setEnabled(
                element.texture_name is not None and element.uv is not None
            )
            self.change_texture_button.setEnabled(element.original_texture_name is not None)
            self.uv_value.setText(
                (
                    f"X {element.uv.left} · Y {element.uv.top} · "
                    f"{element.uv.width} × {element.uv.height}"
                )
                if element.uv is not None
                else "—"
            )
            font = ""
            if element.font_color:
                font += f"cor {element.font_color}"
            if element.font_style:
                font += f" · estilo {element.font_style}"
            self.font_value.setText(font or "—")
            self.visible_value.setChecked(element.visible)
            for spin, value in zip(
                (self.x_spin, self.y_spin, self.width_spin, self.height_spin),
                element.geometry,
                strict=True,
            ):
                with QSignalBlocker(spin):
                    spin.setValue(value)
            self.set_enabled(True)
        finally:
            self._loading = False

    def _emit_geometry(self) -> None:
        if not self._loading:
            self.geometry_edited.emit(
                (self.x_spin.value(), self.y_spin.value(), self.width_spin.value(), self.height_spin.value())
            )


class GeometryCommand(QUndoCommand):
    def __init__(
        self,
        window: "EditorWindow",
        index: int,
        old: tuple[int, int, int, int],
        new: tuple[int, int, int, int],
    ):
        super().__init__(QCoreApplication.translate("EditorWindow", "Mover/redimensionar WindowID {id}").format(id=window.document.elements[index].window_id))
        self.window = window
        self.index = index
        self.old = old
        self.new = new

    def redo(self) -> None:
        self.window.apply_geometry(self.index, self.new)

    def undo(self) -> None:
        self.window.apply_geometry(self.index, self.old)


class GeometryBatchCommand(QUndoCommand):
    def __init__(
        self,
        window: "EditorWindow",
        changes: dict[
            int, tuple[tuple[int, int, int, int], tuple[int, int, int, int]]
        ],
    ):
        super().__init__(QCoreApplication.translate("EditorWindow", "Mover {count} elementos").format(count=len(changes)))
        self.window = window
        self.changes = changes

    def redo(self) -> None:
        for index, (_old, new) in self.changes.items():
            self.window.apply_geometry(index, new)

    def undo(self) -> None:
        for index, (old, _new) in self.changes.items():
            self.window.apply_geometry(index, old)


class UVCommand(QUndoCommand):
    def __init__(
        self,
        window: "EditorWindow",
        index: int,
        old: UVRect,
        new: UVRect,
    ):
        super().__init__(
            QCoreApplication.translate("EditorWindow", "Alterar recorte DDS do WindowID {id}").format(id=window.document.elements[index].window_id)
        )
        self.window = window
        self.index = index
        self.old = old
        self.new = new

    def redo(self) -> None:
        self.window.apply_uv(self.index, self.new)

    def undo(self) -> None:
        self.window.apply_uv(self.index, self.old)


class OffsetCommand(QUndoCommand):
    def __init__(self, window: "EditorWindow", index: int, old: tuple[int, int], new: tuple[int, int]):
        super().__init__(
            QCoreApplication.translate("EditorWindow", "Alterar SOffset do WindowID {id}").format(
                id=window.document.elements[index].window_id
            )
        )
        self.window = window
        self.index = index
        self.old = old
        self.new = new

    def redo(self) -> None:
        self.window.apply_offset(self.index, self.new)

    def undo(self) -> None:
        self.window.apply_offset(self.index, self.old)


class ButtonUVCommand(QUndoCommand):
    def __init__(self, window: "EditorWindow", index: int, state: str, old: UVRect, new: UVRect):
        super().__init__(state)
        self.window, self.index, self.state = window, index, state
        self.old, self.new = old, new

    def redo(self) -> None:
        self.window.apply_button_uv(self.index, self.state, self.new)

    def undo(self) -> None:
        self.window.apply_button_uv(self.index, self.state, self.old)


class EditorWindow(QMainWindow):
    def __init__(
        self,
        initial_path: Path | None = None,
        *,
        language: str = "pt_BR",
        restore_last_project: bool = False,
    ):
        super().__init__()
        load_fonts()
        self.language = language
        self.setWindowIcon(QIcon(str(APP_ICON_PATH)))
        self.document: UIDocument | None = None
        self.project: Project | None = None
        self.texture_cache: TextureCache | None = None
        self._texture_generation = 0
        self._texture_results: SimpleQueue = SimpleQueue()
        self._textures_pending: set[str] = set()
        self._texture_total = 0
        self._texture_timer = QTimer(self)
        self._texture_timer.setInterval(50)
        self._texture_timer.timeout.connect(self._apply_loaded_textures)
        self.items: dict[int, ElementItem] = {}
        self.tree_items: dict[int, QTreeWidgetItem] = {}
        self.selected_index: int | None = None
        self._syncing_selection = False
        self.locked_indexes: set[int] = set()
        self.hidden_indexes: set[int] = set()
        self.isolated_index: int | None = None
        self.atlas_dialog: AtlasDialog | None = None
        self.texture_watcher = QFileSystemWatcher(self)
        self.texture_watcher.fileChanged.connect(self._texture_file_changed)

        settings = QSettings("Local", "GF UI Editor")
        stored_resolution = str(settings.value("game_resolution", "game"))
        # "game": acompanha o client.ini do jogo (padrão); senão, um tamanho fixo.
        self.follow_game_resolution = stored_resolution == "game"
        self.game_resolution = (
            self._client_resolution() if self.follow_game_resolution else parse_resolution(stored_resolution)
        )
        background = str(settings.value("game_background", ""))
        self.game_background_path = Path(background) if background else None
        # "builtin": fundo do jogo embutido (padrão); "custom": captura própria; "none".
        self.background_mode = str(
            settings.value("background_mode", "custom" if self.game_background_path else "builtin")
        )
        self.game_screen_item: GameScreenItem | None = None
        self.game_drawn_item: GameDrawnItem | None = None
        self.reference_layer_items: list[ReferenceLayerItem] = []
        self._layer_documents: dict[Path, tuple[int, UIDocument]] = {}
        self.ghost_item: GhostAreaItem | None = None

        self.undo_stack = QUndoStack(self)
        self.scene = QGraphicsScene(self)
        self.view = EditorView(self.move_selected)
        self.view.setFrameShape(QFrame.Shape.NoFrame)
        self.view.setScene(self.scene)
        self.cursor_position_label = QLabel(self.tr("Mouse: X — · Y —"))
        self.cursor_position_label.setMinimumWidth(150)
        self.view.cursor_scene_moved.connect(self._show_cursor_position)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(self.tr("Pesquisar WindowID, tipo, texto ou textura…"))
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self.filter_tree)
        self.tree = QTreeWidget()
        self.tree.setObjectName("elementTree")
        self.tree.setHeaderLabels(["WindowID", self.tr("Tipo"), "ParentNode", self.tr("Estado")])
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.tree.itemSelectionChanged.connect(self._tree_selection_changed)
        # Estado primeiro, como as camadas de um editor de imagem: olho, cadeado e foco clicáveis.
        self.tree.header().moveSection(3, 0)
        self.tree.setMouseTracking(True)
        self.tree.setItemDelegateForColumn(3, ElementStateDelegate({
            ("hidden", False): icon("eye", size=16),
            ("hidden", True): icon("eye-off", COLORS["ACCENT_TEXT"], 16),
            ("locked", False): icon("lock", size=16),
            ("locked", True): icon("lock", COLORS["ACCENT_TEXT"], 16),
            ("isolated", False): icon("focus", size=16),
            ("isolated", True): icon("focus", COLORS["WARNING_TEXT"], 16),
        }, self.tree))
        self.tree.viewport().installEventFilter(self)
        elements_page = QWidget()
        elements_page.setObjectName("treePanel")
        tree_layout = QVBoxLayout(elements_page)
        tree_layout.setContentsMargins(10, 10, 10, 10)
        tree_layout.setSpacing(8)
        tree_layout.addWidget(self.search_edit)
        tree_layout.addWidget(self.tree)
        self.official_button = QPushButton(icon("plus"), self.tr("Adicionar do oficial…"))
        self.official_button.setToolTip(self.tr("Copia controles da UI oficial que este arquivo não tem"))
        self.official_button.setEnabled(False)
        self.official_button.clicked.connect(lambda: self.open_official_compare())
        self.new_image_button = QPushButton(icon("image"), self.tr("Nova imagem…"))
        self.new_image_button.setToolTip(self.tr("Cria um controle de imagem decorativo e abre o atlas para escolher o recorte"))
        self.new_image_button.setEnabled(False)
        self.new_image_button.clicked.connect(lambda: self.new_image())
        element_buttons = QHBoxLayout()
        element_buttons.setSpacing(6)
        element_buttons.addWidget(self.new_image_button)
        element_buttons.addWidget(self.official_button)
        tree_layout.addLayout(element_buttons)

        self.project_label = QLabel()
        self.project_label.setObjectName("panelTitle")
        self.project_path_label = QLabel()
        self.project_path_label.setObjectName("panelSubtitle")
        self.project_path_label.setWordWrap(True)
        self.file_filter_edit = QLineEdit()
        self.file_filter_edit.setPlaceholderText(self.tr("Filtrar arquivos…"))
        self.file_filter_edit.setClearButtonEnabled(True)
        self.file_filter_edit.textChanged.connect(self._filter_files)
        self.files_tree = QTreeWidget()
        self.files_tree.setObjectName("filesTree")
        self.files_tree.setHeaderHidden(True)
        self.files_tree.setColumnCount(2)
        self.files_tree.setRootIsDecorated(False)
        self.files_tree.setIndentation(0)
        self.files_tree.header().setStretchLastSection(False)
        self.files_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.files_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.files_tree.itemClicked.connect(self._file_activated)
        self.files_tree.itemChanged.connect(self._file_layer_toggled)
        self._layer_click = False
        self.files_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.files_tree.customContextMenuRequested.connect(self._files_context_menu)
        self.files_tree.itemActivated.connect(self._file_activated)
        self.files_tree.setCursor(Qt.CursorShape.PointingHandCursor)
        files_page = QWidget()
        files_page.setObjectName("treePanel")
        files_layout = QVBoxLayout(files_page)
        files_layout.setContentsMargins(10, 10, 10, 10)
        files_layout.setSpacing(6)
        files_layout.addWidget(self.project_label)
        files_layout.addWidget(self.project_path_label)
        self.project_paths_label = QLabel()
        self.project_paths_label.setObjectName("pathCaption")
        self.project_paths_label.setWordWrap(True)
        # Caminhos longos não podem alargar o painel; o texto completo fica na dica.
        self.project_paths_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.project_paths_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.project_paths_label.setVisible(False)
        files_layout.addWidget(self.project_paths_label)
        self.shared_publish_warning = QLabel()
        self.shared_publish_warning.setObjectName("warningHint")
        self.shared_publish_warning.setWordWrap(True)
        self.shared_publish_warning.setVisible(False)
        files_layout.addWidget(self.shared_publish_warning)
        self._official_diffs: dict[str, FileDiff] = {}
        self._official_unavailable = 0
        self._dismissed_banners: set[str] = set()
        self._scan_signals = _ScanSignals()
        self._scan_signals.done.connect(self._official_scan_done)
        self.loose_project_button = QPushButton(icon("folder-plus"), self.tr("Criar projeto com estes arquivos"))
        self.loose_project_button.setToolTip(
            self.tr("Copia a UI do jogo para um projeto com estes XML por cima; depois é só usar Enviar para o jogo.")
        )
        self.loose_project_button.setVisible(False)
        self.loose_project_button.clicked.connect(
            lambda: self.new_project(loose_dir=self._files_directory())
        )
        files_layout.addWidget(self.loose_project_button)
        # XML ou texturas: duas listas separadas em vez de uma seção escondida no fim.
        self.files_mode = "xml"
        segments = QWidget()
        segments.setObjectName("segmented")
        segments_layout = QHBoxLayout(segments)
        segments_layout.setContentsMargins(3, 3, 3, 3)
        segments_layout.setSpacing(2)
        self.files_mode_buttons = {}
        for mode, label in (("xml", self.tr("XML")), ("textures", self.tr("Texturas"))):
            button = QPushButton(label)
            button.setObjectName("segment")
            button.setCheckable(True)
            button.setChecked(mode == "xml")
            button.clicked.connect(lambda _checked=False, value=mode: self._set_files_mode(value))
            segments_layout.addWidget(button)
            self.files_mode_buttons[mode] = button
        segments.setVisible(False)
        self.files_mode_bar = segments
        files_layout.addWidget(segments)
        files_layout.addWidget(self.file_filter_edit)
        files_layout.addWidget(self.files_tree)

        self.side_tabs = QTabWidget()
        self.side_tabs.setObjectName("sideTabs")
        self.side_tabs.setDocumentMode(True)
        self.side_tabs.addTab(files_page, self.tr("Arquivos"))
        self.side_tabs.addTab(elements_page, self.tr("Elementos"))
        tree_panel = self.side_tabs
        self.properties = PropertyPanel()
        self.properties.geometry_edited.connect(self.edit_selected_geometry)
        self.properties.ghost_fix_requested.connect(self.remove_ghost_area)
        self.properties.atlas_requested.connect(self.open_selected_atlas)
        self.properties.texture_change_requested.connect(self.change_selected_texture)
        properties_scroll = QScrollArea()
        properties_scroll.setObjectName("propertiesScroll")
        properties_scroll.setFrameShape(QFrame.Shape.NoFrame)
        properties_scroll.setWidgetResizable(True)
        properties_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        properties_scroll.setWidget(self.properties)

        self.empty_page = self._build_empty_page()
        self.center_stack = QStackedWidget()
        self.center_stack.addWidget(self.empty_page)
        self.canvas_page = QWidget()
        canvas_layout = QVBoxLayout(self.canvas_page)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.setSpacing(0)
        self.official_banner = QFrame()
        self.official_banner.setObjectName("updateBanner")
        banner_layout = QHBoxLayout(self.official_banner)
        banner_layout.setContentsMargins(14, 8, 8, 8)
        banner_layout.setSpacing(10)
        banner_icon = QLabel()
        banner_icon.setPixmap(icon("info", COLORS["SELECTION_GOLD"], 18).pixmap(18, 18))
        self.official_banner_text = QLabel()
        self.official_banner_text.setWordWrap(True)
        banner_button = QPushButton(self.tr("Ver e adicionar"))
        banner_button.clicked.connect(lambda: self.open_official_compare())
        banner_close = QToolButton()
        banner_close.setIcon(icon("x", COLORS["WARNING_TEXT"], 16))
        banner_close.setAutoRaise(True)
        banner_close.setToolTip(self.tr("Dispensar"))
        banner_close.clicked.connect(self._dismiss_official_banner)
        banner_layout.addWidget(banner_icon)
        banner_layout.addWidget(self.official_banner_text, 1)
        banner_layout.addWidget(banner_button)
        banner_layout.addWidget(banner_close)
        self.official_banner.setVisible(False)
        canvas_layout.addWidget(self.official_banner)
        # Sem a UI oficial guardada o editor não percebe controles novos de uma atualização;
        # o chip do rodapé passa despercebido, então avisa aqui também.
        self.reference_banner = QFrame()
        self.reference_banner.setObjectName("updateBanner")
        reference_layout = QHBoxLayout(self.reference_banner)
        reference_layout.setContentsMargins(14, 8, 8, 8)
        reference_layout.setSpacing(10)
        reference_icon = QLabel()
        reference_icon.setPixmap(icon("info", COLORS["SELECTION_GOLD"], 18).pixmap(18, 18))
        reference_text = QLabel(
            self.tr(
                "A UI oficial desta versão do jogo não está guardada: sem ela o editor não avisa "
                "quando uma atualização traz controles novos."
            )
        )
        reference_text.setWordWrap(True)
        reference_button = QPushButton(self.tr("Guardar UI oficial"))
        reference_button.clicked.connect(lambda: self.open_official_reference())
        reference_close = QToolButton()
        reference_close.setIcon(icon("x", COLORS["WARNING_TEXT"], 16))
        reference_close.setAutoRaise(True)
        reference_close.setToolTip(self.tr("Dispensar"))
        reference_close.clicked.connect(self._dismiss_reference_banner)
        reference_layout.addWidget(reference_icon)
        reference_layout.addWidget(reference_text, 1)
        reference_layout.addWidget(reference_button)
        reference_layout.addWidget(reference_close)
        self.reference_banner.setVisible(False)
        self.reference_banner_dismissed = False
        canvas_layout.addWidget(self.reference_banner)
        canvas_layout.addWidget(self.view, 1)
        self.center_stack.addWidget(self.canvas_page)
        canvas_panel = self.center_stack

        splitter = QSplitter()
        splitter.addWidget(tree_panel)
        splitter.addWidget(canvas_panel)
        splitter.addWidget(properties_scroll)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([290, 830, 320])
        self.setCentralWidget(splitter)

        self._create_actions()
        self.properties.set_context_actions(
            self.lock_action, self.hide_action, self.isolate_action, self.duplicate_action, self.delete_action
        )
        self._create_menus_and_toolbar()
        self._build_canvas_overlays()
        self._sync_resolution_actions()
        self._build_status_chips()
        self._refresh_game_screen()
        self._apply_theme()
        install_pointer_cursors(self)
        self.resize(1500, 900)
        self.setWindowTitle("GF UI Editor")
        self.statusBar().addPermanentWidget(self.cursor_position_label)

        self._refresh_files()
        self._update_title()
        if restore_last_project:
            # Só na janela principal de verdade (não em testes nem na troca de idioma).
            QTimer.singleShot(2500, self._automatic_update_check)
        if initial_path is not None:
            self.open_document(initial_path)
        elif restore_last_project:
            last = str(QSettings("Local", "GF UI Editor").value("last_project", ""))
            if last and (Path(last) / "project.json").is_file():
                self.open_project(Path(last))

    def _create_actions(self) -> None:
        self.new_project_action = QAction(self.tr("Novo projeto…"), self)
        self.new_project_action.setShortcut("Ctrl+Shift+N")
        self.new_project_action.setIcon(icon("folder-plus", "#ffffff" if "folder-plus" == "play" else COLORS["ICON"]))
        self.new_project_action.setIconText(self.tr("Novo projeto"))
        self.new_project_action.triggered.connect(lambda: self.new_project())
        self.open_project_action = QAction(self.tr("Abrir projeto…"), self)
        self.open_project_action.setShortcut("Ctrl+Shift+O")
        self.open_project_action.setIcon(icon("folder-open", "#ffffff" if "folder-open" == "play" else COLORS["ICON"]))
        self.open_project_action.setIconText(self.tr("Projeto"))
        self.open_project_action.triggered.connect(self.choose_project)
        self.test_action = QAction(self.tr("Enviar para o jogo"), self)
        self.test_action.setShortcut("F5")
        self.test_action.setIcon(icon("send", "#ffffff"))
        self.test_action.setToolTip(
            self.tr("Publica o projeto em UICustom e na pasta UI do jogo e o seleciona no launcher (F5)")
        )
        self.test_action.setEnabled(False)
        self.test_action.triggered.connect(self.test_in_game)
        self.export_action = QAction(self.tr("Exportar UI (.zip)…"), self)
        self.export_action.setEnabled(False)
        self.export_action.triggered.connect(self.export_project_zip)
        self.import_action = QAction(self.tr("Importar arquivos…"), self)
        self.import_action.setIcon(icon("file-import"))
        self.import_action.setToolTip(
            self.tr("Importar arquivos avulsos para o projeto (substitui os de mesmo nome)")
        )
        self.import_action.setEnabled(False)
        self.import_action.triggered.connect(self.import_files)
        self.official_compare_action = QAction(self.tr("Comparar com a UI oficial…"), self)
        self.official_compare_action.setToolTip(
            self.tr("Mostra os controles da UI oficial que o XML aberto não tem")
        )
        self.official_compare_action.setEnabled(False)
        self.official_compare_action.triggered.connect(lambda: self.open_official_compare())
        self.game_error_action = QAction(self.tr("Resolver erro do jogo…"), self)
        self.game_error_action.setToolTip(
            self.tr("Cole a mensagem \"Child control can not found\" do jogo para achar o XML e o controle")
        )
        self.game_error_action.triggered.connect(self.resolve_game_error)
        self.project_folder_action = QAction(self.tr("Abrir pasta do projeto"), self)
        self.project_folder_action.setEnabled(False)
        self.project_folder_action.triggered.connect(
            lambda: self.project and QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.project.root)))
        )
        self.open_action = QAction(self.tr("Abrir XML…"), self)
        self.open_action.setIcon(icon("file"))
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_action.setIconText(self.tr("Abrir"))
        self.open_action.setToolTip(self.tr("Abrir XML (Ctrl+O)"))
        self.open_action.triggered.connect(self.choose_document)
        self.save_action = QAction(self.tr("Salvar com backup"), self)
        self.save_action.setIcon(icon("save", COLORS["TEXT_BRIGHT"]))
        self.save_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_action.setIconText(self.tr("Salvar"))
        self.save_action.setToolTip(self.tr("Salvar com backup (Ctrl+S)"))
        self.save_action.setEnabled(False)
        self.save_action.triggered.connect(self.save_document)
        self.undo_action = self.undo_stack.createUndoAction(self, self.tr("Desfazer"))
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.undo_action.setIcon(icon("undo"))
        self.redo_action = self.undo_stack.createRedoAction(self, self.tr("Refazer"))
        self.redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self.redo_action.setIcon(icon("redo"))
        self.fit_action = QAction(self.tr("Enquadrar"), self)
        self.fit_action.setIcon(icon("frame"))
        self.fit_action.setShortcut("F")
        self.fit_action.setEnabled(False)
        self.fit_action.triggered.connect(self.fit_scene)
        self.labels_action = QAction(self.tr("Mostrar identificadores"), self)
        self.labels_action.setCheckable(True)
        self.labels_action.setChecked(False)
        self.labels_action.setShortcut("I")
        self.labels_action.setIcon(icon("type"))
        self.labels_action.setToolTip(self.tr("Mostrar identificadores (I)"))
        self.labels_action.toggled.connect(self.set_labels_visible)
        # Texto no canvas como o jogo desenha. A maior parte dos textos vem do código do jogo,
        # então as amostras servem para ver se cabem na caixa.
        self.text_mode = "off"
        self.text_mode_actions = QActionGroup(self)
        self.text_mode_menu = QMenu(self.tr("Texto como no jogo"), self)
        for mode, label in (
            ("off", self.tr("Desligado")),
            ("game", self.tr("Textos do jogo")),
            ("xml", self.tr("Só o texto do XML")),
            ("short", self.tr("Amostra curta")),
            ("long", self.tr("Amostra longa")),
        ):
            action = QAction(label, self, checkable=True)
            action.setChecked(mode == "off")
            action.triggered.connect(lambda _checked=False, value=mode: self.set_text_mode(value))
            self.text_mode_actions.addAction(action)
            self.text_mode_menu.addAction(action)
        self.textures_action = QAction(self.tr("Mostrar texturas"), self)
        self.textures_action.setCheckable(True)
        self.textures_action.setChecked(True)
        self.textures_action.setShortcut("T")
        self.textures_action.toggled.connect(self.set_textures_visible)
        self.atlas_action = QAction(self.tr("Abrir atlas DDS…"), self)
        self.atlas_action.setEnabled(False)
        self.atlas_action.triggered.connect(self.open_selected_atlas)
        self.reload_textures_action = QAction(self.tr("Atualizar arquivos e texturas"), self)
        self.reload_textures_action.setToolTip(
            self.tr("Atualiza a lista de XMLs e recarrega as texturas do disco (Ctrl+R)")
        )
        self.reload_textures_action.setShortcut("Ctrl+R")
        self.reload_textures_action.setIcon(icon("refresh"))
        self.reload_textures_action.setEnabled(False)
        self.reload_textures_action.triggered.connect(self.reload_all_textures)
        self.watch_textures_action = QAction(self.tr("Atualizar DDS automaticamente"), self)
        self.watch_textures_action.setCheckable(True)
        self.watch_textures_action.setChecked(True)
        self.watch_textures_action.toggled.connect(self._watch_texture_files)
        self.preview_action = QAction(self.tr("Preview do jogo"), self)
        self.preview_action.setCheckable(True)
        self.preview_action.setShortcut("P")
        self.preview_action.setIcon(icon("eye"))
        self.preview_action.setToolTip(
            self.tr("Esconde contornos e rótulos do editor para ver a interface como no jogo (P)")
        )
        self.preview_action.toggled.connect(self.set_preview_mode)
        self.resolution_actions = QActionGroup(self)
        self.resolution_actions.setExclusive(True)
        self.resolution_game_action = QAction(self.tr("Igual ao jogo (client.ini)"), self)
        self.resolution_game_action.setCheckable(True)
        self.resolution_game_action.triggered.connect(self.follow_client_resolution)
        self.resolution_actions.addAction(self.resolution_game_action)
        self.resolution_off_action = QAction(self.tr("Sem moldura"), self)
        self.resolution_off_action.setCheckable(True)
        self.resolution_off_action.triggered.connect(lambda: self.set_game_resolution(None))
        self.resolution_actions.addAction(self.resolution_off_action)
        self.resolution_preset_actions: dict[tuple[int, int], QAction] = {}
        for width, height in GAME_RESOLUTIONS:
            action = QAction(f"{width} × {height}", self)
            action.setCheckable(True)
            action.triggered.connect(
                lambda _checked, size=(width, height): self.set_game_resolution(size)
            )
            self.resolution_actions.addAction(action)
            self.resolution_preset_actions[(width, height)] = action
        self.resolution_custom_action = QAction(self.tr("Personalizada…"), self)
        self.resolution_custom_action.setCheckable(True)
        self.resolution_custom_action.triggered.connect(self.choose_custom_resolution)
        self.resolution_actions.addAction(self.resolution_custom_action)
        self.saved_positions_action = QAction(self.tr("Usar posições salvas do User.ini"), self)
        self.saved_positions_action.setCheckable(True)
        self.saved_positions_action.setChecked(True)
        self.saved_positions_action.setToolTip(
            self.tr("Janelas arrastadas no jogo ficam na posição gravada no User.ini da pasta do jogo")
        )
        self.saved_positions_action.toggled.connect(lambda _checked: self._place_game_screen())
        # Marcação das áreas que o jogo desenha sozinho (foto do personagem): ajuda a encaixar a
        # moldura, mas polui a tela quando não se está mexendo nisso.
        self.game_drawn_action = QAction(self.tr("Foto"), self)
        self.game_drawn_action.setCheckable(True)
        self.game_drawn_action.setChecked(True)
        self.game_drawn_action.setToolTip(self.tr("Mostrar onde o jogo desenha a foto do personagem"))
        self.game_drawn_action.toggled.connect(self._sync_game_drawn_visibility)
        self.background_actions = QActionGroup(self)
        self.background_actions.setExclusive(True)
        self.builtin_background_action = QAction(self.tr("Fundo do jogo (embutido)"), self)
        self.builtin_background_action.triggered.connect(lambda: self.set_background_mode("builtin"))
        self.background_action = QAction(self.tr("Captura própria…"), self)
        self.background_action.triggered.connect(self.choose_game_background)
        self.no_background_action = QAction(self.tr("Sem fundo"), self)
        self.no_background_action.triggered.connect(lambda: self.set_background_mode("none"))
        for action in (self.builtin_background_action, self.background_action, self.no_background_action):
            action.setCheckable(True)
            self.background_actions.addAction(action)
        self._sync_background_actions()
        self._sync_resolution_actions()
        self.lock_action = QAction(self.tr("Bloquear selecionado"), self)
        self.lock_action.setShortcut("Ctrl+Shift+L")
        self.lock_action.setIcon(icon("lock", size=16))
        self.lock_action.setIconText(self.tr("Bloquear"))
        self.lock_action.setEnabled(False)
        self.lock_action.triggered.connect(self.toggle_selected_lock)
        self.hide_action = QAction(self.tr("Ocultar selecionado"), self)
        self.hide_action.setShortcut("Ctrl+Shift+H")
        self.hide_action.setIcon(icon("eye-off", size=16))
        self.hide_action.setIconText(self.tr("Ocultar"))
        self.hide_action.setEnabled(False)
        self.hide_action.triggered.connect(self.toggle_selected_hidden)
        self.isolate_action = QAction(self.tr("Isolar selecionado"), self)
        self.isolate_action.setShortcut("Ctrl+Shift+I")
        self.isolate_action.setIcon(icon("focus", size=16))
        self.isolate_action.setIconText(self.tr("Isolar"))
        self.isolate_action.setEnabled(False)
        self.isolate_action.triggered.connect(self.toggle_isolation)
        self.duplicate_action = QAction(self.tr("Duplicar controle"), self)
        self.duplicate_action.setShortcut("Ctrl+D")
        self.duplicate_action.setIcon(icon("copy", size=16))
        self.duplicate_action.setIconText(self.tr("Duplicar"))
        self.duplicate_action.setToolTip(self.tr("Cria uma cópia decorativa deste controle com um WindowID livre"))
        self.duplicate_action.setEnabled(False)
        self.duplicate_action.triggered.connect(self.duplicate_selected)
        self.delete_action = QAction(self.tr("Apagar controle"), self)
        self.delete_action.setShortcut("Delete")
        self.delete_action.setIcon(icon("trash", size=16))
        self.delete_action.setIconText(self.tr("Apagar"))
        self.delete_action.setEnabled(False)
        self.delete_action.triggered.connect(self.delete_selected)
        self.game_hide_action = QAction(self.tr("Ocultar no jogo"), self)
        self.game_hide_action.setCheckable(True)
        self.game_hide_action.setToolTip(self.tr("Grava Visible=\"0\": o controle continua no XML, mas o jogo não o mostra"))
        self.game_hide_action.setEnabled(False)
        self.game_hide_action.triggered.connect(self.toggle_selected_game_visibility)
        self.deselect_action = QAction(self.tr("Desmarcar seleção"), self)
        self.deselect_action.setShortcut("Esc")
        self.deselect_action.triggered.connect(self.clear_selection)
        self.new_image_action = QAction(self.tr("Nova imagem…"), self)
        self.new_image_action.setIcon(icon("image", size=16))
        self.new_image_action.setEnabled(False)
        self.new_image_action.triggered.connect(self.new_image)

    def _create_menus_and_toolbar(self) -> None:
        file_menu = self.menuBar().addMenu(self.tr("Arquivo"))
        file_menu.addAction(self.new_project_action)
        file_menu.addAction(self.open_project_action)
        self.recent_menu = file_menu.addMenu(self.tr("Projetos recentes"))
        self.recent_menu.aboutToShow.connect(self._fill_recent_menu)
        self.home_action = QAction(self.tr("Tela inicial"), self)
        self.home_action.setToolTip(self.tr("Fecha o XML aberto e mostra os projetos recentes"))
        self.home_action.triggered.connect(self.go_home)
        file_menu.addAction(self.home_action)
        file_menu.addSeparator()
        file_menu.addAction(self.open_action)
        file_menu.addAction(self.save_action)
        project_menu = self.menuBar().addMenu(self.tr("Projeto"))
        project_menu.addAction(self.test_action)
        project_menu.addAction(self.import_action)
        self.official_reference_action = QAction(self.tr("UI oficial de referência…"), self)
        self.official_reference_action.triggered.connect(lambda: self.open_official_reference())
        project_menu.addAction(self.official_reference_action)
        project_menu.addAction(self.official_compare_action)
        project_menu.addAction(self.game_error_action)
        project_menu.addAction(self.export_action)
        self.publish_folder_action = QAction(self.tr("Pasta de publicação…"), self)
        self.publish_folder_action.setEnabled(False)
        self.publish_folder_action.triggered.connect(self.choose_publish_folder)
        project_menu.addAction(self.publish_folder_action)
        project_menu.addSeparator()
        project_menu.addAction(self.project_folder_action)
        edit_menu = self.menuBar().addMenu(self.tr("Editar"))
        edit_menu.addAction(self.undo_action)
        edit_menu.addAction(self.redo_action)
        edit_menu.addAction(self.deselect_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.new_image_action)
        edit_menu.addAction(self.duplicate_action)
        edit_menu.addAction(self.delete_action)
        edit_menu.addAction(self.game_hide_action)
        view_menu = self.menuBar().addMenu(self.tr("Visualização"))
        view_menu.addAction(self.fit_action)
        view_menu.addAction(self.labels_action)
        view_menu.addMenu(self.text_mode_menu)
        view_menu.addAction(self.textures_action)
        view_menu.addAction(self.atlas_action)
        view_menu.addAction(self.reload_textures_action)
        view_menu.addAction(self.watch_textures_action)
        view_menu.addSeparator()
        view_menu.addAction(self.preview_action)
        resolution_menu = view_menu.addMenu(self.tr("Resolução do jogo"))
        self.resolution_menu = resolution_menu
        resolution_menu.addAction(self.resolution_game_action)
        resolution_menu.addAction(self.resolution_off_action)
        resolution_menu.addSeparator()
        for action in self.resolution_preset_actions.values():
            resolution_menu.addAction(action)
        resolution_menu.addAction(self.resolution_custom_action)
        resolution_menu.addSeparator()
        resolution_menu.addAction(self.saved_positions_action)
        resolution_menu.addSeparator()
        resolution_menu.addAction(self.builtin_background_action)
        resolution_menu.addAction(self.background_action)
        resolution_menu.addAction(self.no_background_action)
        root_mode_menu = view_menu.addMenu(self.tr("Posição da janela no preview"))
        root_mode_menu.setToolTipsVisible(True)
        self.root_mode_actions = QActionGroup(self)
        self.root_mode_actions.setExclusive(True)
        for mode, label in (
            ("auto", self.tr("Automática (como o jogo)")),
            ("xml", self.tr("X e Y do XML")),
            ("center", self.tr("Centralizada")),
        ):
            action = QAction(label, self)
            action.setCheckable(True)
            action.setData(mode)
            action.setToolTip(
                self.tr("Use se o jogo do seu servidor posicionar esta janela de um jeito diferente do automático.")
            )
            action.triggered.connect(lambda _checked, value=mode: self.set_root_mode(value))
            self.root_mode_actions.addAction(action)
            root_mode_menu.addAction(action)
        root_mode_menu.aboutToShow.connect(self._sync_root_mode_actions)
        navigation_menu = view_menu.addMenu(self.tr("Navegação do canvas"))
        navigation_actions = QActionGroup(self)
        navigation_actions.setExclusive(True)
        saved_style = str(QSettings("Local", "GF UI Editor").value("navigation_style", "corel"))
        if saved_style not in EditorView.NAVIGATION_STYLES:
            saved_style = "corel"
        self.view.navigation_style = saved_style
        for style, label, tip in (
            ("corel", self.tr("Estilo CorelDRAW"), self.tr("Roda: zoom · botão do meio ou Espaço+arrastar: mover")),
            ("paintnet", self.tr("Estilo Paint.NET"), self.tr("Roda: rolar · Shift+roda: para os lados · Ctrl+roda: zoom")),
            ("photoshop", self.tr("Estilo Photoshop"), self.tr("Roda: rolar · Ctrl+roda: para os lados · Alt+roda: zoom")),
        ):
            action = QAction(label, self)
            action.setCheckable(True)
            action.setChecked(style == saved_style)
            action.setToolTip(tip)
            action.setStatusTip(tip)
            action.triggered.connect(lambda _checked, value=style: self.set_navigation_style(value))
            navigation_actions.addAction(action)
            navigation_menu.addAction(action)
        navigation_menu.setToolTipsVisible(True)
        view_menu.addSeparator()
        view_menu.addAction(self.lock_action)
        view_menu.addAction(self.hide_action)
        view_menu.addAction(self.isolate_action)
        help_menu = self.menuBar().addMenu(self.tr("Ajuda"))
        self.language_button = QToolButton(self.menuBar())
        self.language_button.setObjectName("languageButton")
        self.language_button.setText(self.tr("Idioma"))
        self.language_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        language_menu = QMenu(self.language_button)
        language_actions = QActionGroup(self)
        language_actions.setExclusive(True)
        for code, label in LANGUAGE_NAMES:
            action = language_menu.addAction(label)
            action.setData(code)
            action.setCheckable(True)
            action.setChecked(code == self.language)
            language_actions.addAction(action)
            action.triggered.connect(lambda _checked, selected=code: self._choose_language(selected))
        self.language_button.setMenu(language_menu)
        self.menuBar().setCornerWidget(self.language_button, Qt.Corner.TopRightCorner)
        self.about_action = QAction(self.tr("Sobre o GF UI Editor…"), self)
        self.about_action.triggered.connect(self.show_about)
        self.update_action = QAction(self.tr("Verificar atualizações…"), self)
        self.update_action.triggered.connect(lambda: self.check_for_updates(manual=True))
        self.auto_update_action = QAction(self.tr("Verificar ao iniciar"), self)
        self.auto_update_action.setCheckable(True)
        self.auto_update_action.setChecked(
            QSettings("Local", "GF UI Editor").value("auto_update_check", "true") == "true"
        )
        self.auto_update_action.toggled.connect(
            lambda on: QSettings("Local", "GF UI Editor").setValue("auto_update_check", "true" if on else "false")
        )
        self.how_to_action = QAction(self.tr("Como usar"), self)
        self.how_to_action.setShortcut(QKeySequence.StandardKey.HelpContents)
        self.how_to_action.triggered.connect(self.show_how_to)
        help_menu.addAction(self.how_to_action)
        self.whats_new_action = QAction(self.tr("Novidades desta versão"), self)
        self.whats_new_action.triggered.connect(self.show_whats_new)
        help_menu.addAction(self.whats_new_action)
        help_menu.addAction(self.update_action)
        help_menu.addAction(self.auto_update_action)
        help_menu.addSeparator()
        help_menu.addAction(self.about_action)
        toolbar = self.addToolBar("Principal")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(18, 18))
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        toolbar.addAction(self.new_project_action)
        toolbar.addAction(self.open_project_action)
        toolbar.addAction(self.import_action)
        toolbar.addAction(self.save_action)
        toolbar.addSeparator()
        toolbar.addAction(self.undo_action)
        toolbar.addAction(self.redo_action)
        toolbar.addSeparator()
        toolbar.addAction(self.labels_action)
        toolbar.addAction(self.reload_textures_action)
        for spacer_index in range(2):
            spacer = QWidget()
            spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            spacer.setObjectName("transparent")
            toolbar.addWidget(spacer)
            if spacer_index == 0:
                self.breadcrumb = QLabel()
                self.breadcrumb.setObjectName("breadcrumb")
                self.breadcrumb.setTextFormat(Qt.TextFormat.RichText)
                self.breadcrumb_action = toolbar.addWidget(self.breadcrumb)
        toolbar.addAction(self.test_action)
        for action, name in ((self.save_action, "saveButton"), (self.test_action, "accentButton")):
            button = toolbar.widgetForAction(action)
            button.setObjectName(name)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.main_toolbar = toolbar

    # ---- atualização ----------------------------------------------------------
    def _automatic_update_check(self) -> None:
        settings = QSettings("Local", "GF UI Editor")
        if settings.value("auto_update_check", "true") != "true":
            return
        last = float(settings.value("last_update_check", 0) or 0)
        if time.time() - last < 24 * 3600:
            return
        settings.setValue("last_update_check", time.time())
        self.check_for_updates(manual=False)

    def check_for_updates(self, manual: bool) -> None:
        """Consulta a release mais recente sem travar a janela."""
        results: SimpleQueue = SimpleQueue()

        def run() -> None:
            try:
                results.put(("ok", updater.check_for_update()))
            except updater.UpdateError as exc:
                results.put(("error", exc))

        Thread(target=run, name="gf-ui-update-check", daemon=True).start()
        if manual:
            self.statusBar().showMessage(self.tr("Verificando atualizações…"))
        timer = QTimer(self)
        timer.setInterval(150)

        def poll() -> None:
            try:
                status, value = results.get_nowait()
            except Empty:
                return
            timer.stop()
            timer.deleteLater()
            if status == "error":
                if manual:
                    QMessageBox.warning(
                        self,
                        self.tr("Atualizações"),
                        self.tr("Não foi possível verificar atualizações.\n\n{error}").format(error=value),
                    )
                return
            if value is None:
                if manual:
                    self.statusBar().clearMessage()
                    QMessageBox.information(
                        self,
                        self.tr("Atualizações"),
                        self.tr("Você já está na versão mais recente ({version}).").format(version=__version__),
                    )
                return
            skipped = QSettings("Local", "GF UI Editor").value("skipped_update_version", "")
            if not manual and skipped == value.version:
                return
            self._offer_update(value)

        timer.timeout.connect(poll)
        timer.start()

    def _offer_update(self, info: "updater.UpdateInfo") -> None:
        dialog = WhatsNewDialog(
            info.version,
            info.structured_notes,
            self.language,
            current_version=__version__,
            fallback_text=info.notes,
            can_install=updater.is_installed_build(),
            parent=self,
        )
        dialog.exec()
        if dialog.choice == SKIP:
            QSettings("Local", "GF UI Editor").setValue("skipped_update_version", info.version)
        elif dialog.choice == UPDATE:
            self._install_update(info)

    def show_how_to(self) -> None:
        steps = [
            (
                self.tr("Crie um projeto"),
                self.tr(
                    "Arquivo → Novo projeto. Dê um nome e escolha de onde partir: a UI em uso, uma UI da lista "
                    "(UICustom/…) ou \"Outra pasta…\" se os seus arquivos estão em outro lugar. O editor copia os "
                    "arquivos para o projeto; a pasta original não é alterada."
                ),
            ),
            (
                self.tr("Edite e salve"),
                self.tr(
                    "Abra um XML na aba Arquivos, mova e ajuste os elementos e salve com Ctrl+S. Cada salvamento "
                    "guarda um backup: clique com o botão direito no arquivo para restaurar uma versão anterior."
                ),
            ),
            (
                self.tr("Envie para o jogo com F5"),
                self.tr(
                    "Salvar grava só no projeto. Enviar para o jogo (F5) copia a sua UI para a pasta do jogo e a "
                    "seleciona no launcher; depois inicie o jogo pelo launcher. Se o launcher já estiver aberto, "
                    "escolha a sua UI na lista dele antes de clicar em Jogar."
                ),
            ),
            (
                self.tr("Entenda o preview"),
                self.tr(
                    "A moldura mostra a tela do jogo na sua resolução. Algumas janelas o jogo fixa "
                    "(no centro ou num canto): nelas, arraste a janela para onde o conteúdo deve aparecer "
                    "e o editor ajusta o X/Y que o jogo espera."
                ),
            ),
            (
                self.tr("Compartilhe"),
                self.tr(
                    "Projeto → Exportar UI (.zip) gera o pacote que outras pessoas adicionam no launcher em "
                    "\"Adicionar UI Customizada\"."
                ),
            ),
        ]
        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr("Como usar"))
        dialog.setMinimumWidth(600)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(16)
        title = QLabel(self.tr("Do projeto ao jogo em cinco passos"))
        title.setObjectName("heroTitle")
        layout.addWidget(title)
        for number, (heading, text) in enumerate(steps, 1):
            row = QHBoxLayout()
            row.setSpacing(14)
            badge = QLabel(str(number))
            badge.setObjectName("stepBadge")
            badge.setFixedSize(26, 26)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            body = QLabel(
                f"<span style='color:{COLORS['TEXT_BRIGHT']};font-weight:600'>{escape(heading)}</span><br>"
                f"<span style='color:{COLORS['TEXT_PRIMARY']}'>{escape(text)}</span>"
            )
            body.setTextFormat(Qt.TextFormat.RichText)
            body.setWordWrap(True)
            body.setObjectName("noteEntry")
            row.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
            row.addWidget(body, 1)
            layout.addLayout(row)
        close = QPushButton(self.tr("Fechar"))
        close.setObjectName("accentPush")
        close.setDefault(True)
        close.clicked.connect(dialog.accept)
        footer = QHBoxLayout()
        footer.addStretch(1)
        footer.addWidget(close)
        layout.addLayout(footer)
        install_pointer_cursors(dialog)
        dialog.exec()

    def show_whats_new(self) -> None:
        WhatsNewDialog(__version__, release_notes.bundled(), self.language, parent=self).exec()

    def _install_update(self, info: "updater.UpdateInfo") -> None:
        if not updater.is_installed_build():
            QDesktopServices.openUrl(QUrl(info.page_url))
            return
        if not self._save_before_project_action():
            return
        try:
            installer = self._run_with_progress(
                self.tr("Baixando a versão {version}…").format(version=info.version),
                lambda progress: updater.download_installer(info, progress=progress),
            )
        except updater.UpdateError as exc:
            QMessageBox.critical(
                self, self.tr("Falha na atualização"), self.tr("A atualização foi cancelada.\n\n{error}").format(error=exc)
            )
            return
        try:
            updater.launch_installer(installer)
        except OSError as exc:
            QMessageBox.critical(self, self.tr("Falha na atualização"), str(exc))
            return
        # O instalador fecha o que restar e reabre o editor ao terminar.
        self._closing_for_language = True
        QApplication.instance().quit()

    def show_about(self) -> None:
        AboutDialog(self).exec()

    def _choose_language(self, language: str) -> None:
        if language == self.language or language not in LANGUAGES:
            return
        if not self._save_before_project_action():
            self._sync_language_menu()
            return
        QSettings("Local", "GF UI Editor").setValue("language", language)
        application = QApplication.instance()
        switch_language(application, language)
        # Os textos são definidos ao montar a janela: recriá-la aplica o idioma
        # sem reiniciar, reabrindo o mesmo projeto e o mesmo XML.
        window = EditorWindow(language=language)
        if self.project is not None:
            window.open_project(self.project.root)
        if self.document is not None:
            window.open_document(self.document.path)
        window.set_game_resolution(self.game_resolution)
        window.preview_action.setChecked(self.preview_action.isChecked())
        window.restoreGeometry(self.saveGeometry())
        window.show()
        application._main_window = window
        self._closing_for_language = True
        self.close()

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            stylesheet(
                """
            * { font-family: "${UI_FONT}", "Segoe UI", sans-serif; }
            QMainWindow, QWidget {
                background: ${WINDOW_BG};
                color: ${TEXT_PRIMARY};
                font-size: 13px;
            }
            QWidget#transparent, QWidget#emptyPage QWidget#transparent { background: transparent; }
            QMenuBar, QStatusBar { background: ${CHROME_BG}; color: ${TEXT_MUTED}; }
            QMenuBar { border-bottom: 1px solid ${BORDER_CHROME}; padding: 2px 6px; }
            QMenuBar::item { padding: 5px 9px; border-radius: 6px; background: transparent; }
            QMenuBar::item:selected { background: ${MENU_HOVER_BG}; color: ${TEXT_BRIGHT}; }
            QMenu {
                background: ${CHIP_BG};
                color: ${TEXT_PRIMARY};
                border: 1px solid ${BORDER_INPUT};
                border-radius: 8px;
                padding: 5px;
            }
            QMenu::item { padding: 6px 22px 6px 12px; border-radius: 5px; }
            QMenu::item:selected { background: ${ACCENT_SOFT_BG}; color: ${TEXT_BRIGHT}; }
            QMenu::separator { height: 1px; background: ${BORDER_INPUT}; margin: 5px 6px; }
            QMenu::item:disabled, QMenu::item:selected:disabled,
            QMenuBar::item:disabled, QMenuBar::item:selected:disabled {
                color: ${TEXT_DISABLED};
                background: transparent;
            }
            QToolBar {
                background: ${WINDOW_BG};
                border: 0;
                border-bottom: 1px solid ${BORDER_CHROME};
                spacing: 4px;
                padding: 6px 10px;
            }
            QToolBar::separator { width: 1px; background: ${BORDER_INPUT}; margin: 7px 6px; }
            QToolButton {
                background: transparent;
                border: 1px solid transparent;
                border-radius: 8px;
                padding: 6px;
                color: ${TEXT_PRIMARY};
            }
            QToolButton:hover { background: ${BUTTON_HOVER_BG}; border-color: ${BUTTON_HOVER_BORDER}; }
            QToolButton:pressed, QToolButton:checked { background: ${ACCENT_SOFT_BG}; color: ${ACCENT_TEXT}; }
            QToolButton:disabled { color: ${TEXT_DISABLED}; }
            QToolButton#saveButton {
                background: ${BUTTON_HOVER_BG};
                border-color: ${BORDER_INPUT};
                color: ${TEXT_BRIGHT};
                font-weight: 500;
                padding: 6px 12px;
            }
            QToolButton#saveButton:disabled { color: ${TEXT_DISABLED}; background: transparent; }
            QToolButton#accentButton {
                background: ${ACCENT_BG};
                color: ${WHITE};
                border: 0;
                font-weight: 600;
                padding: 7px 16px;
            }
            QToolButton#accentButton:hover { background: ${ACCENT_HOVER_BG}; }
            QToolButton#accentButton:disabled { background: ${BUTTON_HOVER_BG}; color: ${TEXT_DISABLED}; }
            QLabel#breadcrumb {
                background: ${CHIP_BG};
                border: 1px solid ${BORDER_INPUT};
                border-radius: 8px;
                padding: 5px 12px;
                color: ${TEXT_MUTED};
            }
            QToolButton#languageButton {
                background: transparent;
                border-color: ${BORDER_INPUT};
                margin: 2px 6px 2px 0;
                padding: 3px 9px;
            }
            QPushButton {
                background: ${BUTTON_HOVER_BG};
                color: ${TEXT_PRIMARY};
                border: 1px solid ${BORDER_INPUT};
                border-radius: 7px;
                padding: 7px 12px;
            }
            QPushButton:hover { border-color: ${SCROLLBAR_HANDLE}; color: ${TEXT_BRIGHT}; }
            QPushButton:disabled, QCheckBox:disabled { color: ${TEXT_DISABLED}; }
            QPushButton#startCard, QPushButton#accentCard {
                background: ${CARD_BG};
                border-radius: 12px;
                padding: 16px;
                text-align: left;
                color: ${TEXT_MUTED};
            }
            QPushButton#accentCard { border-color: ${ACCENT_BG}; }
            QPushButton#startCard:hover, QPushButton#accentCard:hover { background: ${BUTTON_HOVER_BG}; color: ${TEXT_PRIMARY}; }
            QWidget#recentBox { background: ${PANEL_BG}; border: 1px solid ${CARD_BORDER}; border-radius: 12px; }
            QPushButton#recentRow {
                background: transparent;
                border: 0;
                border-bottom: 1px solid ${BORDER_PANEL};
                border-radius: 0;
                padding: 10px 14px;
                text-align: left;
                color: ${TEXT_MUTED};
            }
            QPushButton#recentRow:hover { background: ${BUTTON_HOVER_BG}; color: ${TEXT_PRIMARY}; }
            QWidget#emptyPage { background: ${CANVAS_BG}; }
            QLabel#cardHeading { font-size: 15px; font-weight: 600; color: ${TEXT_BRIGHT}; background: transparent; }
            QPushButton#startCard QLabel, QPushButton#accentCard QLabel { background: transparent; }
            QLabel#heroTitle { font-size: 26px; font-weight: 600; color: ${TEXT_BRIGHT}; background: transparent; }
            QLabel#heroSubtitle { font-size: 14px; color: ${TEXT_MUTED}; background: transparent; }
            QWidget#treePanel, QWidget#propertiesPanel, QScrollArea#propertiesScroll { background: ${PANEL_BG}; }
            QLabel#sectionLabel {
                color: ${TEXT_SECTION};
                font-size: 10px;
                font-weight: 600;
                letter-spacing: 1px;
                background: transparent;
            }
            QLabel#panelTitle { color: ${TEXT_TITLE}; font-size: 16px; font-weight: 600; background: transparent; }
            QLabel#panelSubtitle, QLabel#canvasHint { color: ${TEXT_SUBTITLE}; background: transparent; }
            QLabel#fieldLabel { color: ${TEXT_SUBTITLE}; background: transparent; }
            QLabel#fieldValue { color: ${TEXT_BRIGHT}; font-weight: 500; background: transparent; }
            QLabel#pathCaption {
                font-family: "${MONO_FONT}", Consolas, monospace;
                font-size: 11px;
                color: ${TEXT_MUTED};
                background: transparent;
            }
            QLabel#monoCaption, QLabel#zoomLabel {
                font-family: "${MONO_FONT}", Consolas, monospace;
                font-size: 12px;
                color: ${TEXT_MUTED};
                background: transparent;
            }
            QLabel#zoomLabel { color: ${TEXT_BRIGHT}; }
            QLabel#badge {
                background: ${ACCENT_SOFT_BG};
                color: ${ACCENT_TEXT};
                border-radius: 5px;
                padding: 2px 7px;
                font-size: 11px;
                font-weight: 600;
            }
            QLabel#warningHint {
                background: #3a1d1d;
                color: #ffb4a8;
                border-radius: 7px;
                padding: 8px 10px;
                font-size: 12px;
            }
            QLabel#progressHint { color: ${TEXT_MUTED}; background: transparent; }
            QPushButton#accentPush { background: ${ACCENT_BG}; color: ${WHITE}; border: 0; font-weight: 600; }
            QPushButton#accentPush:hover { background: ${ACCENT_HOVER_BG}; }
            QFrame#updateBanner { background: ${WARNING_BG}; border-bottom: 1px solid ${WARNING_BORDER}; }
            QFrame#updateBanner QLabel { color: ${WARNING_TEXT}; background: transparent; }
            QToolButton#chip { background: ${CHIP_BG}; color: ${TEXT_MUTED}; border: 0; border-radius: 9px; padding: 1px 9px; margin: 3px 2px; font-size: 11px; }
            QToolButton#chipWarning { background: #3a2e12; color: ${SELECTION_GOLD}; border: 0; border-radius: 9px; padding: 1px 9px; margin: 3px 2px; font-size: 11px; font-weight: 600; }
            QToolButton#chip:hover, QToolButton#chipWarning:hover { color: ${TEXT_BRIGHT}; }
            QWidget#segmented { background: ${INPUT_BG}; border: 1px solid ${BORDER_INPUT}; border-radius: 8px; }
            QPushButton#segment { background: transparent; border: 0; border-radius: 6px; padding: 4px 10px; color: ${TEXT_MUTED}; }
            QPushButton#segment:hover { color: ${TEXT_PRIMARY}; }
            QPushButton#segment:checked { background: ${ACCENT_SOFT_BG}; color: ${ACCENT_TEXT}; font-weight: 600; }
            QFrame#pickRow { background: ${CARD_BG}; border: 1px solid ${CARD_BORDER}; border-radius: 8px; }
            QFrame#pickRow:hover { border-color: ${BUTTON_HOVER_BORDER}; }
            QFrame#pickRow[checked="true"] { background: ${ACCENT_SOFT_BG}; border-color: ${ACCENT_BG}; }
            QFrame#pickRow QLabel#pickCell { background: transparent; color: ${TEXT_MUTED}; }
            QFrame#pickRow[checked="true"] QLabel#pickCell { color: ${TEXT_BRIGHT}; }
            QCheckBox#pickCheck::indicator { width: 18px; height: 18px; border-radius: 4px; border: 1px solid ${BORDER_INPUT}; background: ${PANEL_BG}; }
            QCheckBox#pickCheck::indicator:checked { background: ${ACCENT_BG}; border-color: ${ACCENT_BG}; }
            QPushButton#accentPush:disabled { background: ${BUTTON_HOVER_BG}; color: ${TEXT_MUTED}; }
            QPushButton#accentPush:checked { background: ${ACCENT_SOFT_BG}; color: ${ACCENT_TEXT}; border: 1px solid ${ACCENT_BG}; }
            QLabel#hintBox {
                background: ${ACCENT_SOFT_BG};
                color: ${ACCENT_TEXT};
                border-radius: 7px;
                padding: 8px 10px;
                font-size: 12px;
            }
            QLabel#stepBadge {
                background: ${ACCENT_SOFT_BG};
                color: ${ACCENT_TEXT};
                border-radius: 13px;
                font-weight: 700;
            }
            QLabel#versionChip {
                background: ${NOTE_NEW};
                color: ${CHROME_BG};
                border-radius: 5px;
                padding: 2px 8px;
                font-family: "${MONO_FONT}", Consolas, monospace;
                font-size: 12px;
                font-weight: 600;
            }
            QLabel#noteEntry { background: transparent; font-size: 13px; }
            QLabel#noteBox {
                background: ${CHROME_BG};
                color: ${TEXT_MUTED};
                border-radius: 8px;
                padding: 10px 12px;
                font-size: 12px;
            }
            QFrame#separatorLine { background: ${BORDER_PANEL}; border: 0; }
            QPushButton#ghostPush { background: transparent; border-color: transparent; color: ${TEXT_MUTED}; }
            QPushButton#ghostPush:hover { color: ${TEXT_BRIGHT}; }
            QLabel#chipWarning {
                background: #3a2e12;
                color: ${SELECTION_GOLD};
                border-radius: 9px;
                padding: 1px 9px;
                margin: 3px 2px;
                font-size: 11px;
                font-weight: 600;
            }
            QLabel#chip {
                background: ${CHIP_BG};
                color: ${TEXT_MUTED};
                border-radius: 9px;
                padding: 1px 9px;
                margin: 3px 2px;
                font-size: 11px;
            }
            QFrame#card {
                background: ${CARD_BG};
                border: 1px solid ${CARD_BORDER};
                border-radius: 10px;
            }
            QFrame#card QWidget { background: transparent; }
            QFrame#card QPushButton#accentPush { background: ${ACCENT_BG}; }
            QFrame#card QPushButton#accentPush:hover { background: ${ACCENT_HOVER_BG}; }
            QFrame#card QPushButton#accentPush:disabled { background: ${BUTTON_HOVER_BG}; }
            QFrame#floatingBar {
                background: ${CHIP_BG};
                border: 1px solid ${BORDER_INPUT};
                border-radius: 10px;
            }
            QFrame#floatingBar QToolButton#pill { border-radius: 7px; padding: 4px 9px; color: ${TEXT_PRIMARY}; }
            QFrame#floatingBar QToolButton#pill:checked { background: ${ACCENT_SOFT_BG}; color: ${ACCENT_TEXT}; }
            QFrame#floatingBar QToolButton#pillWarning {
                border-radius: 7px; padding: 4px 9px; background: #3a2e12; color: ${SELECTION_GOLD}; font-weight: 600;
            }
            QFrame#floatingBar QToolButton::menu-indicator { image: none; width: 0; }
            QToolButton#inspectorAction {
                background: ${BUTTON_HOVER_BG};
                border: 1px solid ${BORDER_INPUT};
                border-radius: 7px;
                padding: 6px 4px;
            }
            QToolButton#inspectorAction:focus { border-color: ${FOCUS_BLUE}; }
            QPushButton#githubButton {
                background: ${ACCENT_BG};
                color: ${WHITE};
                border: 0;
                border-radius: 7px;
                padding: 7px 12px;
            }
            QPushButton#githubButton:hover { background: ${ACCENT_HOVER_BG}; }
            QLineEdit, QSpinBox, QPlainTextEdit, QComboBox {
                background: ${INPUT_BG};
                color: ${TEXT_BRIGHT};
                border: 1px solid ${BORDER_INPUT};
                border-radius: 7px;
                padding: 6px 9px;
                selection-background-color: ${ACCENT_BG};
            }
            QSpinBox#monoSpin { font-family: "${MONO_FONT}", Consolas, monospace; }
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border-color: ${FOCUS_BLUE}; }
            QLineEdit:read-only { color: ${TEXT_READONLY}; background: transparent; border-color: transparent; padding-left: 0; }
            QComboBox QAbstractItemView { background: ${CHIP_BG}; border: 1px solid ${BORDER_INPUT}; selection-background-color: ${ACCENT_SOFT_BG}; }
            QTreeWidget {
                background: transparent;
                alternate-background-color: transparent;
                border: 0;
                outline: 0;
            }
            QTreeWidget::item { min-height: 26px; border-radius: 6px; padding-left: 4px; }
            QTreeWidget::item:selected { background: ${TREE_SELECTED_BG}; color: ${TEXT_BRIGHT}; }
            QTreeWidget::item:hover:!selected { background: ${TREE_HOVER_BG}; }
            QHeaderView::section {
                background: transparent;
                color: ${TEXT_HEADER};
                border: 0;
                border-bottom: 1px solid ${BORDER_PANEL};
                padding: 6px;
                font-size: 11px;
                font-weight: 600;
            }
            QTabWidget#sideTabs::pane { border: 0; background: ${PANEL_BG}; }
            QTabWidget#sideTabs QTabBar { background: ${PANEL_BG}; }
            QTabWidget#sideTabs QTabBar::tab {
                background: transparent;
                color: ${TEXT_SUBTITLE};
                padding: 10px 14px 8px;
                border: 0;
                border-bottom: 2px solid transparent;
                font-weight: 500;
            }
            QTabWidget#sideTabs QTabBar::tab:selected { color: ${TEXT_BRIGHT}; border-bottom-color: ${ACCENT_BG}; font-weight: 600; }
            QTabWidget#sideTabs QTabBar::tab:hover:!selected { color: ${TEXT_PRIMARY}; }
            QSplitter::handle { background: ${BORDER_PANEL}; }
            QSplitter::handle:horizontal { width: 1px; }
            QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; border: 0; }
            QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; border: 0; }
            QScrollBar::handle { background: ${SCROLLBAR_HANDLE}; border-radius: 3px; min-height: 28px; min-width: 28px; }
            QScrollBar::handle:hover { background: ${TEXT_DISABLED}; }
            QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page { width: 0; height: 0; background: transparent; }
            QAbstractScrollArea::corner { background: transparent; border: 0; }
            QStatusBar { border-top: 1px solid ${BORDER_CHROME}; font-size: 11px; }
            QStatusBar::item { border: 0; }
            QToolTip { background: ${TOOLTIP_BG}; color: ${TEXT_BRIGHT}; border: 1px solid ${BORDER_TOOLTIP}; padding: 4px 6px; }
            QDialog { background: ${PANEL_BG}; }
            QCheckBox { spacing: 8px; background: transparent; }
            QCheckBox::indicator {
                width: 15px; height: 15px;
                border: 1px solid ${SCROLLBAR_HANDLE};
                border-radius: 4px;
                background: ${INPUT_BG};
            }
            QCheckBox::indicator:hover { border-color: ${FOCUS_BLUE}; }
            QCheckBox::indicator:checked { background: ${ACCENT_BG}; border-color: ${ACCENT_BORDER}; }
            QDialog QLabel, QDialog QWidget#transparent { background: transparent; }
                """.replace("${UI_FONT}", UI_FONT).replace("${MONO_FONT}", MONO_FONT)
            )
        )

    def choose_document(self) -> None:
        if not self._confirm_discard_changes():
            return
        initial = DEFAULT_UI_DIRECTORY if DEFAULT_UI_DIRECTORY.exists() else Path.home()
        filename, _ = QFileDialog.getOpenFileName(
            self, self.tr("Abrir XML de interface"), str(initial), self.tr("XML (*.xml);;Todos os arquivos (*)")
        )
        if not filename:
            return
        path = Path(filename)
        if self.project is None or not self.project.contains(path):
            if self._offer_project_for(path):
                return
        self.open_document(path)

    def _offer_project_for(self, path: Path) -> bool:
        """Sugere criar um projeto ao abrir um XML solto. True se o projeto foi criado."""
        settings = QSettings("Local", "GF UI Editor")
        if settings.value("offer_project_on_open", "true") != "true":
            return False
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(self.tr("Criar um projeto?"))
        box.setText(self.tr("Editar {name} dentro de um projeto?").format(name=path.name))
        box.setInformativeText(
            self.tr(
                "Num projeto suas alterações ficam guardadas com histórico, e Enviar para o jogo copia "
                "tudo para a pasta certa. Arquivos soltos o jogo só vê se você copiá-los manualmente."
            )
        )
        create = box.addButton(self.tr("Criar projeto"), QMessageBox.ButtonRole.AcceptRole)
        box.addButton(self.tr("Só abrir"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(create)
        never = QCheckBox(self.tr("Não perguntar de novo"))
        box.setCheckBox(never)
        box.exec()
        if never.isChecked():
            settings.setValue("offer_project_on_open", "false")
        if box.clickedButton() is not create:
            return False
        return self.new_project(loose_dir=path.parent, focus=path)

    def set_navigation_style(self, style: str) -> None:
        self.view.navigation_style = style
        QSettings("Local", "GF UI Editor").setValue("navigation_style", style)

    def _confirm_utf8_conversion(self, path: Path) -> bool:
        answer = QMessageBox.question(
            self,
            self.tr("Arquivo salvo como UTF-8"),
            self.tr(
                "{name} foi salvo como UTF-8 (provavelmente por um editor de texto), mas o jogo lê os XML em Big5.\n\n"
                "Converter o arquivo para Big5? Uma cópia do original será guardada como backup."
            ).format(name=path.name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        return answer == QMessageBox.StandardButton.Yes

    def open_document(self, path: Path) -> None:
        try:
            document = UIDocument.load(path)
        except DocumentError as exc:
            if exc.code == "utf8" and self._confirm_utf8_conversion(path):
                in_project = self.project is not None and self.project.contains(path)
                try:
                    convert_utf8_file_to_big5(path, self.project.history_path_for(path) if in_project else None)
                    document = UIDocument.load(path)
                except DocumentError as retry_exc:
                    QMessageBox.critical(self, self.tr("Não foi possível abrir"), document_error_text(retry_exc))
                    return
            else:
                if exc.code != "utf8":
                    QMessageBox.critical(self, self.tr("Não foi possível abrir"), document_error_text(exc))
                return
        self.document = document
        if self.project is not None and self.project.contains(document.path):
            QSettings("Local", "GF UI Editor").setValue(
                f"last_file/{self.project.custom_name}",
                document.path.resolve().relative_to(self.project.ui_dir.resolve()).as_posix(),
            )
        self._texture_generation += 1
        ui_directory = document.path.parent.resolve()
        if self.texture_cache is None or self.texture_cache.ui_directory != ui_directory:
            self.texture_cache = TextureCache(ui_directory)
        else:
            self.texture_cache.missing.clear()
        self.undo_stack.clear()
        self.selected_index = None
        self.locked_indexes.clear()
        self.hidden_indexes.clear()
        self.isolated_index = None
        self._sync_isolation_warning()
        self.search_edit.clear()
        self.properties.set_element(None)
        self._rebuild_scene(load_textures=False)
        self._rebuild_tree()
        self.save_action.setEnabled(True)
        self.fit_action.setEnabled(True)
        self.reload_textures_action.setEnabled(True)
        self._watch_texture_files()
        self._update_element_actions()
        self._update_title()
        self._refresh_files()
        self.fit_scene()
        self._start_texture_loading()
        self._update_official_banner()
        self._check_xml_structure()

    def _check_xml_structure(self) -> None:
        """Texto solto entre as tags (sobra de edição manual) trava o jogo ou some com controles.

        Child_Cnt diferente sozinho não é avisado: vários XML originais do jogo
        têm a contagem errada e funcionam.
        """
        assert self.document is not None
        strays = self.document.stray_texts()
        if not strays:
            return
        line, text = strays[0]
        details = self.tr("Linha {line}: {text}").format(line=line, text=text[:60])
        if len(strays) > 1:
            details += "\n" + self.tr("(e mais {count} trecho(s) assim)").format(count=len(strays) - 1)
        answer = QMessageBox.warning(
            self,
            self.tr("Texto solto no XML"),
            self.tr(
                "Este arquivo tem texto solto entre as tags, sobra de edição manual:\n\n{details}\n\n"
                "O jogo pode travar ou mostrar \"Child control can not found\". Remover esse texto e "
                "acertar o Child_Cnt? A correção é gravada ao salvar."
            ).format(details=details),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.document.fix_structure()
            self._update_title()
            self.statusBar().showMessage(self.tr("O XML será corrigido ao salvar."), 6000)

    def _rebuild_scene(self, *, load_textures: bool = True) -> None:
        assert self.document is not None and self.texture_cache is not None
        self.view.set_interaction_priority(None)
        self.scene.clear()
        self.reference_layer_items = []  # a cena apagou os itens
        self.items.clear()
        for element in self.document.elements:
            pixmap = (
                self.texture_cache.pixmap_for(element)
                if load_textures or (element.texture_name and self.texture_cache.has_source(element.texture_name))
                else None
            )
            item = ElementItem(
                element, pixmap, self._canvas_selection_changed, self.elements_dragged
            )
            item.set_labels_visible(self.labels_action.isChecked())
            item.set_game_text(self._game_text_for(element))
            item.set_texture_visible(self.textures_action.isChecked())
            item.set_preview_mode(self.preview_action.isChecked())
            self.scene.addItem(item)
            self.items[element.index] = item
        self.game_screen_item = None
        self.game_drawn_item = None
        self.ghost_item = None  # a cena foi refeita
        self._refresh_game_screen()

    def _game_text_for(self, element) -> str:
        if self.text_mode == "off":
            return ""
        if self.text_mode == "game":
            # O jogo troca o WindowText pelo rótulo que o código escreve, quando há um.
            # O jogo só escreve o WindowText em controles de texto ou botões; painéis e a
            # raiz guardam ali só um nome interno ("PX1-1").
            takes_text = "TextNode" in element.child_tags or "ButtonNode" in element.child_tags
            fallback = element.window_text if takes_text else ""
            return self._game_labels().get(element.window_id, fallback)
        if element.window_text or self.text_mode == "xml":
            return element.window_text
        if "TextNode" not in element.child_tags and "ButtonNode" not in element.child_tags:
            return ""
        if not element.text_props or element.width < 4:
            return ""
        if self.text_mode == "short":
            return self.tr("Texto")
        return self.tr("Texto de exemplo bem comprido para testar o espaço")

    def _game_labels(self) -> dict[str, str]:
        if self.document is None:
            return {}
        key = (self.document.path.name.lower(), self._document_game_dir())
        if getattr(self, "_game_labels_key", None) != key:
            self._game_labels_key = key
            self._game_labels_cache = game_texts.labels_for(key[0], key[1])
        return self._game_labels_cache

    def set_text_mode(self, mode: str) -> None:
        self.text_mode = mode
        if self.document is None:
            return
        for element in self.document.elements:
            item = self.items.get(element.index)
            if item is not None:
                item.set_game_text(self._game_text_for(element))
        self._refresh_reference_layers()

    def _clear_reference_layers(self) -> None:
        for layer in self.reference_layer_items:
            if layer.scene() is self.scene:
                self.scene.removeItem(layer)
        self.reference_layer_items = []

    def _layer_document(self, path: Path) -> UIDocument | None:
        """Abre (e guarda) um XML de camada; relê só quando o arquivo muda."""
        try:
            modified = path.stat().st_mtime_ns
        except OSError:
            return None
        cached = self._layer_documents.get(path)
        if cached is not None and cached[0] == modified:
            return cached[1]
        try:
            document = UIDocument.load(path)
        except Exception:
            return None
        self._layer_documents[path] = (modified, document)
        return document

    def _refresh_reference_layers(self) -> None:
        """Desenha os XMLs marcados como camada onde o jogo os põe na tela."""
        self._clear_reference_layers()
        if (
            self.project is None or self.document is None or self.game_screen_item is None
            or self.game_resolution is None or self.texture_cache is None
        ):
            return
        current = self.document.path.name.lower()
        game_dir = self._document_game_dir()
        positions = (
            load_user_positions(game_dir / "User.ini")
            if game_dir is not None and self.saved_positions_action.isChecked() else {}
        )
        screen = self.game_screen_item.pos()
        for name in self.project.reference_layers:
            if name.lower() == current:
                continue
            document = self._layer_document(self.project.ui_dir / name)
            if document is None or not document.elements:
                continue
            root = document.elements[0]
            section = saved_section_for(name)
            screen_x, screen_y = root_screen_position(
                name, self.game_resolution, root.geometry, positions.get(section) if section else None,
                mode=self.project.root_modes.get(name, "auto"), game_dir=game_dir,
            )
            labels = game_texts.labels_for(name, game_dir) if self.text_mode == "game" else {}
            # Mesmo espaço do XML para todos os elementos: tela = raiz na tela + (elemento - raiz).
            origin = screen + QPointF(screen_x - root.x, screen_y - root.y)
            layer = ReferenceLayerItem(name, QRectF())
            layer.setPos(origin)
            for element in document.elements:
                if not element.visible:
                    continue
                takes_text = "TextNode" in element.child_tags or "ButtonNode" in element.child_tags
                text = labels.get(element.window_id, element.window_text if takes_text else "")
                layer.add_control(
                    QRectF(element.x, element.y, element.width, element.height),
                    self.texture_cache.pixmap_for(element),
                    text, element.text_props, "ButtonNode" in element.child_tags,
                )
            self.scene.addItem(layer)
            self.reference_layer_items.append(layer)

    def set_reference_layer(self, name: str, enabled: bool) -> None:
        if self.project is None:
            return
        layers = [layer for layer in self.project.reference_layers if layer.lower() != name.lower()]
        if enabled:
            layers.append(name)
        self.set_reference_layers(layers)

    def set_reference_layers(self, layers: list[str]) -> None:
        if self.project is None:
            return
        self.project.reference_layers = list(layers)
        self.project.save_manifest()
        self._refresh_reference_layers()
        # Depois do sinal da caixa: a lista é refeita para a camada subir para o topo.
        QTimer.singleShot(0, self._refresh_files_keeping_scroll)

    def _refresh_files_keeping_scroll(self) -> None:
        bar = self.files_tree.verticalScrollBar()
        position = bar.value()
        self._refresh_files()
        bar.setValue(position)

    def build_default_hud(self) -> None:
        """Liga como camadas as janelas que o jogo mostra sempre na tela."""
        if self.project is None:
            return
        available = {path.as_posix().lower(): path.as_posix() for path in self.project.files()}
        layers = list(self.project.reference_layers)
        for name in DEFAULT_HUD:
            match = available.get(name.lower())
            if match is not None and match.lower() not in (layer.lower() for layer in layers):
                layers.append(match)
        self.set_reference_layers(layers)
        if self.game_resolution is None:
            self.statusBar().showMessage(
                self.tr("As camadas aparecem no Preview do jogo: escolha uma resolução na barra do canvas."), 6000
            )

    def _refresh_game_screen(self) -> None:
        self._clear_reference_layers()
        if self.game_drawn_item is not None and self.game_drawn_item.scene() is self.scene:
            self.scene.removeItem(self.game_drawn_item)
        self.game_drawn_item = None
        self._sync_game_drawn_visibility()
        if self.game_screen_item is not None:
            self.scene.removeItem(self.game_screen_item)
            self.game_screen_item = None
        if self.game_resolution is not None:
            background = None
            if self.background_mode == "custom" and self.game_background_path is not None and self.game_background_path.is_file():
                background = QPixmap(str(self.game_background_path))
            elif self.background_mode == "builtin":
                builtin = backgrounds.pick(self.game_resolution)
                if builtin is not None:
                    background = QPixmap(str(builtin))
            width, height = self.game_resolution
            self.game_screen_item = GameScreenItem(width, height, background)
            self.scene.addItem(self.game_screen_item)
            self._place_game_screen()
        self._sync_window_frame()
        self._sync_manual_position_warning()
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-50, -50, 50, 50))

    def _place_game_screen(self) -> None:
        """Desloca a moldura para que a raiz caia onde o jogo a desenharia.

        Os elementos continuam nas coordenadas do XML; só a tela se move.
        """
        if self.game_screen_item is None or self.game_resolution is None:
            return
        before = self.game_screen_item.pos()
        before_in_view = self.view.mapFromScene(before)
        width, height = self.game_resolution
        caption = f"{width} × {height}"
        if self.document is not None and self.document.elements:
            root = self.document.elements[0]
            name = self.document.path.name
            section = saved_section_for(name)
            game_dir = self._document_game_dir()
            mode = self._root_mode()
            saved = self._saved_root_position()
            screen_x, screen_y = self._root_screen_for(root.geometry)
            self.game_screen_item.setPos(root.x - screen_x, root.y - screen_y)
            drawn = GAME_DRAWN_AREAS.get(name.lower())
            if drawn is not None:
                if self.game_drawn_item is None:
                    self.game_drawn_item = GameDrawnItem(
                        QRectF(0, 0, drawn[2], drawn[3]),
                        self.tr("Foto do personagem: o jogo desenha fixa aqui na tela"),
                    )
                    self.scene.addItem(self.game_drawn_item)
                self.game_drawn_item.setPos(self.game_screen_item.pos() + QPointF(drawn[0], drawn[1]))
            self._sync_game_drawn_visibility()
            self._refresh_reference_layers()
            caption += " · " + self.tr("janela no jogo em ({x}, {y})").format(x=screen_x, y=screen_y)
            if mode != "auto":
                caption += " · " + self.tr("posição escolhida por você")
            elif rule_for(name) is None and saved_position_applies(self.game_resolution, root.geometry, saved):
                caption += " · " + self.tr("posição salva no User.ini [{section}]").format(section=section)
            elif placement(name, game_dir) in ("anchor", "placed"):
                caption += " · " + self.tr("posição definida pelo cliente")
            elif is_centered(name, game_dir):
                caption += " · " + self.tr("centralizada pelo jogo")
            elif placement(name, game_dir) == "xml":
                caption += " · " + self.tr("o jogo usa o X/Y do XML")
            elif placement(name, game_dir) == "unused":
                caption += " · " + self.tr("arquivo não carregado pelo jogo")
            else:
                caption += " · " + self.tr("posição no jogo ainda não mapeada: usando o X/Y do XML")
            if game_dir is None:
                caption += " · " + self.tr("pasta do jogo não encontrada (escolha em Arquivo → Novo projeto)")
        else:
            self.game_screen_item.setPos(0, 0)
        self.game_screen_item.set_caption(caption)
        self._keep_screen_in_place(before, before_in_view)
        self._sync_window_frame()
        self._sync_manual_position_warning()
        self._refresh_screen_position()

    def _sync_game_drawn_visibility(self, _checked: bool = False) -> None:
        if self.game_drawn_item is not None:
            self.game_drawn_item.setVisible(self.game_drawn_action.isChecked())
        if hasattr(self, "game_drawn_button"):
            self.game_drawn_button.setVisible(self.game_drawn_item is not None)

    def _sync_manual_position_warning(self) -> None:
        if not hasattr(self, "manual_position_button"):
            return
        manual = self.document is not None and self.game_screen_item is not None and self._root_mode() != "auto"
        if manual != (not self.manual_position_button.isHidden()):
            self.manual_position_button.setVisible(manual)
            self.view._place_overlays()

    def _saved_root_position(self):
        assert self.document is not None
        section = saved_section_for(self.document.path.name)
        game_dir = self._document_game_dir()
        if section and game_dir is not None and self.saved_positions_action.isChecked():
            return load_user_positions(game_dir / "User.ini").get(section)
        return None

    def _root_screen_for(self, geometry: tuple[int, int, int, int]) -> tuple[int, int]:
        """Onde o jogo poria a janela principal se ela tivesse esta geometria."""
        assert self.document is not None and self.game_resolution is not None
        return root_screen_position(
            self.document.path.name, self.game_resolution, geometry, self._saved_root_position(),
            mode=self._root_mode(), game_dir=self._document_game_dir(),
        )

    def _keep_screen_in_place(self, before, before_in_view) -> None:
        """A tela não sai do lugar na vista quando a raiz muda: é o conteúdo que anda."""
        assert self.game_screen_item is not None
        shift = self.game_screen_item.pos() - before
        if shift.isNull():
            return
        self.scene.setSceneRect(self.scene.sceneRect().translated(shift))
        drift = self.view.mapFromScene(self.game_screen_item.pos()) - before_in_view
        for bar, amount in (
            (self.view.horizontalScrollBar(), drift.x()),
            (self.view.verticalScrollBar(), drift.y()),
        ):
            bar.setValue(bar.value() + amount)

    def _sync_window_frame(self) -> None:
        """Numa janela que o jogo posiciona, mostra a raiz como moldura do conteúdo.

        O retângulo real da raiz fica preso ao centro ou a um canto; arrastar a
        moldura leva o conteúdo junto e o X/Y da raiz é acertado por baixo.
        """
        if self.document is None or 0 not in self.items or not self.document.elements:
            return
        root = self.document.elements[0]
        self._sync_menu_shortcut_preview()
        item = self.items[0]
        item.apply_element(root)
        item.carries_content = len(self.document.elements) > 1
        offset = self._screen_offset()
        bounds = self._content_bounds()
        if offset is not None and bounds is not None and self._root_position_is_set_by_game():
            geometry = root.geometry
            def frame_geometry(width: int, height: int) -> QRectF:
                return QRectF(*self._resized_root(geometry, width, height))
            item.set_content_frame(bounds, offset, frame_geometry)
        self._sync_ghost_area()

    def _sync_menu_shortcut_preview(self) -> None:
        if self.document.path.name.lower() != "menu.xml":
            return
        root_y = self.document.elements[0].y
        enabled = self.game_screen_item is not None and self._root_mode() == "auto"
        for element in self.document.elements:
            y = menu_shortcut_preview_y(self.document.path.name, element.window_id, root_y)
            if y is None or element.kind != "slot":
                continue
            self.items[element.index].set_preview_offset(QPointF(0, y - element.y if enabled else 0))

    def _content_bounds(self) -> QRectF | None:
        """Retângulo que envolve tudo menos a janela principal, em coordenadas do XML."""
        if self.document is None or len(self.document.elements) < 2:
            return None
        bounds = QRectF()
        for element in self.document.elements[1:]:
            area = QRectF(element.x, element.y, max(1, element.width), max(1, element.height))
            bounds = bounds.united(area.translated(self.items[element.index].preview_offset))
        return bounds

    GHOST_TOLERANCE = 8

    def _ghost_area(self, geometry: tuple[int, int, int, int] | None = None) -> QRectF | None:
        """Parte da tela que o jogo ainda trata como janela, longe do conteúdo.

        O jogo prende a janela principal ao centro (ou a um canto) e desenha o
        conteúdo deslocado dela. Se o conteúdo foi levado para outro lugar, o
        retângulo da janela continua lá, invisível, recebendo cliques e arraste.
        """
        bounds = self._content_bounds()
        if bounds is None or self._screen_offset() is None or not self._root_position_is_set_by_game():
            return None
        x, y, width, height = geometry or self.document.elements[0].geometry
        if width <= 1 and height <= 1:
            return None
        area = QRectF(x, y, max(1, width), max(1, height))
        margin = self.GHOST_TOLERANCE
        # Uma dentro da outra é uma janela comum (com folga ou com conteúdo maior); só
        # há área sobrando quando o conteúdo saiu de cima da janela principal.
        if bounds.adjusted(-margin, -margin, margin, margin).contains(area):
            return None
        if area.adjusted(-margin, -margin, margin, margin).contains(bounds):
            return None
        # Com fundo próprio visível a área não é invisível, e encolher apagaria o fundo.
        return None if self._root_draws_background() else area

    def _sync_ghost_area(self) -> None:
        area = self._ghost_area()
        if area is None:
            if self.ghost_item is not None:
                self.scene.removeItem(self.ghost_item)
                self.ghost_item = None
        else:
            if self.ghost_item is None:
                self.ghost_item = GhostAreaItem(self.tr("Área invisível da janela"))
                self.scene.addItem(self.ghost_item)
            self.ghost_item.set_area(area)
        self.properties.set_ghost_warning(area is not None and self.selected_index == 0)

    def _root_draws_background(self) -> bool:
        """A janela principal tem textura visível? Encolhê-la apagaria esse fundo."""
        item = self.items.get(0)
        texture = item.texture_item if item is not None else None
        if texture is None or texture.pixmap().isNull():
            return False
        image = texture.pixmap().toImage().scaled(16, 16)
        return any(image.pixelColor(x, y).alpha() > 8 for x in range(16) for y in range(16))

    def _collapsed_root(self, geometry: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
        """A mesma janela com 1 × 1, com o X/Y compensado para o conteúdo não sair do lugar."""
        return self._resized_root(geometry, 1, 1)

    def _resized_root(
        self, geometry: tuple[int, int, int, int], width: int, height: int
    ) -> tuple[int, int, int, int]:
        # O ponto onde o jogo põe a janela depende do tamanho dela (centro, canto direito...).
        x, y = geometry[:2]
        before = self._root_screen_for(geometry)
        after = self._root_screen_for((x, y, width, height))
        return x + after[0] - before[0], y + after[1] - before[1], width, height

    def _without_ghost_area(self, geometry: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
        """Depois de mover a janela: encolhe a principal se ela fosse sobrar longe do conteúdo."""
        if self._ghost_area(geometry) is None:
            return geometry
        self.statusBar().showMessage(
            self.tr("A janela principal foi reduzida a 1 × 1 para não deixar uma área invisível no lugar antigo."),
            10000,
        )
        return self._collapsed_root(geometry)

    def remove_ghost_area(self) -> None:
        if self.document is None or self._ghost_area() is None:
            return
        root = self.document.elements[0].geometry
        self.undo_stack.push(GeometryCommand(self, 0, root, self._collapsed_root(root)))

    def _screen_offset(self) -> tuple[int, int] | None:
        """Quanto somar a uma coordenada do XML para obter a da tela do jogo."""
        if self.game_screen_item is None or self.document is None:
            return None
        position = self.game_screen_item.pos()
        return -round(position.x()), -round(position.y())

    def _show_cursor_position(self, x: int, y: int) -> None:
        offset = self._screen_offset()
        if offset is None:
            text = self.tr("Mouse: X {x} · Y {y}").format(x=x, y=y)
        else:
            # O XML guarda posições relativas à janela; a tela é onde o jogo desenha.
            text = self.tr("XML: X {x} · Y {y}    Tela: X {sx} · Y {sy}").format(
                x=x, y=y, sx=x + offset[0], sy=y + offset[1]
            )
        self.cursor_position_label.setText(text)

    def _refresh_screen_position(self) -> None:
        offset = self._screen_offset()
        if offset is None or self.selected_index is None or self.document is None:
            self.properties.set_screen_position(None)
            return
        element = self.document.elements[self.selected_index]
        frame = self._window_frame_on_screen() if self.selected_index == 0 else None
        if frame is not None:
            self.properties.show_window_position(frame, (element.x, element.y))
            return
        position = self.items[element.index].scenePos()
        self.properties.set_screen_position((round(position.x()) + offset[0], round(position.y()) + offset[1]))

    def _window_frame_on_screen(self) -> tuple[int, int] | None:
        """Onde a moldura da janela aparece na tela, quando o jogo é quem a posiciona."""
        offset = self._screen_offset()
        item = self.items.get(0)
        if offset is None or item is None or not item.frame_mode:
            return None
        return round(item.pos().x()) + offset[0], round(item.pos().y()) + offset[1]

    def _document_game_dir(self) -> Path | None:
        """Pasta do jogo do arquivo aberto: a do projeto, ou a pasta acima de UI."""
        if self.document is None:
            return None
        if self.project is not None and self.project.contains(self.document.path):
            return self.project.game_dir
        beside = self.document.path.parent.parent
        if looks_like_game_dir(beside):
            return beside
        # XML avulso (ex.: Downloads): usa a pasta do jogo configurada para ter as regras.
        return self._game_dir()

    def _root_mode_key(self) -> str:
        assert self.document is not None
        if self.project is not None and self.project.contains(self.document.path):
            return self.document.path.resolve().relative_to(self.project.ui_dir.resolve()).as_posix()
        return self.document.path.name.lower()

    def _root_mode(self) -> str:
        if self.document is None:
            return "auto"
        if self.project is not None and self.project.contains(self.document.path):
            return self.project.root_modes.get(self._root_mode_key(), "auto")
        return str(QSettings("Local", "GF UI Editor").value(f"root_mode/{self._root_mode_key()}", "auto"))

    def _sync_root_mode_actions(self) -> None:
        mode = self._root_mode()
        for action in self.root_mode_actions.actions():
            action.setEnabled(self.document is not None)
            action.setChecked(action.data() == mode)

    def set_root_mode(self, mode: str) -> None:
        if self.document is None:
            return
        key = self._root_mode_key()
        if self.project is not None and self.project.contains(self.document.path):
            if mode == "auto":
                self.project.root_modes.pop(key, None)
            else:
                self.project.root_modes[key] = mode
            self.project.save_manifest()
        else:
            QSettings("Local", "GF UI Editor").setValue(f"root_mode/{key}", mode)
        self._place_game_screen()
        if self.selected_index == 0:
            self.properties.set_anchor_hint(self._anchor_hint_for(0))

    def _client_resolution(self) -> tuple[int, int]:
        game_dir = self._game_dir()
        return (client_resolution(game_dir) if game_dir is not None else None) or (1024, 768)

    def follow_client_resolution(self) -> None:
        QSettings("Local", "GF UI Editor").setValue("game_resolution", "game")
        self.follow_game_resolution = True
        self.game_resolution = self._client_resolution()
        self._sync_resolution_actions()
        self._refresh_game_screen()

    def _sync_resolution_actions(self) -> None:
        if hasattr(self, "resolution_button"):
            if self.game_resolution is None:
                text = self.tr("Sem moldura")
            else:
                text = f"{self.game_resolution[0]} × {self.game_resolution[1]}"
                if self.follow_game_resolution:
                    text += " · " + self.tr("jogo")
            self.resolution_button.setText(text)
        if self.follow_game_resolution and self.game_resolution is not None:
            self.resolution_game_action.setChecked(True)
            self.resolution_game_action.setText(
                self.tr("Igual ao jogo ({width} × {height})").format(width=self.game_resolution[0], height=self.game_resolution[1])
            )
        elif self.game_resolution is None:
            self.resolution_off_action.setChecked(True)
        elif self.game_resolution in self.resolution_preset_actions:
            self.resolution_preset_actions[self.game_resolution].setChecked(True)
        else:
            self.resolution_custom_action.setChecked(True)
        if self.resolution_custom_action.isChecked() and self.game_resolution is not None:
            width, height = self.game_resolution
            self.resolution_custom_action.setText(
                self.tr("Personalizada ({width} × {height})…").format(width=width, height=height)
            )
        else:
            self.resolution_custom_action.setText(self.tr("Personalizada…"))

    def set_game_resolution(self, resolution: tuple[int, int] | None) -> None:
        self.game_resolution = resolution
        self.follow_game_resolution = False
        QSettings("Local", "GF UI Editor").setValue(
            "game_resolution", f"{resolution[0]}x{resolution[1]}" if resolution else "off"
        )
        self._sync_resolution_actions()
        self._refresh_game_screen()

    def choose_custom_resolution(self) -> None:
        width, height = self.game_resolution or (1024, 768)
        text, accepted = QInputDialog.getText(
            self,
            self.tr("Resolução do jogo"),
            self.tr("Largura × altura (ex.: 1366x768):"),
            text=f"{width}x{height}",
        )
        resolution = parse_resolution(text) if accepted else None
        if accepted and resolution is None:
            QMessageBox.warning(
                self,
                self.tr("Resolução inválida"),
                self.tr("Use o formato largura x altura, por exemplo 1366x768."),
            )
        if resolution is None:
            self._sync_resolution_actions()
            return
        self.set_game_resolution(resolution)

    def choose_game_background(self) -> None:
        game_dir = self._game_dir()
        captures = game_dir / "ScreenCapture" if game_dir is not None else None
        if self.game_background_path:
            start = str(self.game_background_path.parent)
        else:
            start = str(captures) if captures is not None and captures.is_dir() else ""
        filename, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Escolher captura de tela do jogo"),
            start,
            self.tr("Imagens (*.png *.jpg *.jpeg *.bmp)"),
        )
        if filename:
            self.set_game_background(Path(filename))
        else:
            self._sync_background_actions()

    def _sync_background_actions(self) -> None:
        {
            "builtin": self.builtin_background_action,
            "custom": self.background_action,
            "none": self.no_background_action,
        }.get(self.background_mode, self.builtin_background_action).setChecked(True)

    def set_background_mode(self, mode: str) -> None:
        self.background_mode = mode
        QSettings("Local", "GF UI Editor").setValue("background_mode", mode)
        self._sync_background_actions()
        self._refresh_game_screen()

    def set_game_background(self, path: Path | None) -> None:
        self.game_background_path = path
        QSettings("Local", "GF UI Editor").setValue("game_background", str(path) if path else "")
        self.background_mode = "custom" if path is not None else "builtin"
        QSettings("Local", "GF UI Editor").setValue("background_mode", self.background_mode)
        self._sync_background_actions()
        if path is not None:
            # A captura define a resolução: o jogo desenha a UI em pixels de
            # tela, então a moldura passa a ter exatamente o tamanho da imagem.
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                size = (pixmap.width(), pixmap.height())
                game_size = self._client_resolution()
                self.set_game_resolution(size)
                if size != game_size:
                    self.statusBar().showMessage(
                        self.tr(
                            "A captura tem {w}×{h}, mas o jogo está configurado para {gw}×{gh}. "
                            "Para o preview bater, capture só a área do jogo na resolução em que você joga."
                        ).format(w=size[0], h=size[1], gw=game_size[0], gh=game_size[1]),
                        15000,
                    )
                return
        self._refresh_game_screen()

    def set_preview_mode(self, enabled: bool) -> None:
        for item in self.items.values():
            item.set_preview_mode(enabled)
        if enabled:
            self.labels_action.setChecked(False)

    def _start_texture_loading(self) -> None:
        assert self.document is not None and self.texture_cache is not None
        names = sorted({
            element.texture_name for element in self.document.elements
            if element.texture_name and element.uv
            and not self.texture_cache.has_source(element.texture_name)
        })
        self._textures_pending = set(names)
        self._texture_total = len(names)
        # Texturas já no cache (lidas pelas camadas de referência, por exemplo) não entram
        # na fila: aplica agora, senão os elementos ficariam sem imagem.
        for element in self.document.elements:
            if element.texture_name and element.uv and self.texture_cache.has_source(element.texture_name):
                self._refresh_element_texture(element.index)
        if not names:
            self.statusBar().showMessage(self.tr("{count} elementos carregados").format(count=len(self.document.elements)))
            return
        generation = self._texture_generation
        directory = self.texture_cache.ui_directory
        self.statusBar().showMessage(self.tr("Elementos prontos · carregando texturas ({done}/{total})…").format(done=0, total=len(names)))
        self._texture_timer.start()

        def load() -> None:
            cache = TextureCache(directory)
            for name in names:
                try:
                    source = cache.prepare_source(name)
                except Exception:
                    source = None
                self._texture_results.put((generation, name, source))

        Thread(target=load, name="gf-ui-textures", daemon=True).start()

    def _apply_loaded_textures(self) -> None:
        while True:
            try:
                generation, name, source = self._texture_results.get_nowait()
            except Empty:
                break
            if generation != self._texture_generation or name not in self._textures_pending:
                continue
            assert self.document is not None and self.texture_cache is not None
            self._textures_pending.remove(name)
            if source is None:
                self.texture_cache.missing.add(name)
            else:
                self.texture_cache.install_source(source)
                for element in self.document.elements:
                    if element.texture_name == name:
                        self._refresh_element_texture(element.index)
                        if element.index == 0:
                            self._sync_ghost_area()  # o fundo da janela principal muda a resposta
            done = self._texture_total - len(self._textures_pending)
            if self._textures_pending:
                self.statusBar().showMessage(self.tr("Elementos prontos · carregando texturas ({done}/{total})…").format(done=done, total=self._texture_total))
            else:
                missing = len(self.texture_cache.missing)
                suffix = self.tr(" · texturas ausentes: {count}").format(count=missing) if missing else ""
                self.statusBar().showMessage(self.tr("{count} elementos carregados").format(count=len(self.document.elements)) + suffix)
                self._texture_timer.stop()

    def _rebuild_tree(self) -> None:
        assert self.document is not None
        self.tree.clear()
        self.tree_items.clear()
        id_map: dict[str, QTreeWidgetItem] = {}
        pending: list[tuple[UIElement, QTreeWidgetItem]] = []
        for element in self.document.elements:
            item = QTreeWidgetItem(
                [element.window_id, kind_label(element.kind, element.ctrl_type), element.parent_id or "", ""]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, element.index)
            self.tree_items[element.index] = item
            item.setData(3, STATE_ROLE, ())
            item.setToolTip(3, self.tr("Ocultar · Bloquear · Isolar"))
            id_map.setdefault(element.window_id, item)
            pending.append((element, item))
        for element, item in pending:
            parent_item = id_map.get(element.parent_id or "")
            if parent_item is not None and parent_item is not item:
                parent_item.addChild(item)
            else:
                self.tree.addTopLevelItem(item)
        self.tree.resizeColumnToContents(0)
        self.tree.resizeColumnToContents(3)

    def select_element(self, index: int) -> None:
        if self.document is None or self._syncing_selection:
            return
        self._syncing_selection = True
        try:
            self.selected_index = index
            for item_index, item in self.items.items():
                item.setSelected(item_index == index)
            tree_item = self.tree_items.get(index)
            if tree_item is not None:
                parent = tree_item.parent()
                while parent is not None:
                    parent.setExpanded(True)
                    parent = parent.parent()
                self.tree.clearSelection()
                tree_item.setSelected(True)
                self.tree.setCurrentItem(tree_item)
                self.tree.scrollToItem(tree_item)
            self._set_primary_selection(index, 1)
            item_bounds = self.items[index].mapRectToScene(self.items[index].rect())
            viewport_bounds = self.view.mapToScene(self.view.viewport().rect()).boundingRect()
            if not viewport_bounds.intersects(item_bounds):
                self.view.centerOn(item_bounds.center())
        finally:
            self._syncing_selection = False

    def _anchor_hint_for(self, index: int) -> str | None:
        if self.document is None:
            return None
        if self._root_mode() != "auto":
            return None
        if index != 0:
            element = self.document.elements[index]
            if element.kind == "slot" and menu_shortcut_preview_y(
                self.document.path.name, element.window_id, self.document.elements[0].y
            ) is not None:
                return self.tr(
                    "O jogo define a posição vertical destes atalhos do Menu. "
                    "Com o preview ativo, o Y exibido segue essa regra; o campo Y mantém o valor do XML."
                )
            return None
        if placement(self.document.path.name) in ("anchor", "placed"):
            return self.tr(
                "O jogo prende esta janela a um ponto da tela. "
                "Com o Preview do jogo ligado, arraste a janela ou edite X/Y para colocá-la onde deve aparecer na tela; "
                "o editor grava no XML o valor que o jogo espera."
            )
        if is_centered(self.document.path.name, self._document_game_dir()):
            return self.tr(
                "O jogo centraliza esta janela na tela. "
                "Com o Preview do jogo ligado, arraste a janela ou edite X/Y para colocá-la onde deve aparecer na tela; "
                "o editor grava no XML o valor que o jogo espera."
            )
        return None

    def _set_primary_selection(self, index: int, selection_count: int) -> None:
        assert self.document is not None
        self.selected_index = index
        self.view.set_interaction_priority(self.items[index])
        self.properties.set_element(self.document.elements[index])
        self._refresh_screen_position()
        self.properties.set_anchor_hint(self._anchor_hint_for(index))
        self.properties.set_ghost_warning(index == 0 and self._ghost_area() is not None)
        self.properties.set_enabled(index not in self.locked_indexes)
        if self.isolated_index is not None and self.isolated_index != index:
            previous_isolated_index = self.isolated_index
            self.isolated_index = index
            self._apply_visibility_state()
            self._refresh_tree_state(previous_isolated_index)
            self._refresh_tree_state(index)
            self._sync_isolation_warning()
        self._update_element_actions()
        suffix = self.tr(" · {count} selecionados").format(count=selection_count) if selection_count > 1 else ""
        self.statusBar().showMessage(
            self.tr("WindowID {id} · índice {index}").format(
                id=self.document.elements[index].window_id, index=index
            ) + suffix
        )

    def clear_selection(self) -> None:
        if self.document is None:
            return
        self.scene.clearSelection()
        self._canvas_selection_changed(-1)

    def _canvas_selection_changed(self, changed_index: int) -> None:
        if self.document is None or self._syncing_selection:
            return
        selected_indexes = [
            index for index, item in self.items.items() if item.isSelected()
        ]
        self._syncing_selection = True
        try:
            self.tree.clearSelection()
            if selected_indexes:
                primary = (
                    changed_index if changed_index in selected_indexes else selected_indexes[-1]
                )
                tree_item = self.tree_items.get(primary)
                if tree_item is not None:
                    self.tree.setCurrentItem(tree_item)
                for index in selected_indexes:
                    selected_tree_item = self.tree_items.get(index)
                    if selected_tree_item is not None:
                        selected_tree_item.setSelected(True)
                self._set_primary_selection(primary, len(selected_indexes))
            else:
                self.selected_index = None
                self.view.set_interaction_priority(None)
                self.properties.set_element(None)
                self._update_element_actions()
        finally:
            self._syncing_selection = False

    def _tree_selection_changed(self) -> None:
        if self._syncing_selection:
            return
        selected = self.tree.selectedItems()
        if selected:
            indexes = [
                item.data(0, Qt.ItemDataRole.UserRole)
                for item in selected
                if isinstance(item.data(0, Qt.ItemDataRole.UserRole), int)
            ]
            current = self.tree.currentItem()
            current_index = (
                current.data(0, Qt.ItemDataRole.UserRole) if current is not None else None
            )
            primary = current_index if current_index in indexes else indexes[0]
            self._syncing_selection = True
            try:
                for index, item in self.items.items():
                    item.setSelected(index in indexes)
                self._set_primary_selection(primary, len(indexes))
            finally:
                self._syncing_selection = False
        else:
            self._syncing_selection = True
            try:
                for item in self.items.values():
                    item.setSelected(False)
                self.selected_index = None
                self.view.set_interaction_priority(None)
                self.properties.set_element(None)
                self._update_element_actions()
            finally:
                self._syncing_selection = False

    def elements_dragged(
        self,
        changes: dict[
            int, tuple[tuple[int, int, int, int], tuple[int, int, int, int]]
        ],
    ) -> None:
        changes = {
            index: geometries
            for index, geometries in changes.items()
            if index not in self.locked_indexes and geometries[0] != geometries[1]
        }
        changes = self._root_move_as_screen_move(changes)
        if changes:
            self.undo_stack.push(GeometryBatchCommand(self, changes))
            if 0 in changes and self._window_frame_on_screen() is None:
                self._warn_root_position_ignored()

    def edit_selected_geometry(self, geometry: tuple[int, int, int, int]) -> None:
        if self.document is None or self.selected_index is None:
            return
        if self.selected_index in self.locked_indexes:
            self.statusBar().showMessage(self.tr("O elemento selecionado está bloqueado."), 3000)
            self.properties.set_element(self.document.elements[self.selected_index])
            self.properties.set_enabled(False)
            return
        element = self.document.elements[self.selected_index]
        frame = self._window_frame_on_screen() if self.selected_index == 0 else None
        if frame is not None:
            # O painel mostra a posição na tela; a raiz anda ao contrário (ver _root_move_as_screen_move).
            moved_root = (
                element.x - (geometry[0] - frame[0]), element.y - (geometry[1] - frame[1]),
                element.width, element.height,
            )
            if geometry[2:] != element.geometry[2:]:
                # Mudar o tamanho desloca o ponto onde o jogo põe a janela: o conteúdo não deve pular.
                geometry = self._resized_root(moved_root, geometry[2], geometry[3])
            elif moved_root != element.geometry:
                geometry = self._without_ghost_area(moved_root)
            else:
                geometry = moved_root
        if element.geometry != geometry:
            moved = frame is None and element.geometry[:2] != geometry[:2]
            self.undo_stack.push(
                GeometryCommand(self, self.selected_index, element.geometry, geometry)
            )
            if self.selected_index == 0 and moved:
                self._warn_root_position_ignored()

    def _root_move_as_screen_move(self, changes: dict) -> dict:
        """Mover só a raiz de uma janela que o jogo fixa = mover o conteúdo na tela.

        O jogo põe a raiz no centro (ou num canto) e desenha cada elemento
        deslocado dela por (elemento - raiz). Para o conteúdo ir aonde o usuário
        levou a janela, o X/Y da raiz anda no sentido contrário. Movendo a raiz
        junto com os elementos, a diferença não muda e nada é invertido.
        """
        if 0 not in changes or self.document is None:
            return changes
        # A moldura da raiz pode estar desenhada fora do X/Y do XML: vale o deslocamento.
        old, new = changes[0]
        dx, dy = new[0] - old[0], new[1] - old[1]
        x, y = self.document.elements[0].geometry[:2]
        root = self.document.elements[0].geometry
        if set(changes) == {0} and self._root_position_is_set_by_game():
            if new[2:] != old[2:]:
                moved = (x - dx, y - dy, root[2], root[3])
                return {0: (root, self._resized_root(moved, new[2], new[3]))}
            moved = (x - dx, y - dy, new[2], new[3])
            if self._window_frame_on_screen() is not None and (dx or dy):
                moved = self._without_ghost_area(moved)
            return {0: (root, moved)}
        if set(changes) == {0} and new[2:] == old[2:] and (dx or dy):
            # Janela comum: arrastar a principal é mover a janela inteira. Movendo tudo junto,
            # muda a posição padrão dela sem mexer na relação entre os elementos.
            shown_at = self._preview_default_position()
            if shown_at is not None:
                # A janela estava desenhada na posição salva: o padrão do XML passa a ser
                # o ponto da tela onde ela foi solta, não o X/Y antigo mais o arraste.
                dx, dy = shown_at[0] + dx - x, shown_at[1] + dy - y
            return {
                element.index: (
                    element.geometry, (element.x + dx, element.y + dy, element.width, element.height)
                )
                for element in self.document.elements
                if element.index == 0 or element.index not in self.locked_indexes
            }
        return {**changes, 0: (root, (x + dx, y + dy, new[2], new[3]))}

    def _preview_default_position(self) -> tuple[int, int] | None:
        """Ao mover uma janela com posição salva no User.ini, o preview passa a mostrar a do XML.

        O jogo reabre essas janelas onde o jogador as deixou; o XML só define a
        posição padrão, que é o que se está editando. Devolve onde a janela
        estava desenhada, se era na posição salva.
        """
        if self.document is None or self.game_resolution is None or not self.saved_positions_action.isChecked():
            return None
        if rule_for(self.document.path.name) is not None:
            return None
        root = self.document.elements[0].geometry
        if not saved_position_applies(self.game_resolution, root, self._saved_root_position()):
            return None
        shown_at = self._root_screen_for(root)
        self.saved_positions_action.setChecked(False)
        self.statusBar().showMessage(
            self.tr(
                "O jogo lembra onde você deixou esta janela (User.ini). O preview agora mostra a posição "
                "padrão do XML, que vale para quem ainda não a moveu no jogo."
            ),
            15000,
        )
        return shown_at

    def _root_position_is_set_by_game(self) -> bool:
        return self.document is not None and self._anchor_hint_for(0) is not None

    def _warn_root_position_ignored(self) -> None:
        """Explica o efeito do X/Y da raiz numa janela que o jogo posiciona sozinho."""
        if not self._root_position_is_set_by_game():
            return
        self.statusBar().showMessage(
            self.tr("O jogo fixa esta janela; o X/Y dela desloca o conteúdo no sentido contrário. Confira o resultado no preview."),
            12000,
        )

    def move_selected(self, dx: int, dy: int) -> None:
        if self.document is None or self.selected_index is None:
            return
        selected_indexes = [
            index
            for index, item in self.items.items()
            if item.isSelected() and index not in self.locked_indexes
        ]
        changes = {}
        for index in selected_indexes:
            element = self.document.elements[index]
            x, y, width, height = element.geometry
            changes[index] = (element.geometry, (x + dx, y + dy, width, height))
        changes = self._root_move_as_screen_move(changes)
        if changes:
            self.undo_stack.push(GeometryBatchCommand(self, changes))
            if 0 in changes and self._window_frame_on_screen() is None:
                self._warn_root_position_ignored()
        else:
            self.statusBar().showMessage(self.tr("Os elementos selecionados estão bloqueados."), 3000)

    def apply_geometry(self, index: int, geometry: tuple[int, int, int, int]) -> None:
        assert self.document is not None
        self.document.set_geometry(index, geometry)
        self.items[index].apply_element(self.document.elements[index])
        if index == 0:
            self._place_game_screen()
        else:
            self._sync_window_frame()
        if self.selected_index == index:
            self.properties.set_element(self.document.elements[index])
            self._refresh_screen_position()
        elif self.selected_index == 0:
            self._refresh_screen_position()  # a moldura acompanha o conteúdo
        self._update_title()

    def edit_uv(
        self, index: int, uv: UVRect, resize_element: bool, offset: tuple[int, int] | None = None
    ) -> None:
        if self.document is None:
            return
        if index in self.locked_indexes:
            self.statusBar().showMessage(self.tr("O elemento selecionado está bloqueado."), 3000)
            return
        element = self.document.elements[index]
        if element.uv is None:
            return
        geometry = (element.x, element.y, uv.width, uv.height)
        uv_changed = element.uv != uv
        geometry_changed = resize_element and element.geometry != geometry
        offset_changed = offset is not None and element.progress_offset is not None and offset != element.progress_offset
        if not uv_changed and not geometry_changed and not offset_changed:
            return
        self.undo_stack.beginMacro(self.tr("Alterar atlas do WindowID {id}").format(id=element.window_id))
        if uv_changed:
            self.undo_stack.push(UVCommand(self, index, element.uv, uv))
        if geometry_changed:
            self.undo_stack.push(
                GeometryCommand(self, index, element.geometry, geometry)
            )
        if offset_changed:
            self.undo_stack.push(OffsetCommand(self, index, element.progress_offset, offset))
        self.undo_stack.endMacro()

    def apply_offset(self, index: int, offset: tuple[int, int]) -> None:
        assert self.document is not None
        self.document.set_progress_offset(index, offset)
        self._refresh_element_texture(index)
        self._update_title()

    def apply_uv(self, index: int, uv: UVRect) -> None:
        assert self.document is not None
        self.document.set_uv(index, uv)
        self._refresh_element_texture(index)
        if self.selected_index == index:
            self.properties.set_element(self.document.elements[index])
        self._update_title()

    def edit_button_uvs(self, index: int, states: dict[str, UVRect], resize_element: bool) -> None:
        if self.document is None or index in self.locked_indexes:
            return
        element = self.document.elements[index]
        if "ButtonNode" not in element.child_tags or element.uv is None or not self.document.button_states_editable:
            return
        allowed = {"NorUV": element.uv, **element.button_uvs}
        changes = {state: uv for state, uv in states.items()
                   if state in allowed and allowed[state] is not None and allowed[state] != uv}
        normal = states.get("NorUV", element.uv)
        geometry = (element.x, element.y, normal.width, normal.height)
        resize = resize_element and element.geometry != geometry
        if not changes and not resize:
            return
        self.undo_stack.beginMacro(self.tr("Alterar atlas do WindowID {id}").format(id=element.window_id))
        for state, uv in changes.items():
            command = (UVCommand(self, index, element.uv, uv) if state == "NorUV" else
                       ButtonUVCommand(self, index, state, element.button_uvs[state], uv))
            self.undo_stack.push(command)
        if resize:
            self.undo_stack.push(GeometryCommand(self, index, element.geometry, geometry))
        self.undo_stack.endMacro()

    def apply_button_uv(self, index: int, state: str, uv: UVRect) -> None:
        assert self.document is not None
        self.document.set_button_uv(index, state, uv)
        self._update_title()

    def apply_texture(self, index: int, name: str) -> None:
        assert self.document is not None
        self.document.set_texture(index, name)
        self._refresh_element_texture(index)
        if self.selected_index == index:
            self.properties.set_element(self.document.elements[index])
        self._watch_texture_files()
        self._update_title()

    def change_selected_texture(self) -> None:
        """Troca o BGmap do controle: outro .dds da UI, uma cópia para editar ou um de fora."""
        if self.document is None or self.selected_index is None or self.texture_cache is None:
            return
        index = self.selected_index
        if index in self.locked_indexes or not self.document.texture_editable(index):
            return
        current = self.document.elements[index].texture_name or ""
        folder = self.texture_cache.ui_directory
        menu = QMenu(self)
        use_other = menu.addAction(self.tr("Usar outro .dds desta UI…"))
        copy_current = menu.addAction(self.tr("Criar cópia de {name} para editar…").format(name=current))
        copy_current.setEnabled(bool(current) and self.texture_cache.path_for(current) is not None)
        bring = menu.addAction(self.tr("Trazer .dds de outra pasta…"))
        button = self.properties.change_texture_button
        chosen = menu.exec(button.mapToGlobal(button.rect().bottomLeft()))
        if chosen is None:
            return
        name = None
        if chosen is use_other:
            names = sorted(
                (path.name for path in folder.iterdir() if path.suffix.lower() in (".dds", ".tga") and path.is_file()),
                key=str.lower,
            )
            if not names:
                return
            name, accepted = QInputDialog.getItem(
                self, self.tr("Trocar .dds"), self.tr("Textura para este controle:"),
                names, names.index(current) if current in names else 0, False,
            )
            if not accepted:
                return
        elif chosen is copy_current:
            source = self.texture_cache.path_for(current)
            suggestion = f"{Path(current).stem}_custom{Path(current).suffix or '.dds'}"
            name, accepted = QInputDialog.getText(
                self, self.tr("Criar cópia do .dds"), self.tr("Nome do novo arquivo (fica na pasta da UI):"), text=suggestion
            )
            name = name.strip()
            if not accepted or not name:
                return
            if not name.lower().endswith((".dds", ".tga")):
                name += ".dds"
            target = folder / name
            if target.exists():
                QMessageBox.warning(self, self.tr("Criar cópia do .dds"), self.tr("Já existe {name} nesta pasta.").format(name=name))
                return
            try:
                shutil.copy2(source, target)
            except OSError as exc:
                QMessageBox.critical(self, self.tr("Criar cópia do .dds"), str(exc))
                return
        elif chosen is bring:
            filename, _filter = QFileDialog.getOpenFileName(
                self, self.tr("Trazer .dds"), "", self.tr("Texturas (*.dds *.tga)")
            )
            if not filename:
                return
            source = Path(filename)
            name = source.name
            target = folder / name
            if os.path.normcase(str(source.resolve())) != os.path.normcase(str(target.resolve())):
                if target.exists():
                    answer = QMessageBox.question(
                        self, self.tr("Trazer .dds"),
                        self.tr("Já existe {name} nesta UI. Substituir?").format(name=name),
                    )
                    if answer != QMessageBox.StandardButton.Yes:
                        return
                    if self.project is not None and self.project.contains(target):
                        self.project.remember_original(target)
                        shutil.copy2(target, self.project.history_path_for(target))
                try:
                    shutil.copy2(source, target)
                except OSError as exc:
                    QMessageBox.critical(self, self.tr("Trazer .dds"), str(exc))
                    return
                self.texture_cache.invalidate(target)
        if not name or name == current:
            return
        if self.project is not None:
            self.project.files(refresh=True)
            self._refresh_files()
        changes = {index: (current, name)}
        others = [
            element.index
            for element in self.document.elements
            if element.index != index
            and element.texture_name == current
            and element.index not in self.locked_indexes
            and self.document.texture_editable(element.index)
        ]
        if others:
            answer = QMessageBox.question(
                self,
                self.tr("Trocar .dds"),
                self.tr("Trocar também nos outros {count} controle(s) deste XML que usam {old}?").format(
                    count=len(others), old=current
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes:
                changes.update({other: (current, name) for other in others})
        self.undo_stack.push(TextureCommand(self, changes))
        self.statusBar().showMessage(
            self.tr("{count} controle(s) agora usam {name}. Salve para gravar.").format(count=len(changes), name=name), 8000
        )

    def open_selected_atlas(self) -> None:
        if self._textures_pending:
            self.statusBar().showMessage(self.tr("Aguarde o carregamento das texturas para abrir o atlas."), 4000)
            return
        if (
            self.document is None
            or self.texture_cache is None
            or self.selected_index is None
        ):
            return
        index = self.selected_index
        element = self.document.elements[index]
        if not element.texture_name or element.uv is None:
            self.statusBar().showMessage(
                self.tr("Este elemento não possui uma textura NorUV editável."), 4000
            )
            return
        pixmap = self.texture_cache.source_pixmap(element.texture_name)
        if pixmap is None:
            self.statusBar().showMessage(
                self.tr("Não foi possível abrir {name}.").format(name=element.texture_name), 5000
            )
            return
        if self.atlas_dialog is not None:
            self.atlas_dialog.close()
        dialog = AtlasDialog(
            element.texture_name,
            pixmap,
            element.uv,
            lambda uv, resize, offset, item_index=index: self.edit_uv(
                item_index, uv, resize, offset
            ),
            self,
            progress_offset=element.progress_offset,
            offset_editable=self.document.offsets_editable,
            texture_path=self.texture_cache.path_for(element.texture_name),
            button_uvs=(element.button_uvs if "ButtonNode" in element.child_tags
                        and self.document.button_states_editable else None),
            apply_button_uvs=lambda states, resize, item_index=index: self.edit_button_uvs(item_index, states, resize),
        )
        dialog.finished.connect(self._atlas_dialog_closed)
        self.atlas_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _atlas_dialog_closed(self, _result: int = 0) -> None:
        self.atlas_dialog = None

    def _refresh_element_texture(self, index: int) -> None:
        if self.document is None or self.texture_cache is None:
            return
        element = self.document.elements[index]
        if element.texture_name in self._textures_pending:
            return
        self.items[index].set_pixmap(self.texture_cache.pixmap_for(element))

    def reload_all_textures(self) -> None:
        if self.project is not None:
            self.project.files(refresh=True)
        self._refresh_files()
        if self.document is None or self.texture_cache is None:
            self.statusBar().showMessage(self.tr("Lista de arquivos atualizada."), 4000)
            return
        if self._textures_pending:
            self.statusBar().showMessage(
                self.tr("Lista de arquivos atualizada. Aguarde o carregamento das texturas."), 4000
            )
            return
        self.texture_cache.invalidate()
        for index in self.items:
            self._refresh_element_texture(index)
        self._reload_open_atlas()
        self._watch_texture_files()
        self.statusBar().showMessage(self.tr("Arquivos e texturas atualizados do disco."), 4000)

    def _watch_texture_files(self, enabled: bool | None = None) -> None:
        watched = self.texture_watcher.files()
        if watched:
            self.texture_watcher.removePaths(watched)
        if (
            self.document is None
            or self.texture_cache is None
            or not self.watch_textures_action.isChecked()
        ):
            return
        paths = {
            str(path)
            for element in self.document.elements
            if element.texture_name
            for path in [self.texture_cache.path_for(element.texture_name)]
            if path is not None and path.exists()
        }
        if paths:
            self.texture_watcher.addPaths(sorted(paths))

    def _texture_file_changed(self, filename: str) -> None:
        QTimer.singleShot(300, lambda path=Path(filename): self._reload_texture(path))

    def _reload_texture(self, texture_path: Path, attempts: int = 5) -> None:
        if self.document is None or self.texture_cache is None:
            return
        if not texture_path.exists():
            if attempts > 0:
                QTimer.singleShot(
                    500,
                    lambda path=texture_path, remaining=attempts - 1: self._reload_texture(
                        path, remaining
                    ),
                )
            else:
                self._watch_texture_files()
                self.statusBar().showMessage(
                    self.tr("A textura {name} não está disponível.").format(name=texture_path.name), 5000
                )
            return
        self.texture_cache.invalidate(texture_path)
        refreshed = 0
        changed_name = texture_path.name.lower()
        for element in self.document.elements:
            if not element.texture_name:
                continue
            if element.texture_name.lower() == changed_name:
                self._refresh_element_texture(element.index)
                refreshed += 1
        self._reload_open_atlas()
        self._watch_texture_files()
        self.statusBar().showMessage(
            self.tr("{name} atualizado automaticamente · elementos: {count}.").format(name=texture_path.name, count=refreshed),
            5000,
        )

    def _reload_open_atlas(self) -> None:
        if self.atlas_dialog is None or self.texture_cache is None:
            return
        pixmap = self.texture_cache.source_pixmap(self.atlas_dialog.texture_name)
        if pixmap is not None:
            self.atlas_dialog.reload_pixmap(pixmap)

    def set_labels_visible(self, visible: bool) -> None:
        for item in self.items.values():
            item.set_labels_visible(visible)

    def set_textures_visible(self, visible: bool) -> None:
        for item in self.items.values():
            item.set_texture_visible(visible)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if (
            watched is self.tree.viewport()
            and event.type() == QEvent.Type.MouseButtonPress
            and event.button() == Qt.MouseButton.LeftButton
        ):
            model_index = self.tree.indexAt(event.position().toPoint())
            if model_index.isValid() and model_index.column() == 3:
                rect = self.tree.visualRect(model_index)
                slot = state_slot_at(rect.left(), event.position().x())
                item = self.tree.itemFromIndex(model_index)
                element_index = item.data(0, Qt.ItemDataRole.UserRole) if item is not None else None
                if slot is not None and element_index is not None:
                    {"hidden": self.toggle_hidden, "locked": self.toggle_lock, "isolated": self.toggle_isolation_of}[slot](
                        int(element_index)
                    )
                    return True  # o clique no ícone não muda a seleção
        return super().eventFilter(watched, event)

    def toggle_selected_lock(self) -> None:
        if self.selected_index is not None:
            self.toggle_lock(self.selected_index)

    def toggle_lock(self, index: int) -> None:
        if index in self.locked_indexes:
            self.locked_indexes.remove(index)
        else:
            self.locked_indexes.add(index)
        self.items[index].set_locked(index in self.locked_indexes)
        if index == self.selected_index:
            self.properties.set_enabled(index not in self.locked_indexes)
        self._refresh_tree_state(index)
        self._update_element_actions()

    def toggle_selected_hidden(self) -> None:
        if self.selected_index is not None:
            self.toggle_hidden(self.selected_index)

    def toggle_hidden(self, index: int) -> None:
        if index in self.hidden_indexes:
            self.hidden_indexes.remove(index)
        else:
            self.hidden_indexes.add(index)
        self._apply_visibility_state()
        self._refresh_tree_state(index)
        self._update_element_actions()

    def toggle_isolation(self) -> None:
        if self.isolated_index is not None:
            self.toggle_isolation_of(self.isolated_index)
        elif self.selected_index is not None:
            self.toggle_isolation_of(self.selected_index)

    def toggle_isolation_of(self, index: int) -> None:
        previous = self.isolated_index
        self.isolated_index = None if previous == index else index
        self._apply_visibility_state()
        if previous is not None:
            self._refresh_tree_state(previous)
        self._refresh_tree_state(index)
        self._update_element_actions()
        self._sync_isolation_warning()

    def _sync_isolation_warning(self) -> None:
        """Isolar some com o resto da janela: o aviso na barra explica e desfaz."""
        if not hasattr(self, "isolation_button"):
            return
        if self.isolated_index is None or self.document is None:
            self.isolation_button.setVisible(False)
            return
        element = self.document.elements[self.isolated_index]
        self.isolation_button.setText(
            self.tr("Isolado: WindowID {id} · mostrar tudo").format(id=element.window_id)
        )
        self.isolation_button.setVisible(True)

    def _apply_visibility_state(self) -> None:
        for index, item in self.items.items():
            visible = index not in self.hidden_indexes
            if self.isolated_index is not None:
                visible = visible and index == self.isolated_index
            item.setVisible(visible)

    def _refresh_tree_state(self, index: int) -> None:
        tree_item = self.tree_items.get(index)
        if tree_item is None:
            return
        states: list[str] = []
        if index in self.locked_indexes:
            states.append(self.tr("Bloqueado"))
        if index in self.hidden_indexes:
            states.append(self.tr("Oculto"))
        if index == self.isolated_index:
            states.append(self.tr("Isolado"))
        tree_item.setToolTip(3, ", ".join(states) or self.tr("Ocultar · Bloquear · Isolar"))
        active = []
        if index in self.hidden_indexes:
            active.append("hidden")
        if index in self.locked_indexes:
            active.append("locked")
        if index == self.isolated_index:
            active.append("isolated")
        tree_item.setData(3, STATE_ROLE, tuple(active))

    def _update_element_actions(self) -> None:
        enabled = self.selected_index is not None
        self.lock_action.setEnabled(enabled)
        self.hide_action.setEnabled(enabled)
        self.isolate_action.setEnabled(enabled)
        structural = enabled and self.selected_index != 0 and self.selected_index not in self.locked_indexes
        self.duplicate_action.setEnabled(structural)
        self.delete_action.setEnabled(structural)
        self.game_hide_action.setEnabled(structural)
        self.new_image_action.setEnabled(self.document is not None)
        self.new_image_button.setEnabled(self.document is not None)
        if enabled and self.document is not None and self.selected_index is not None:
            self.game_hide_action.setChecked(not self.document.elements[self.selected_index].visible)
        atlas_enabled = False
        if enabled and self.document is not None and self.selected_index is not None:
            element = self.document.elements[self.selected_index]
            atlas_enabled = element.texture_name is not None and element.uv is not None
        self.atlas_action.setEnabled(atlas_enabled)
        if not enabled:
            self.lock_action.setText(self.tr("Bloquear selecionado"))
            self.lock_action.setIconText(self.tr("Bloquear"))
            self.hide_action.setText(self.tr("Ocultar selecionado"))
            self.hide_action.setIconText(self.tr("Ocultar"))
            self.isolate_action.setText(self.tr("Isolar selecionado"))
            self.isolate_action.setIconText(self.tr("Isolar"))
            return
        assert self.selected_index is not None
        self.lock_action.setText(
            self.tr("Desbloquear selecionado")
            if self.selected_index in self.locked_indexes
            else self.tr("Bloquear selecionado")
        )
        self.lock_action.setIconText(
            self.tr("Desbloquear") if self.selected_index in self.locked_indexes else self.tr("Bloquear")
        )
        self.hide_action.setText(
            self.tr("Mostrar selecionado")
            if self.selected_index in self.hidden_indexes
            else self.tr("Ocultar selecionado")
        )
        self.hide_action.setIconText(
            self.tr("Mostrar") if self.selected_index in self.hidden_indexes else self.tr("Ocultar")
        )
        self.isolate_action.setText(
            self.tr("Mostrar todos") if self.isolated_index is not None else self.tr("Isolar selecionado")
        )
        self.isolate_action.setIconText(
            self.tr("Mostrar todos") if self.isolated_index is not None else self.tr("Isolar")
        )

    def filter_tree(self, text: str) -> None:
        if self.document is None:
            return
        query = text.strip().casefold()

        def visit(item: QTreeWidgetItem) -> bool:
            index = item.data(0, Qt.ItemDataRole.UserRole)
            own_match = not query
            if isinstance(index, int):
                element = self.document.elements[index]
                searchable = " ".join(
                    (
                        element.window_id,
                        kind_label(element.kind, element.ctrl_type),
                        element.parent_id or "",
                        element.window_text,
                        element.texture_name or "",
                        element.ctrl_type or "",
                    )
                ).casefold()
                own_match = not query or query in searchable
            child_match = False
            for child_index in range(item.childCount()):
                child_match = visit(item.child(child_index)) or child_match
            visible = own_match or child_match
            item.setHidden(not visible)
            if query and child_match:
                item.setExpanded(True)
            return visible

        for top_index in range(self.tree.topLevelItemCount()):
            visit(self.tree.topLevelItem(top_index))

    def fit_scene(self) -> None:
        if not self.items:
            return
        if self.game_screen_item is not None:
            # Preview frames the game screen, not controls parked off-screen by
            # a custom UI. Ignore the caption, which ignores view transforms.
            bounds = self.game_screen_item.mapRectToScene(self.game_screen_item.rect())
        else:
            root = self.items[0]
            bounds = root.mapRectToScene(root.rect())
            # Without a screen preview, include nearby layout (even outside the
            # root panel) but not distant controls used to hide artwork in-game.
            neighborhood = bounds.adjusted(
                -max(1920, bounds.width()), -max(1080, bounds.height()),
                max(1920, bounds.width()), max(1080, bounds.height()),
            )
            for item in self.items.values():
                item_bounds = item.mapRectToScene(item.rect())
                if item.isVisible() and neighborhood.intersects(item_bounds):
                    bounds = bounds.united(item_bounds)
        self.view.fitInView(bounds.adjusted(-20, -20, 20, 20), Qt.AspectRatioMode.KeepAspectRatio)
        self.view.notify_zoom()

    def save_document(self) -> None:
        if self.document is None:
            return
        if not self.document.is_dirty:
            self.statusBar().showMessage(self.tr("Nenhuma alteração para salvar."), 4000)
            return
        if not self._confirm_diff_preview():
            return
        in_project = self.project is not None and self.project.contains(self.document.path)
        if in_project:
            try:
                self.project.remember_original(self.document.path)
            except OSError:
                pass
        try:
            backup = self.document.save(
                self.project.history_path_for(self.document.path) if in_project else None
            )
        except ExternalModificationError as exc:
            QMessageBox.warning(self, self.tr("Arquivo alterado externamente"), document_error_text(exc))
            return
        except DocumentError as exc:
            QMessageBox.critical(self, self.tr("Falha ao salvar"), document_error_text(exc))
            return
        self.undo_stack.clear()
        self._update_title()
        if in_project:
            self.project.prune_history(self.document.path)
            self._refresh_official_diff()
            self._refresh_files()
            self.statusBar().showMessage(
                self.tr("Salvo no projeto. O jogo só recebe as mudanças com Enviar para o jogo (F5)."), 10000
            )
            return
        self.statusBar().showMessage(self.tr("Salvo. Backup: {name}").format(name=backup.name), 10000)
        QMessageBox.information(
            self,
            self.tr("XML salvo"),
            self.tr("As alterações foram salvas.\n\nBackup exato:\n{path}").format(path=backup),
        )

    # ---- visual --------------------------------------------------------------
    def _build_empty_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("emptyPage")
        outer = QVBoxLayout(page)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        column = QWidget()
        column.setObjectName("transparent")
        column.setFixedWidth(620)
        layout = QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)
        title = QLabel()
        title.setObjectName("heroTitle")
        self.hero_title = title
        subtitle = QLabel()
        subtitle.setObjectName("heroSubtitle")
        self.hero_subtitle = subtitle
        subtitle.setWordWrap(True)
        cards = QHBoxLayout()
        cards.setSpacing(12)
        for icon_name, heading, text, slot, accent in (
            ("folder-plus", self.tr("Novo projeto"), self.tr("A partir da UI em uso, de uma UI do UICustom ou de outra pasta."), lambda: self.new_project(), True),
            ("file", self.tr("Abrir um XML solto"), self.tr("Edita direto no arquivo, sem projeto (o launcher pode sobrescrever)."), self.choose_document, False),
        ):
            card = QPushButton()
            card.setObjectName("accentCard" if accent else "startCard")
            card.setAccessibleName(heading)
            card.setMinimumHeight(132)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(16, 16, 16, 16)
            card_layout.setSpacing(8)
            glyph = QLabel()
            glyph.setPixmap(icon(icon_name, COLORS["ACCENT_TEXT"] if accent else COLORS["ICON"], 22).pixmap(22, 22))
            heading_label = QLabel(heading)
            heading_label.setObjectName("cardHeading")
            text_label = QLabel(text)
            text_label.setObjectName("panelSubtitle")
            text_label.setWordWrap(True)
            for label in (glyph, heading_label, text_label):
                label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                card_layout.addWidget(label)
            card_layout.addStretch(1)
            card.clicked.connect(slot)
            cards.addWidget(card)
        recent_label = QLabel(self.tr("RECENTES"))
        recent_label.setObjectName("sectionLabel")
        self.recent_box = QWidget()
        self.recent_box.setObjectName("recentBox")
        self.recent_layout = QVBoxLayout(self.recent_box)
        self.recent_layout.setContentsMargins(0, 0, 0, 0)
        self.recent_layout.setSpacing(0)
        key = f"<span style='font-family:\"{MONO_FONT}\";color:{COLORS['TEXT_PRIMARY']};background:{COLORS['BUTTON_HOVER_BG']}'>&nbsp;%s&nbsp;</span>"
        shortcuts = QLabel(
            self.tr("{a} novo projeto &nbsp;&nbsp;&nbsp; {b} abrir projeto &nbsp;&nbsp;&nbsp; {c} testar no jogo").format(
                a=key % "Ctrl+Shift+N", b=key % "Ctrl+Shift+O", c=key % "F5"
            )
        )
        shortcuts.setObjectName("panelSubtitle")
        shortcuts.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addLayout(cards)
        layout.addSpacing(8)
        layout.addWidget(recent_label)
        layout.addWidget(self.recent_box)
        layout.addWidget(shortcuts)
        outer.addWidget(column)
        self.recent_label = recent_label
        return page

    def _recent_projects(self, limit: int) -> list[Path]:
        return sorted(
            list_projects(), key=lambda root: (root / "project.json").stat().st_mtime, reverse=True
        )[:limit]

    def _fill_recent_menu(self) -> None:
        self.recent_menu.clear()
        current = os.path.normcase(str(self.project.root)) if self.project is not None else None
        projects = self._recent_projects(15)
        for root in projects:
            action = self.recent_menu.addAction(icon("package"), root.name)
            action.setToolTip(str(root))
            if os.path.normcase(str(root)) == current:
                action.setCheckable(True)
                action.setChecked(True)
            action.triggered.connect(lambda _checked=False, path=root: self.switch_project(path))
        if not projects:
            empty = self.recent_menu.addAction(self.tr("Nenhum projeto ainda"))
            empty.setEnabled(False)
        self.recent_menu.addSeparator()
        browse = self.recent_menu.addAction(self.tr("Procurar pasta…"))
        browse.triggered.connect(self._browse_project)

    def switch_project(self, root: Path) -> None:
        if not self._confirm_discard_changes():
            return
        self.open_project(root)

    def close_document(self) -> None:
        """Volta ao estado sem XML aberto (mostra a tela inicial no centro)."""
        self.document = None
        self._texture_generation += 1
        self.undo_stack.clear()
        self.selected_index = None
        self.locked_indexes.clear()
        self.hidden_indexes.clear()
        self.isolated_index = None
        self._sync_isolation_warning()
        self.scene.clear()
        self.reference_layer_items = []  # a cena apagou os itens
        self.items.clear()
        self.tree.clear()
        self.tree_items.clear()
        self.properties.set_element(None)
        self.save_action.setEnabled(False)
        self.fit_action.setEnabled(False)
        self._watch_texture_files()
        self._update_element_actions()
        self._update_title()
        self._refresh_files()

    def go_home(self) -> None:
        if self.document is None or not self._confirm_discard_changes():
            return
        self.close_document()

    def _refresh_recent_projects(self) -> None:
        while self.recent_layout.count():
            widget = self.recent_layout.takeAt(0).widget()
            if widget is not None:
                # Fora do layout ele ainda é desenhado até o deleteLater rodar: sem isto,
                # redesenhos seguidos empilham as linhas antigas sobre as novas.
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        projects = self._recent_projects(5)
        self.recent_label.setVisible(bool(projects))
        self.recent_box.setVisible(bool(projects))
        for root in projects:
            try:
                project = Project.load(root)
                title = project.name
                details = self.tr("{count} arquivos · {path}").format(count=len(project.base_hashes), path=root.parent.name)
            except (OSError, ValueError):
                title, details = root.name, str(root)
            button = QPushButton(f"{title}\n{details}")
            button.setToolTip(str(root))
            button.setObjectName("recentRow")
            button.setIcon(icon("package", COLORS["ACCENT_TEXT"]))
            button.clicked.connect(lambda _checked=False, path=root: self.switch_project(path))
            self.recent_layout.addWidget(button)

    def _update_center_page(self) -> None:
        if self.document is None:
            if self.project is not None:
                self.hero_title.setText(self.project.name)
                self.hero_subtitle.setText(
                    self.tr("Escolha um XML na aba Arquivos para começar a editar. Os alterados aparecem no topo; F5 publica no jogo.")
                )
            else:
                self.hero_title.setText(self.tr("Comece um projeto de UI"))
                self.hero_subtitle.setText(
                    self.tr("Você edita uma cópia fora da pasta do jogo. Quando quiser ver o resultado, aperte F5 para enviar ao jogo e inicie-o pelo launcher.")
                )
            self._refresh_recent_projects()
            self.center_stack.setCurrentWidget(self.empty_page)
        else:
            self.center_stack.setCurrentWidget(self.canvas_page)

    def _build_canvas_overlays(self) -> None:
        bar = QFrame(self.view)
        bar.setObjectName("floatingBar")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(4, 4, 4, 4)
        bar_layout.setSpacing(2)

        def bar_button(text: str = "", action: QAction | None = None) -> QToolButton:
            button = QToolButton()
            button.setObjectName("pill")
            if action is not None:
                button.setDefaultAction(action)
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
                button.setIconSize(QSize(15, 15))
            else:
                button.setText(text)
            bar_layout.addWidget(button)
            return button

        bar_button(action=self.preview_action)
        self.resolution_button = bar_button()
        self.resolution_button.setIcon(icon("monitor", size=15))
        self.resolution_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.resolution_button.setMenu(self.resolution_menu)
        self.resolution_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        background_menu = QMenu(self)
        background_menu.addAction(self.builtin_background_action)
        background_menu.addAction(self.background_action)
        background_menu.addAction(self.no_background_action)
        self.background_button = bar_button(self.tr("Fundo"))
        self.background_button.setIcon(icon("image", size=15))
        self.background_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.background_button.setMenu(background_menu)
        self.background_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        user_ini = bar_button(action=self.saved_positions_action)
        user_ini.setText("User.ini")
        self.saved_positions_action.changed.connect(lambda: user_ini.setText("User.ini"))
        self.game_drawn_button = bar_button(action=self.game_drawn_action)
        layers_menu = QMenu(self)
        layers_menu.addAction(self.tr("Montar HUD padrão"), self.build_default_hud)
        layers_menu.addAction(self.tr("Limpar camadas"), lambda: self.set_reference_layers([]))
        self.layers_button = bar_button(self.tr("Camadas"))
        self.layers_button.setIcon(icon("layers", size=15))
        self.layers_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.layers_button.setMenu(layers_menu)
        self.layers_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.layers_button.setToolTip(
            self.tr("Outras janelas do projeto, onde o jogo as desenha. Marque arquivos no painel Arquivos ou monte o HUD padrão.")
        )
        self.text_mode_button = bar_button(self.tr("Texto"))
        self.text_mode_button.setIcon(icon("type", size=15))
        self.text_mode_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.text_mode_button.setMenu(self.text_mode_menu)
        self.text_mode_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.text_mode_button.setToolTip(self.tr("Texto como no jogo: amostras com a fonte do jogo e aviso quando não cabem"))
        self.game_drawn_button.setVisible(False)
        # Aviso de posição manual: o preview deixa de seguir o jogo neste arquivo.
        self.manual_position_button = bar_button(self.tr("Posição manual · voltar ao automático"))
        self.manual_position_button.setObjectName("pillWarning")
        self.manual_position_button.setToolTip(
            self.tr(
                "Neste arquivo o preview usa uma posição escolhida à mão (Visualização → Posição da janela no preview) "
                "e pode não mostrar onde a janela aparece no jogo. Clique para voltar a seguir o jogo."
            )
        )
        self.manual_position_button.clicked.connect(lambda: self.set_root_mode("auto"))
        self.manual_position_button.setVisible(False)
        self.isolation_button = bar_button("")
        self.isolation_button.setObjectName("pillWarning")
        self.isolation_button.setToolTip(self.tr("Só o elemento isolado está à mostra. Clique para mostrar tudo de novo."))
        self.isolation_button.clicked.connect(self.toggle_isolation)
        self.isolation_button.setVisible(False)
        self.view.add_overlay(bar, "top")

        zoom = QFrame(self.view)
        zoom.setObjectName("floatingBar")
        zoom_layout = QHBoxLayout(zoom)
        zoom_layout.setContentsMargins(3, 3, 3, 3)
        zoom_layout.setSpacing(2)
        zoom_out = QToolButton()
        zoom_out.setObjectName("pill")
        zoom_out.setIcon(icon("minus", size=15))
        zoom_out.setToolTip(self.tr("Diminuir zoom"))
        zoom_out.clicked.connect(lambda: self.view.zoom_by(1 / 1.25))
        self.zoom_label = QLabel("100%")
        self.zoom_label.setObjectName("zoomLabel")
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.zoom_label.setMinimumWidth(48)
        zoom_in = QToolButton()
        zoom_in.setObjectName("pill")
        zoom_in.setIcon(icon("plus", size=15))
        zoom_in.setToolTip(self.tr("Aumentar zoom"))
        zoom_in.clicked.connect(lambda: self.view.zoom_by(1.25))
        fit = QToolButton()
        fit.setObjectName("pill")
        fit.setDefaultAction(self.fit_action)
        fit.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        fit.setIconSize(QSize(15, 15))
        for widget in (zoom_out, self.zoom_label, zoom_in, fit):
            zoom_layout.addWidget(widget)
        self.view.zoom_changed.connect(lambda factor: self.zoom_label.setText(f"{round(factor * 100)}%"))
        self.view.add_overlay(zoom, "bottom-left")

    def _build_status_chips(self) -> None:
        self.status_chips: list[QLabel] = []
        for _ in range(4):
            chip = QLabel()
            chip.setObjectName("chip")
            chip.setVisible(False)
            self.statusBar().addWidget(chip)
            self.status_chips.append(chip)
        self.reference_chip = QToolButton()
        self.reference_chip.setObjectName("chip")
        self.reference_chip.setVisible(False)
        self.reference_chip.setToolTip(self.tr("Cópia da UI oficial usada para comparar e achar controles que faltam"))
        self.reference_chip.clicked.connect(lambda: self.open_official_reference())
        self.statusBar().addPermanentWidget(self.reference_chip)
        self.cursor_position_label.setObjectName("monoCaption")

    def _update_status_chips(self) -> None:
        texts: list[str] = []
        if self.document is not None:
            texts.append(self.tr("{count} elementos").format(count=len(self.document.elements)))
            changed = sum(1 for element in self.document.elements if element.changed_attributes or element.original_uv != element.uv)
            if changed:
                texts.append(self.tr("{count} alteração(ões) não salva(s)").format(count=changed))
        pending = 0
        if self.project is not None:
            texts.append(self.tr("{name} → UICustom").format(name=self.project.custom_name))
            try:
                pending = len(self.project.unpublished_files())
            except OSError:
                pending = 0
            if pending:
                texts.append(self.tr("{count} arquivo(s) ainda não publicados no jogo · F5").format(count=pending))
        for chip, text in zip(self.status_chips, texts + [""] * 4):
            chip.setText(text)
            chip.setVisible(bool(text))
            chip.setObjectName("chip")
        if pending:
            self.status_chips[len(texts) - 1].setObjectName("chipWarning")
        for chip in self.status_chips:
            chip.style().unpolish(chip)
            chip.style().polish(chip)
        self._update_reference_chip()

    def _update_reference_chip(self) -> None:
        game_dir = self._document_game_dir() or self._game_dir()
        if game_dir is None or not (game_dir / "GameDataFileList.txt").is_file():
            self.reference_chip.setVisible(False)
            self.reference_banner.setVisible(False)
            return
        ready = reference_ready(game_dir)
        self.reference_banner.setVisible(not ready and not self.reference_banner_dismissed)
        self.reference_chip.setText(
            self.tr("UI oficial: guardada") if ready else self.tr("UI oficial: não guardada · guardar")
        )
        self.reference_chip.setObjectName("chip" if ready else "chipWarning")
        self.reference_chip.style().unpolish(self.reference_chip)
        self.reference_chip.style().polish(self.reference_chip)
        self.reference_chip.setVisible(True)

    def _dismiss_reference_banner(self) -> None:
        self.reference_banner_dismissed = True
        self.reference_banner.setVisible(False)

    def open_official_reference(self) -> None:
        game_dir = self._document_game_dir() or self._game_dir()
        if game_dir is None:
            QMessageBox.information(
                self,
                self.tr("UI oficial de referência"),
                self.tr("Defina a pasta do jogo primeiro (Arquivo → Novo projeto → Pasta do jogo)."),
            )
            return
        OfficialUIDialog(game_dir, self).exec()
        self._update_reference_chip()
        self._start_official_scan()

    def _update_breadcrumb(self) -> None:
        parts = []
        if self.project is not None:
            parts.append(f"<span style='color:{COLORS['TEXT_BRIGHT']};font-weight:500'>{self.project.name}</span>")
        if self.document is not None:
            parts.append(f"<span style='font-family:\"{MONO_FONT}\";font-size:12px'>{self.document.path.name}</span>")
        text = f"<span style='color:{COLORS['TEXT_MUTED']}'> / </span>".join(parts)
        if self.document is not None and self.document.is_dirty:
            text += f" <span style='color:{COLORS['SELECTION_GOLD']}'>●</span>"
        self.breadcrumb.setText(text)
        self.breadcrumb_action.setVisible(bool(parts))

    # ---- projetos ---------------------------------------------------------
    def _game_dir(self) -> Path | None:
        if self.project is not None and self.project.game_dir is not None:
            return self.project.game_dir
        saved = str(QSettings("Local", "GF UI Editor").value("game_dir", ""))
        if saved and Path(saved).is_dir():
            return normalize_game_dir(Path(saved))
        game_dir = DEFAULT_UI_DIRECTORY.parent
        return game_dir if game_dir.is_dir() else None

    def new_project(self, loose_dir: Path | None = None, focus: Path | None = None) -> bool:
        if not self._confirm_discard_changes():
            return False
        if focus is None and self.document is not None and loose_dir is not None:
            focus = self.document.path
        dialog = NewProjectDialog(self._game_dir(), self, loose_dir=loose_dir)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.source_dir is None:
            return False
        game_dir = dialog.game_dir
        if game_dir is not None:
            QSettings("Local", "GF UI Editor").setValue("game_dir", str(game_dir))
        try:
            name, source = dialog.name_edit.text().strip(), dialog.source_dir
            include_assets = dialog.assets_check.isChecked()
            publish_folder = dialog.publish_folder

            def build(progress):
                if not source.exists():
                    raise FileNotFoundError(str(source))
                if source.is_file():  # .zip: extrai para uma pasta temporária e parte dela
                    with tempfile.TemporaryDirectory() as folder:
                        return Project.create(
                            name, extract_ui_zip(source, Path(folder)), game_dir, progress=progress,
                            include_assets=include_assets, publish_folder=publish_folder,
                        )
                return Project.create(
                    name, source, game_dir, progress=progress, include_assets=include_assets,
                    publish_folder=publish_folder,
                )

            project = self._run_with_progress(self.tr("Copiando arquivos da UI para o projeto…"), build)
            for loose in dialog.loose_files:
                target, _backup = project.import_file(loose)
                if focus is not None and loose == focus:
                    focus = target
        except FileExistsError as exc:
            QMessageBox.warning(
                self, self.tr("Projeto já existe"), self.tr("Já existe um projeto em {path}.").format(path=exc.args[0])
            )
            return False
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            QMessageBox.critical(self, self.tr("Não foi possível criar o projeto"), str(exc))
            return False
        self.open_project(project.root)
        if focus is not None:
            if not project.contains(focus):
                focus = project.import_target(focus)
            if focus.is_file():
                self.document = None
                self.open_document(focus)
        self.statusBar().showMessage(
            self.tr("Projeto criado com {count} arquivos.").format(count=len(project.base_hashes)), 8000
        )
        return True

    # ---- UI oficial --------------------------------------------------------
    def _project_base_bytes(self, relative: str) -> bytes | None:
        """O arquivo como era na criação do projeto (para saber de qual versão oficial partiu)."""
        project = self.project
        if project is None:
            return None
        path = project.ui_dir / relative
        original = project.original_path_for(path)
        try:
            if original.is_file():
                return original.read_bytes()
            data = path.read_bytes()
        except OSError:
            return None
        key = Path(relative).as_posix()
        return data if project.base_hashes.get(key) == hashlib.sha1(data).hexdigest() else None

    def _start_official_scan(self) -> None:
        """Compara a UI do projeto com a oficial em segundo plano (a janela não trava)."""
        project = self.project
        if project is None or project.game_dir is None:
            return
        game_dir, ui_dir, root = project.game_dir, project.ui_dir, project.root
        base_bytes = self._project_base_bytes
        signals = self._scan_signals

        def work() -> None:
            try:
                snapshot_official_ui(game_dir)
                diffs, unavailable = scan_official(game_dir, ui_dir, base_bytes)
            except Exception:  # noqa: BLE001 - a comparação é só um aviso
                return
            signals.done.emit((root, diffs, unavailable))

        Thread(target=work, daemon=True).start()

    def _official_scan_done(self, result) -> None:
        root, diffs, unavailable = result
        if self.project is None or self.project.root != root:
            return
        self._official_diffs = diffs
        self._official_unavailable = unavailable
        self._refresh_files()
        self._update_official_banner()

    def _official_key(self) -> str | None:
        if self.document is None:
            return None
        if self.project is not None and self.project.contains(self.document.path):
            return self.document.path.resolve().relative_to(self.project.ui_dir.resolve()).as_posix().lower()
        return self.document.path.name.lower()

    def _update_official_banner(self) -> None:
        key = self._official_key()
        diff = self._official_diffs.get(key) if key is not None else None
        show = bool(diff and diff.new_ids) and key not in self._dismissed_banners
        if show:
            self.official_banner_text.setText(
                self.tr("A atualização do jogo trouxe {count} controle(s) que este arquivo não tem ({ids}).").format(
                    count=len(diff.new_ids), ids=", ".join(diff.new_ids[:6]) + ("…" if len(diff.new_ids) > 6 else "")
                )
            )
        self.official_banner.setVisible(show)
        has_document = self.document is not None
        self.official_compare_action.setEnabled(has_document)
        self.official_button.setEnabled(has_document)

    def _dismiss_official_banner(self) -> None:
        key = self._official_key()
        if key is not None:
            self._dismissed_banners.add(key)
        self._update_official_banner()

    def _refresh_official_diff(self) -> None:
        """Recalcula a diferença do arquivo aberto depois de salvar."""
        project, key = self.project, self._official_key()
        if project is None or project.game_dir is None or key is None or self.document is None:
            return
        relative = self.document.path.resolve().relative_to(project.ui_dir.resolve()).as_posix()
        diff = file_diff(project.game_dir, project.ui_dir, relative, self._project_base_bytes)
        if diff is None:
            self._official_diffs.pop(key, None)
        else:
            self._official_diffs[key] = diff
        self._refresh_files()
        self._update_official_banner()

    def open_official_compare(self, focus_id: str | None = None) -> None:
        if self.document is None:
            return
        game_dir = self._document_game_dir()
        relative = self._official_key() or self.document.path.name
        official = official_text_for(game_dir, relative) if game_dir is not None else None
        if official is None:
            answer = QMessageBox.question(
                self,
                self.tr("UI oficial indisponível"),
                self.tr("Não há cópia oficial de {file} para comparar. Guardar a UI oficial agora?").format(
                    file=self.document.path.name
                ),
            )
            if answer == QMessageBox.StandardButton.Yes:
                self.open_official_reference()
            return
        current = self.document.render_text()
        missing = missing_controls(current, official)
        if not missing:
            QMessageBox.information(
                self,
                self.tr("Controles da UI oficial"),
                self.tr("{file} já tem todos os controles da UI oficial.").format(file=self.document.path.name),
            )
            return
        diff = self._official_diffs.get(relative.lower())
        new_ids = [window_id for window_id in missing if diff is not None and window_id in diff.new_ids]
        other_ids = [window_id for window_id in missing if window_id not in new_ids]
        dialog = OfficialControlsDialog(
            self.document.path.name, new_ids, other_ids, control_info(official, missing), focus_id, self
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        text, inserted = insert_controls(current, official, set(dialog.selected_ids()))
        if not inserted:
            return
        try:
            new_document = self.document.with_text(text)
        except DocumentError as exc:
            QMessageBox.critical(self, self.tr("Não foi possível adicionar"), document_error_text(exc))
            return
        self.undo_stack.push(StructureCommand(self, self.document, new_document, inserted))
        self.statusBar().showMessage(
            self.tr("{count} controle(s) do oficial adicionado(s). Ajuste a posição se precisar; salve para gravar.").format(
                count=len(inserted)
            ),
            10000,
        )

    def _swap_document(self, document: UIDocument, select_ids: list[str]) -> None:
        """Mostra outro estado do mesmo arquivo (inserção de controles e o desfazer dela)."""
        self.document = document
        self.selected_index = None
        self.locked_indexes.clear()
        self.hidden_indexes.clear()
        self.isolated_index = None
        self._sync_isolation_warning()
        self.properties.set_element(None)
        self._rebuild_scene()
        self._rebuild_tree()
        self._watch_texture_files()
        self._update_element_actions()
        self._update_title()
        wanted = set(select_ids)
        indexes = [index for index, element in enumerate(document.elements) if element.window_id in wanted]
        if indexes:
            self.select_element(indexes[0])
            for index in indexes[1:]:
                item = self.items.get(index)
                if item is not None:
                    item.setSelected(True)

    # ---- criar, duplicar e apagar controles ---------------------------------
    def _official_ids(self) -> set[str] | None:
        """WindowIDs que a versão oficial deste XML tem (os que o jogo pode procurar)."""
        if self.document is None:
            return None
        game_dir = self._document_game_dir()
        relative = self._official_key() or self.document.path.name
        official = official_text_for(game_dir, relative) if game_dir is not None else None
        return window_ids(official) if official is not None else None

    def _push_structure(self, text: str, select: list[str]) -> bool:
        assert self.document is not None
        try:
            new_document = self.document.with_text(text)
        except DocumentError as exc:
            QMessageBox.critical(self, self.tr("Não foi possível alterar"), document_error_text(exc))
            return False
        self.undo_stack.push(StructureCommand(self, self.document, new_document, select))
        return True

    def _structure_error(self, error: ControlError) -> None:
        messages = {
            "has_children": self.tr("Este controle é uma janela com outros controles dentro; isso ainda não é suportado."),
            "id_in_use": self.tr("Esse WindowID já existe neste arquivo."),
        }
        QMessageBox.information(self, self.tr("Controles"), messages.get(error.code, self.tr("Não foi possível alterar este controle.")))

    def duplicate_selected(self) -> None:
        if self.document is None or self.selected_index in (None, 0):
            return
        element = self.document.elements[self.selected_index]
        text = self.document.render_text()
        new_id = free_window_id(text, element.window_id, self._official_ids() or set())
        try:
            new_text = duplicate_control(text, element.window_id, new_id)
        except ControlError as error:
            self._structure_error(error)
            return
        if self._push_structure(new_text, [new_id]):
            self.statusBar().showMessage(
                self.tr("Cópia criada com o WindowID {id}. É decorativa: o jogo não usa esse ID, então botões e barras copiados não funcionam.").format(id=new_id),
                12000,
            )

    def delete_selected(self) -> None:
        if self.document is None or self.selected_index in (None, 0):
            return
        element = self.document.elements[self.selected_index]
        official = self._official_ids()
        if official is None or element.window_id in official:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Warning)
            box.setWindowTitle(self.tr("Apagar controle"))
            box.setText(
                self.tr("O jogo pode procurar o controle {id}. Apagá-lo pode causar \"Child control can not found\".").format(id=element.window_id)
                if official is not None
                else self.tr("Sem a UI oficial para conferir, não dá para saber se o jogo usa o controle {id}.").format(id=element.window_id)
            )
            box.setInformativeText(self.tr("Ocultar no jogo tira o controle da tela sem esse risco."))
            hide = box.addButton(self.tr("Ocultar no jogo"), QMessageBox.ButtonRole.AcceptRole)
            delete = box.addButton(self.tr("Apagar mesmo assim"), QMessageBox.ButtonRole.DestructiveRole)
            box.addButton(self.tr("Cancelar"), QMessageBox.ButtonRole.RejectRole)
            box.setDefaultButton(hide)
            box.exec()
            if box.clickedButton() is hide:
                if element.visible:
                    self.toggle_selected_game_visibility()
                return
            if box.clickedButton() is not delete:
                return
        try:
            new_text = delete_control(self.document.render_text(), element.window_id)
        except ControlError as error:
            self._structure_error(error)
            return
        if self._push_structure(new_text, []):
            self.statusBar().showMessage(self.tr("Controle {id} apagado. Ctrl+Z desfaz.").format(id=element.window_id), 8000)

    def toggle_selected_game_visibility(self) -> None:
        if self.document is None or self.selected_index in (None, 0):
            return
        index = self.selected_index
        element = self.document.elements[index]
        old = element.attrs.get("Visible")
        new = "1" if not element.visible else "0"
        self.undo_stack.push(AttributeCommand(self, index, "Visible", old, new))

    def apply_attribute(self, index: int, name: str, value: str | None) -> None:
        assert self.document is not None
        element = self.document.elements[index]
        if value is None:
            element.attrs.pop(name, None)
        else:
            element.attrs[name] = value
        if self.selected_index == index:
            self.properties.set_element(element)
            self._update_element_actions()
        self._update_title()

    def new_image(self) -> None:
        if self.document is None or self.texture_cache is None:
            return
        text = self.document.render_text()
        selected = self.document.elements[self.selected_index] if self.selected_index is not None else None
        owner = None
        if selected is not None:
            owner = selected.window_id if "Container_Node" in selected.child_tags else owner_of(text, selected.window_id)
        owner = owner or self.document.elements[0].window_id
        folder = self.texture_cache.ui_directory
        names = sorted(
            (path.name for path in folder.iterdir() if path.suffix.lower() in (".dds", ".tga") and path.is_file()),
            key=str.lower,
        )
        if not names:
            QMessageBox.information(self, self.tr("Nova imagem"), self.tr("Não há arquivos .dds na pasta desta UI."))
            return
        default = selected.texture_name if selected is not None and selected.texture_name in names else names[0]
        texture, accepted = QInputDialog.getItem(
            self, self.tr("Nova imagem"), self.tr("Textura da imagem (depois você escolhe o recorte no atlas):"),
            names, names.index(default), False,
        )
        if not accepted:
            return
        owner_element = next((element for element in self.document.elements if element.window_id == owner), self.document.elements[0])
        new_id = free_window_id(text, "1", self._official_ids() or set())
        try:
            new_text = new_image_control(
                text, owner, new_id, texture, UVRect(0, 0, 32, 32), (owner_element.x + 16, owner_element.y + 16)
            )
        except ControlError as error:
            self._structure_error(error)
            return
        if not self._push_structure(new_text, [new_id]):
            return
        self.statusBar().showMessage(self.tr("Imagem {id} criada. Marque o recorte no atlas.").format(id=new_id), 10000)
        QTimer.singleShot(0, self._open_atlas_for_new_image)

    def _open_atlas_for_new_image(self) -> None:
        self.open_selected_atlas()
        dialog = getattr(self, "atlas_dialog", None)
        if dialog is not None:
            dialog.edit_button.setChecked(True)
            dialog.resize_element.setChecked(True)
            dialog.view.fit_texture()

    def resolve_game_error(self) -> None:
        """Do texto do erro do jogo até o XML e o controle que falta."""
        text, accepted = QInputDialog.getMultiLineText(
            self,
            self.tr("Resolver erro do jogo"),
            self.tr("Cole a mensagem de erro do jogo (por exemplo, a que tem \"Child control can not found\"):"),
        )
        if not accepted or not text.strip():
            return
        parsed = parse_game_error(text)
        if parsed is None:
            QMessageBox.information(
                self,
                self.tr("Resolver erro do jogo"),
                self.tr("Não encontrei um arquivo .cpp e um ID=… nessa mensagem."),
            )
            return
        cpp, window_id = parsed
        game_dir = self._document_game_dir() or self._game_dir()
        candidates = error_candidates(game_dir, cpp, window_id) if game_dir is not None else []
        if not candidates and game_dir is not None and self.project is not None:
            # Erro com .cpp genérico (ex.: "Filename.cpp"): procura pelo ID nos XMLs do
            # oficial que o projeto não tem.
            candidates = files_missing_id(game_dir, self.project.ui_dir, window_id)
        if not candidates:
            QMessageBox.information(
                self,
                self.tr("Resolver erro do jogo"),
                self.tr(
                    "Não sei qual XML o {cpp} usa com o ID {id}, ou não há cópia da UI oficial para conferir. "
                    "Escolha \"UI Padrão\" no launcher, clique em Jogar uma vez e tente de novo."
                ).format(cpp=cpp, id=window_id),
            )
            return
        name = candidates[0]
        if len(candidates) > 1:
            name, accepted = QInputDialog.getItem(
                self, self.tr("Resolver erro do jogo"), self.tr("Qual destes arquivos?"), candidates, 0, False
            )
            if not accepted:
                return
        if self.project is not None:
            path = self.project.ui_dir / name
        elif self.document is not None:
            path = self.document.path.parent / name
        else:
            QMessageBox.information(
                self, self.tr("Resolver erro do jogo"), self.tr("O controle {id} fica em {file}. Abra a UI e tente de novo.").format(id=window_id, file=name)
            )
            return
        if not path.is_file():
            QMessageBox.information(
                self, self.tr("Resolver erro do jogo"), self.tr("Esta UI não tem o arquivo {file}.").format(file=name)
            )
            return
        if self.document is None or os.path.normcase(str(self.document.path.resolve())) != os.path.normcase(str(path.resolve())):
            if not self._confirm_discard_changes():
                return
            self.open_document(path)
            if self.document is None:
                return
        if any(element.window_id == window_id for element in self.document.elements):
            QMessageBox.information(
                self,
                self.tr("Resolver erro do jogo"),
                self.tr(
                    "{file} já tem o controle {id}. O erro deve vir de outra coisa no arquivo, como texto solto "
                    "entre as tags; o editor avisa ao abrir quando encontra algo assim."
                ).format(file=name, id=window_id),
            )
            return
        self.open_official_compare(focus_id=window_id)

    def import_files(self) -> None:
        if self.project is None:
            return
        names, _filter = QFileDialog.getOpenFileNames(
            self, self.tr("Importar arquivos para o projeto"), "",
            self.tr("Arquivos da UI (*.xml *.dds *.tga *.ini);;Todos os arquivos (*)"),
        )
        sources = [Path(name) for name in names]
        if not sources:
            return
        targets = {source: self.project.import_target(source) for source in sources}
        replaced = [target for target in targets.values() if target.exists()]
        if replaced:
            listing = "\n".join(
                f"• {target.relative_to(self.project.ui_dir).as_posix()}" for target in replaced[:15]
            )
            if len(replaced) > 15:
                listing += "\n" + self.tr("… e mais {count}").format(count=len(replaced) - 15)
            answer = QMessageBox.question(
                self,
                self.tr("Substituir arquivos?"),
                self.tr(
                    "Estes arquivos já existem no projeto e serão substituídos "
                    "(a versão atual fica no histórico):\n\n{files}"
                ).format(files=listing),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        open_path = self.document.path.resolve() if self.document is not None else None
        reopen = open_path is not None and any(target.resolve() == open_path for target in replaced)
        if reopen and not self._confirm_discard_changes():
            return
        try:
            for source in sources:
                self.project.import_file(source)
        except OSError as exc:
            QMessageBox.critical(self, self.tr("Não foi possível importar"), str(exc))
        if reopen:
            self.document.raw = open_path.read_bytes()  # evita o aviso de alteração externa ao reabrir
            self.open_document(open_path)
        self.reload_all_textures()
        self.statusBar().showMessage(
            self.tr("{count} arquivo(s) importado(s), {replaced} substituído(s).").format(
                count=len(sources), replaced=len(replaced)
            ),
            6000,
        )

    def choose_project(self) -> None:
        if not self._confirm_discard_changes():
            return
        projects = list_projects()
        menu = QMenu(self)
        for root in projects:
            action = menu.addAction(root.name)
            action.triggered.connect(lambda _checked, path=root: self.open_project(path))
        if projects:
            menu.addSeparator()
        other = menu.addAction(self.tr("Procurar pasta…"))
        other.triggered.connect(self._browse_project)
        button = self.main_toolbar.widgetForAction(self.open_project_action)
        menu.exec(button.mapToGlobal(button.rect().bottomLeft()) if button else self.cursor().pos())

    def _browse_project(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, self.tr("Abrir projeto"), str(PROJECTS_ROOT if PROJECTS_ROOT.exists() else Path.home())
        )
        if not folder:
            return
        if not (Path(folder) / "project.json").is_file():
            QMessageBox.warning(self, self.tr("Não é um projeto"), self.tr("A pasta escolhida não tem project.json."))
            return
        self.open_project(Path(folder))

    def open_project(self, root: Path) -> None:
        try:
            project = Project.load(root)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, self.tr("Não foi possível abrir o projeto"), str(exc))
            return
        self.project = project
        if self.document is not None and not project.contains(self.document.path):
            self.close_document()
        QSettings("Local", "GF UI Editor").setValue("last_project", str(root))
        if self.follow_game_resolution:
            self.game_resolution = self._client_resolution()
            self._sync_resolution_actions()
            self._refresh_game_screen()
        self.test_action.setEnabled(project.game_dir is not None)
        self.export_action.setEnabled(True)
        self.import_action.setEnabled(True)
        self.publish_folder_action.setEnabled(project.game_dir is not None)
        self.project_folder_action.setEnabled(True)
        self.reload_textures_action.setEnabled(True)
        self.side_tabs.setCurrentIndex(0)
        self._refresh_files()
        self._update_title()
        self._official_diffs = {}
        self._start_official_scan()
        last = str(QSettings("Local", "GF UI Editor").value(f"last_file/{project.custom_name}", ""))
        if last and (project.ui_dir / last).is_file() and self.document is None:
            self.open_document(project.ui_dir / last)

    def _files_directory(self) -> Path | None:
        if self.project is not None:
            return self.project.ui_dir
        if self.document is not None:
            return self.document.path.parent
        return None

    def _refresh_files(self) -> None:
        self.files_tree.clear()
        directory = self._files_directory()
        if self.project is not None:
            modified = self.project.modified_files()
            files = [path for path in self.project.files() if path.suffix.lower() == ".xml"]
            # Só as da pasta principal da UI: as de subpastas (mapas, ícones) são milhares.
            textures = [
                path for path in self.project.files()
                if path.suffix.lower() in TEXTURE_SUFFIXES and len(path.parts) == 1
            ]
            self.project_label.setText(self.project.name)
            self.project_path_label.setText(
                self.tr("{count} arquivos XML · {modified} alterados").format(
                    count=sum(1 for path in self.project.files() if path.suffix.lower() == ".xml"),
                    modified=len(modified),
                )
            )
            self.project_path_label.setToolTip(str(self.project.root))
            lines = [self.tr("Editando em: {path}").format(path=self.project.ui_dir)]
            if self.project.game_dir is not None:
                lines.append(
                    self.tr("Publica em: {path}").format(
                        path=self.project.game_dir / "UICustom" / self.project.custom_name
                    )
                )
            others = (
                projects_publishing_to(self.project.custom_name, exclude=self.project.root)
                if self.project.game_dir is not None
                else []
            )
            self.shared_publish_warning.setText(
                self.tr(
                    "O projeto {projects} também envia para UICustom/{folder}: um sobrescreve o outro no jogo. "
                    "Troque em Projeto → Pasta de publicação…"
                ).format(projects=", ".join(others), folder=self.project.custom_name)
            )
            self.shared_publish_warning.setVisible(bool(others))
            self.project_paths_label.setText("\n".join(lines))
            self.project_paths_label.setToolTip(self.project_paths_label.text())
            self.project_paths_label.setVisible(True)
            self.loose_project_button.setVisible(False)

        else:
            self.project_label.setText(self.tr("Sem projeto"))
            self.shared_publish_warning.setVisible(False)
            self.project_paths_label.setVisible(directory is not None)
            if directory is not None:
                self.project_paths_label.setText(self.tr("Editando em: {path}").format(path=directory))
            self.project_path_label.setText(
                self.tr(
                    "Arquivos soltos: o jogo só vê estas mudanças se você copiar os arquivos para a pasta "
                    "da UI escolhida no launcher. Com um projeto, Enviar para o jogo faz isso por você."
                )
                if directory is not None
                else self.tr("Crie um projeto para editar fora da pasta do jogo e testar com F5.")
            )
            self.loose_project_button.setVisible(directory is not None)
            modified = set()
            files = []
            textures = []
            if directory is not None:
                files = sorted(
                    (path.relative_to(directory) for path in directory.glob("*.xml") if not is_backup_file(path.name)),
                    key=lambda item: item.as_posix().lower(),
                )
        current = os.path.normcase(str(self.document.path)) if self.document is not None else None
        bold = self.files_tree.font()
        bold.setBold(True)
        self.files_mode_bar.setVisible(bool(textures))
        if self.files_mode == "textures" and textures:
            files = textures
        groups: list[tuple[str, list[Path]]] = []
        changed = [path for path in files if path.as_posix() in modified]
        layers = set(self.project.reference_layers) if self.project is not None else set()
        blocker = QSignalBlocker(self.files_tree)  # caixas marcadas aqui não são cliques
        # Camadas marcadas no topo: fica fácil ver o que está ligado e desmarcar.
        layered = [path for path in files if path.as_posix() in layers]
        if layered:
            groups.append((self.tr("CAMADAS · {count}").format(count=len(layered)), layered))
        if changed:
            groups.append((self.tr("ALTERADOS · {count}").format(count=len(changed)), changed))
        groups.append((self.tr("TODOS · {count}").format(count=len(files)), files))
        for title, group_files in groups:
            header = QTreeWidgetItem([title, ""])
            header.setFlags(Qt.ItemFlag.ItemIsEnabled)
            header.setForeground(0, QColor(COLORS["TEXT_SECTION"]))
            header_font = self.files_tree.font()
            header_font.setPointSizeF(max(7.0, header_font.pointSizeF() - 1.5))
            header_font.setBold(True)
            header.setFont(0, header_font)
            header.setFirstColumnSpanned(True)
            self.files_tree.addTopLevelItem(header)
            for relative in group_files:
                key = relative.as_posix()
                item = QTreeWidgetItem([key, "●" if key in modified else ""])
                full_path = (directory / relative) if directory is not None else relative
                item.setData(0, Qt.ItemDataRole.UserRole, str(full_path))
                item.setIcon(
                    0,
                    icon(
                        "image" if relative.suffix.lower() in TEXTURE_SUFFIXES else "file",
                        COLORS["ACCENT_TEXT"] if key in modified else COLORS["TEXT_DISABLED"],
                        14,
                    ),
                )
                item.setForeground(1, QColor(COLORS["SELECTION_GOLD"]))
                item.setToolTip(1, self.tr("alterado") if key in modified else "")
                diff = self._official_diffs.get(key.lower()) if self.project is not None else None
                if diff is not None and diff.new_ids:
                    item.setText(1, f"+{len(diff.new_ids)}")
                    item.setForeground(1, QColor(COLORS["WARNING_TEXT"]))
                    item.setToolTip(
                        1, self.tr("A atualização do jogo trouxe {count} controle(s) que este arquivo não tem").format(count=len(diff.new_ids))
                    )
                elif diff is not None and diff.other_ids:
                    item.setText(1, ("● " if key in modified else "") + str(len(diff.other_ids)))
                    item.setForeground(1, QColor(COLORS["TEXT_DISABLED"]))
                    item.setToolTip(
                        1, self.tr("A UI oficial tem {count} controle(s) que este arquivo não tem (podem ter sido removidos de propósito)").format(count=len(diff.other_ids))
                    )
                if current is not None and os.path.normcase(str(full_path)) == current:
                    item.setFont(0, bold)
                if self.project is not None and relative.suffix.lower() == ".xml":
                    # Marcar = mostrar como camada de referência no Preview do jogo.
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(0, Qt.CheckState.Checked if key in layers else Qt.CheckState.Unchecked)
                    item.setToolTip(0, self.tr("Marque para ver esta janela junto, onde o jogo a desenha (Preview do jogo)"))
                header.addChild(item)
            header.setExpanded(True)
        del blocker
        self._filter_files(self.file_filter_edit.text())

    def _set_files_mode(self, mode: str) -> None:
        self.files_mode = mode
        for value, button in self.files_mode_buttons.items():
            button.setChecked(value == mode)
        self.file_filter_edit.setPlaceholderText(
            self.tr("Filtrar texturas…") if mode == "textures" else self.tr("Filtrar arquivos…")
        )
        self._refresh_files()

    def _filter_files(self, text: str) -> None:
        needle = text.strip().lower()
        for index in range(self.files_tree.topLevelItemCount()):
            group = self.files_tree.topLevelItem(index)
            visible = 0
            for child_index in range(group.childCount()):
                child = group.child(child_index)
                hidden = bool(needle) and needle not in child.text(0).lower()
                child.setHidden(hidden)
                visible += not hidden
            group.setHidden(visible == 0)

    def _file_layer_toggled(self, item: QTreeWidgetItem, _column: int) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data or self.project is None or not item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
            return
        # O clique na caixa também dispara itemClicked: não abre o arquivo nesse caso.
        self._layer_click = True
        QTimer.singleShot(0, lambda: setattr(self, "_layer_click", False))
        name = Path(data).resolve().relative_to(self.project.ui_dir.resolve()).as_posix()
        checked = item.checkState(0) == Qt.CheckState.Checked
        self.set_reference_layer(name, checked)
        # O mesmo arquivo aparece em "Alterados" e "Todos": mantém as duas caixas iguais.
        with QSignalBlocker(self.files_tree):
            for index in range(self.files_tree.topLevelItemCount()):
                group = self.files_tree.topLevelItem(index)
                for child_index in range(group.childCount()):
                    child = group.child(child_index)
                    if child is not item and child.data(0, Qt.ItemDataRole.UserRole) == data:
                        child.setCheckState(0, item.checkState(0))

    def _file_activated(self, item: QTreeWidgetItem, _column: int = 0) -> None:
        if self._layer_click:
            self._layer_click = False
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        path = Path(data)
        if path.suffix.lower() in TEXTURE_SUFFIXES:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
            return
        if self.document is not None and os.path.normcase(str(self.document.path)) == os.path.normcase(str(path)):
            self.side_tabs.setCurrentIndex(1)
            return
        if not self._confirm_discard_changes():
            return
        self.open_document(path)
        self.side_tabs.setCurrentIndex(1)

    def _run_with_progress(self, label: str, work):
        """Roda `work(progress)` fora da thread da interface, com barra de progresso.

        Exceções do trabalho são relançadas aqui, para os tratamentos de quem chama.
        """
        dialog = QProgressDialog(label, None, 0, 0, self)
        dialog.setWindowTitle("GF UI Editor")
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setMinimumDuration(0)
        dialog.setMinimumWidth(380)
        state = {"done": 0, "total": 0, "result": None, "error": None}

        def progress(done: int, total: int) -> None:
            state["done"], state["total"] = done, total

        def run() -> None:
            try:
                state["result"] = work(progress)
            except BaseException as exc:  # noqa: BLE001 - relançada na thread da interface
                state["error"] = exc

        worker = Thread(target=run, daemon=True)
        worker.start()
        dialog.show()
        while worker.is_alive():
            if state["total"]:
                dialog.setMaximum(state["total"])
                dialog.setValue(state["done"])
                dialog.setLabelText(f"{label}\n{state['done']} / {state['total']}")
            QApplication.processEvents()
            worker.join(0.03)
        dialog.close()
        if state["error"] is not None:
            raise state["error"]
        return state["result"]

    # ---- histórico ------------------------------------------------------------
    def _history_entries(self, path: Path) -> tuple[list[Path], Path | None]:
        """Backups (mais recente primeiro) e o original, se houver."""
        if self.project is not None and self.project.contains(path):
            original = self.project.original_path_for(path)
            return self.project.history(path), original if original.exists() else None
        backups = sorted(
            path.parent.glob(f"{path.stem}.before-gf-ui-editor-*{path.suffix}"), key=lambda item: item.name, reverse=True
        )
        return backups, None

    @staticmethod
    def _backup_label(backup: Path) -> str:
        match = re.search(r"(\d{8})-(\d{6})", backup.name)
        if not match:
            return backup.name
        stamp = datetime.strptime(match[1] + match[2], "%Y%m%d%H%M%S")
        today = datetime.now().date()
        if stamp.date() == today:
            day = QCoreApplication.translate("EditorWindow", "hoje")
        elif (today - stamp.date()).days == 1:
            day = QCoreApplication.translate("EditorWindow", "ontem")
        else:
            day = stamp.strftime("%d/%m")
        return f"{day} {stamp:%H:%M:%S}"

    def _files_context_menu(self, position) -> None:
        item = self.files_tree.itemAt(position)
        data = item.data(0, Qt.ItemDataRole.UserRole) if item is not None else None
        if not data:
            return
        path = Path(data)
        backups, original = self._history_entries(path)
        menu = QMenu(self)
        open_action = menu.addAction(self.tr("Abrir"))
        open_action.triggered.connect(lambda: self._file_activated(item))
        if self.project is not None and self.project.contains(path):
            rename = menu.addAction(self.tr("Renomear…"))
            rename.triggered.connect(lambda: self.rename_project_file(path))
            delete = menu.addAction(self.tr("Apagar…"))
            delete.triggered.connect(lambda: self.delete_project_file(path))
            menu.addSeparator()
        history_menu = menu.addMenu(self.tr("Restaurar versão anterior"))
        history_menu.setEnabled(bool(backups))
        for backup in backups:
            action = history_menu.addAction(self._backup_label(backup))
            action.triggered.connect(lambda _checked=False, source=backup: self.restore_file(path, source))
        revert = menu.addAction(self.tr("Desfazer todas as alterações"))
        revert.setEnabled(original is not None)
        revert.setToolTip(self.tr("Volta o arquivo para como era quando o projeto foi criado."))
        if original is not None:
            revert.triggered.connect(lambda: self.restore_file(path, original))
        menu.addSeparator()
        folder = backups[0].parent if backups else (original.parent if original is not None else None)
        reveal = menu.addAction(self.tr("Abrir pasta do histórico"))
        reveal.setEnabled(folder is not None)
        if folder is not None:
            reveal.triggered.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))))
        menu.exec(self.files_tree.viewport().mapToGlobal(position))

    def _is_open(self, path: Path) -> bool:
        return self.document is not None and os.path.normcase(str(self.document.path.resolve())) == os.path.normcase(str(path.resolve()))

    def _xml_using_texture(self, name: str) -> list[Path]:
        """XMLs do projeto com BGmap apontando para a textura `name`."""
        assert self.project is not None
        pattern = re.compile(rb'BGmap\s*=\s*"' + re.escape(name.encode("latin-1", "ignore")) + rb'"', re.IGNORECASE)
        found = []
        for relative in self.project.files():
            if relative.suffix.lower() != ".xml":
                continue
            path = self.project.ui_dir / relative
            try:
                if pattern.search(path.read_bytes()):
                    found.append(path)
            except OSError:
                continue
        return found

    def rename_project_file(self, path: Path) -> None:
        if self.project is None:
            return
        name, accepted = QInputDialog.getText(self, self.tr("Renomear"), self.tr("Novo nome:"), text=path.name)
        name = name.strip()
        if not accepted or not name or name == path.name:
            return
        if any(char in name for char in '\\/:*?"<>|'):
            QMessageBox.warning(self, self.tr("Renomear"), self.tr("O nome não pode ter \\ / : * ? \" < > |."))
            return
        if not Path(name).suffix:
            name += path.suffix
        target = path.with_name(name)
        replacing = target.exists() and os.path.normcase(str(target)) != os.path.normcase(str(path))
        if replacing:
            answer = QMessageBox.question(
                self,
                self.tr("Substituir arquivo?"),
                self.tr("Já existe {name} no projeto. Substituir? A versão atual vai para o histórico.").format(name=name),
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        reopen = self._is_open(path) or (replacing and self._is_open(target))
        if reopen and not self._confirm_discard_changes():
            return
        is_texture = path.suffix.lower() in TEXTURE_SUFFIXES
        users = self._xml_using_texture(path.name) if is_texture else []
        if reopen:
            self.close_document()
        try:
            new_path, _backup = self.project.rename_file(path, name)
        except OSError as exc:
            QMessageBox.critical(self, self.tr("Renomear"), str(exc))
            return
        if users:
            answer = QMessageBox.question(
                self,
                self.tr("Atualizar XMLs?"),
                self.tr("{count} XML(s) do projeto usam {old}. Trocar para {new} neles também?").format(
                    count=len(users), old=path.name, new=new_path.name
                ),
            )
            if answer == QMessageBox.StandardButton.Yes:
                self._retarget_texture(users, path.name, new_path.name)
        self.project.files(refresh=True)
        self._refresh_files()
        if reopen and new_path.suffix.lower() == ".xml":
            self.open_document(new_path)
        self.statusBar().showMessage(self.tr("{old} agora se chama {new}.").format(old=path.name, new=new_path.name), 8000)

    def _retarget_texture(self, paths: list[Path], old: str, new: str) -> None:
        """Troca BGmap="old" por BGmap="new" mexendo só nesse atributo, com backup de cada XML."""
        assert self.project is not None
        pattern = re.compile(r'(BGmap\s*=\s*")' + re.escape(old) + r'(")', re.IGNORECASE)
        for path in paths:
            try:
                raw = path.read_bytes()
                text = raw.decode("big5")
            except (OSError, UnicodeDecodeError):
                continue
            changed = pattern.sub(lambda match: match.group(1) + new + match.group(2), text)
            if changed == text:
                continue
            self.project.remember_original(path)
            shutil.copy2(path, self.project.history_path_for(path))
            path.write_bytes(changed.encode("big5"))

    def delete_project_file(self, path: Path) -> None:
        if self.project is None:
            return
        details = self.tr("Uma cópia fica no histórico do projeto.")
        game_dir = self.project.game_dir
        if path.suffix.lower() == ".xml" and game_dir is not None:
            relative = path.resolve().relative_to(self.project.ui_dir.resolve()).as_posix()
            if official_text_for(game_dir, relative) is not None:
                details = self.tr(
                    "Este arquivo existe na UI oficial: sem ele, o jogo pode usar o da UI padrão ou acusar erro. "
                    "Uma cópia fica no histórico do projeto."
                )
        elif path.suffix.lower() in TEXTURE_SUFFIXES:
            users = self._xml_using_texture(path.name)
            if users:
                details = self.tr(
                    "{count} XML(s) do projeto ainda usam esta textura e ficariam sem imagem. "
                    "Uma cópia fica no histórico do projeto."
                ).format(count=len(users))
        answer = QMessageBox.question(self, self.tr("Apagar {name}?").format(name=path.name), details)
        if answer != QMessageBox.StandardButton.Yes:
            return
        if self._is_open(path):
            if not self._confirm_discard_changes():
                return
            self.close_document()
        try:
            self.project.delete_file(path)
        except OSError as exc:
            QMessageBox.critical(self, self.tr("Apagar"), str(exc))
            return
        self.project.files(refresh=True)
        self._refresh_files()
        self.statusBar().showMessage(self.tr("{name} apagado. A cópia está no histórico do projeto.").format(name=path.name), 8000)

    def restore_file(self, path: Path, source: Path) -> None:
        is_open = self.document is not None and os.path.normcase(str(self.document.path)) == os.path.normcase(str(path))
        if is_open and self.document.is_dirty:
            answer = QMessageBox.question(
                self,
                self.tr("Descartar alterações?"),
                self.tr("{name} tem alterações não salvas que serão perdidas ao restaurar. Continuar?").format(name=path.name),
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            current = path.read_bytes().decode("big5", errors="replace").splitlines()
            restored = source.read_bytes().decode("big5", errors="replace").splitlines()
        except OSError as exc:
            QMessageBox.critical(self, self.tr("Falha ao restaurar"), str(exc))
            return
        diff = "\n".join(
            difflib.unified_diff(current, restored, fromfile=self.tr("{name} (atual)").format(name=path.name), tofile=self.tr("versão restaurada"), lineterm="")
        )
        if not diff:
            self.statusBar().showMessage(self.tr("Essa versão é igual ao arquivo atual."), 5000)
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr("Restaurar {name}").format(name=path.name))
        dialog.resize(1000, 650)
        explanation = QLabel(self.tr("Estas linhas vão mudar. O estado atual fica guardado no histórico, então dá para voltar."))
        explanation.setWordWrap(True)
        view = QPlainTextEdit()
        view.setReadOnly(True)
        view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        view.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        view.setPlainText(diff)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(self.tr("Restaurar"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(self.tr("Cancelar"))
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout = QVBoxLayout(dialog)
        layout.addWidget(explanation)
        layout.addWidget(view)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            if self.project is not None and self.project.contains(path):
                self.project.restore(path, source)
            else:
                backup = path.with_name(
                    f"{path.stem}.before-gf-ui-editor-{datetime.now():%Y%m%d-%H%M%S}{path.suffix}"
                )
                shutil.copy2(path, backup)
                shutil.copy2(source, path)
        except OSError as exc:
            QMessageBox.critical(self, self.tr("Falha ao restaurar"), str(exc))
            return
        if is_open:
            self.document.raw = path.read_bytes()  # evita o aviso de alteração externa ao reabrir
            self.open_document(path)
        self._refresh_files()
        self.statusBar().showMessage(self.tr("{name} restaurado.").format(name=path.name), 6000)

    def _save_before_project_action(self) -> bool:
        if self.document is None or not self.document.is_dirty:
            return True
        answer = QMessageBox.question(
            self,
            self.tr("Salvar antes?"),
            self.tr("{name} tem alterações não salvas. Salvar antes de continuar?").format(name=self.document.path.name),
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Save:
            self.save_document()
            return not self.document.is_dirty
        return True

    def test_in_game(self) -> None:
        if self.project is None or self.project.game_dir is None:
            return
        if not self._save_before_project_action():
            return
        pending = sorted(diff.relative for diff in self._official_diffs.values() if diff.new_ids)
        if pending:
            answer = QMessageBox.question(
                self,
                self.tr("Controles novos do jogo"),
                self.tr(
                    "Estes arquivos não têm controles que a atualização do jogo trouxe, e o jogo pode mostrar "
                    "\"Child control can not found\":\n\n{files}\n\nEnviar mesmo assim?"
                ).format(files=", ".join(pending[:8]) + ("…" if len(pending) > 8 else "")),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        settings = QSettings("Local", "GF UI Editor")
        if settings.value("publish_confirmed", "false") != "true":
            answer = QMessageBox.question(
                self,
                self.tr("Enviar para o jogo"),
                self.tr(
                    "Isto vai:\n\n"
                    "• atualizar {custom}\n"
                    "• copiar os arquivos do projeto para a pasta UI do jogo\n"
                    "• selecionar \"{name}\" no Launcher.ini, para o launcher não reaplicar outra UI ao clicar Jogar\n\n"
                    "Outras UIs em UICustom não são alteradas. Continuar?"
                ).format(custom=self.project.game_dir / "UICustom" / self.project.custom_name, name=self.project.custom_name),
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            settings.setValue("publish_confirmed", "true")
        try:
            project = self.project
            result = self._run_with_progress(
                self.tr("Publicando no jogo…"), lambda progress: project.publish(progress=progress)
            )
        except OSError as exc:
            QMessageBox.critical(
                self,
                self.tr("Falha ao publicar"),
                self.tr("Não foi possível copiar os arquivos. Feche o jogo se ele estiver aberto e tente de novo.\n\n{error}").format(error=exc),
            )
            return
        self._update_status_chips()
        self.statusBar().showMessage(
            self.tr("Publicado: {count} arquivo(s) atualizados na pasta UI. Abra o jogo pelo launcher ou direto.").format(
                count=result.copied_to_ui
            ),
            12000,
        )
        wanted = f"custom:{project.custom_name}"
        if result.launcher_running and result.previous_selection != wanted:
            QMessageBox.information(
                self,
                self.tr("Selecione a UI no launcher"),
                self.tr(
                    "Os arquivos foram publicados, mas o launcher está aberto com outra UI selecionada.\n\n"
                    "Antes de clicar em Jogar, escolha \"{name}\" na lista de UIs do launcher "
                    "(ou feche e abra o launcher). Senão ele reaplica a UI anterior por cima do seu teste."
                ).format(name=project.custom_name),
            )

    def choose_publish_folder(self) -> None:
        """Escolhe em qual pasta de UICustom o F5 publica este projeto."""
        if self.project is None or self.project.game_dir is None:
            return
        own = self.tr("Pasta própria do projeto ({name})").format(name=safe_name(self.project.name))
        custom_root = self.project.game_dir / "UICustom"
        folders = sorted(item.name for item in custom_root.iterdir() if item.is_dir()) if custom_root.is_dir() else []
        options = [own] + folders
        current = options.index(self.project.publish_folder) if self.project.publish_folder in options else 0
        choice, accepted = QInputDialog.getItem(
            self,
            self.tr("Pasta de publicação"),
            self.tr(
                "O F5 copia os arquivos do projeto para esta pasta de UICustom.\n"
                "Numa pasta que já existe, ele só adiciona e atualiza arquivos; nada é apagado."
            ),
            options,
            current,
            False,
        )
        if not accepted:
            return
        self.project.publish_folder = "" if choice == own else choice
        self.project.save_manifest()
        self._refresh_files()
        self._update_title()

    def export_project_zip(self) -> None:
        if self.project is None:
            return
        if not self._save_before_project_action():
            return
        default = Path.home() / "Documents" / f"{self.project.custom_name}.zip"
        filename, _ = QFileDialog.getSaveFileName(
            self, self.tr("Exportar UI"), str(default), self.tr("UI do launcher (*.zip)")
        )
        if not filename:
            return
        try:
            project = self.project
            path = self._run_with_progress(
                self.tr("Compactando a UI…"), lambda progress: project.export_zip(Path(filename), progress=progress)
            )
        except OSError as exc:
            QMessageBox.critical(self, self.tr("Falha ao exportar"), str(exc))
            return
        self.statusBar().showMessage(
            self.tr("Exportado para {path}. No launcher: Adicionar UI Customizada.").format(path=path), 12000
        )

    def _confirm_diff_preview(self) -> bool:
        assert self.document is not None
        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr("Confirmar alterações no XML"))
        dialog.resize(1000, 650)
        explanation = QLabel(
            self.tr("Confira as linhas que serão alteradas. O backup exato será criado antes da gravação.")
        )
        diff_view = QPlainTextEdit()
        diff_view.setReadOnly(True)
        diff_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        diff_view.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        diff_view.setPlainText(self.document.unified_diff())
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(self.tr("Salvar"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(self.tr("Cancelar"))
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout = QVBoxLayout(dialog)
        layout.addWidget(explanation)
        layout.addWidget(diff_view)
        layout.addWidget(buttons)
        return dialog.exec() == QDialog.DialogCode.Accepted

    def _update_title(self) -> None:
        self._update_breadcrumb()
        self._update_status_chips()
        self._update_center_page()
        if self.document is None:
            self.setWindowTitle(f"GF UI Editor [{self.project.name}]" if self.project is not None else "GF UI Editor")
            return
        marker = " *" if self.document.is_dirty else ""
        project = f" [{self.project.name}]" if self.project is not None else ""
        self.setWindowTitle(
            f"GF UI Editor{project} — {self.document.path.name}{marker} — {self.document.path.parent}"
        )

    def _confirm_discard_changes(self) -> bool:
        if self.document is None or not self.document.is_dirty:
            return True
        result = QMessageBox.question(
            self,
            self.tr("Descartar alterações?"),
            self.tr("Existem alterações não salvas. Deseja descartá-las?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return result == QMessageBox.StandardButton.Yes

    def _sync_language_menu(self) -> None:
        for action in self.language_button.menu().actions():
            action.setChecked(action.data() == self.language)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if getattr(self, "_closing_for_language", False) or self._confirm_discard_changes():
            event.accept()
        else:
            event.ignore()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Editor visual dos XMLs de UI do Grand Fantasia")
    parser.add_argument("xml", nargs="?", type=Path, help="XML que será aberto ao iniciar")
    parser.add_argument("--lang", choices=LANGUAGES, help="Idioma da interface nesta execução")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    application = QApplication(sys.argv[:1])
    application.setApplicationName("GF UI Editor")
    application.setOrganizationName("Local")
    application.setWindowIcon(QIcon(str(APP_ICON_PATH)))
    language = args.lang or QSettings("Local", "GF UI Editor").value("language", "pt_BR")
    if language not in LANGUAGES:
        language = "pt_BR"
    switch_language(application, language)
    window = EditorWindow(args.xml, language=language, restore_last_project=True)
    window.show()
    application._main_window = window
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
