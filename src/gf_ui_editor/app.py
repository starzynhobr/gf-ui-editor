from __future__ import annotations

import argparse
from datetime import datetime
import difflib
from html import escape
import os
from pathlib import Path
from queue import Empty, SimpleQueue
import re
import shutil
import sys
from threading import Thread
import time

from PySide6.QtCore import QCoreApplication, QFileSystemWatcher, QRectF, QSize, QSettings, QSignalBlocker, QTimer, Qt, QUrl, Signal
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
from .editor_widgets import EditorView, ElementItem, GameScreenItem
from .game_layout import (
    client_resolution,
    load_user_positions,
    root_screen_position,
    is_centered,
    rule_for,
    saved_position_applies,
    saved_section_for,
)
from .i18n import LANGUAGE_NAMES, LANGUAGES, document_error_text, kind_label, switch_language
from .icons import MONO_FONT, UI_FONT, icon, load_fonts
from .interaction import install_pointer_cursors
from . import backgrounds
from . import release_notes, updater
from .update_dialog import SKIP, UPDATE, WhatsNewDialog
from .project import PROJECTS_ROOT, Project, custom_ui_sources, is_backup_file, list_projects, safe_name
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
)


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

    def __init__(self, game_dir: Path | None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Novo projeto de UI"))
        self.setMinimumWidth(460)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(self.tr("Ex.: UI-Hero ajustada"))
        self.source_combo = QComboBox()
        if game_dir is not None:
            for label, path in custom_ui_sources(game_dir):
                text = self.tr("UI em uso no jogo (pasta UI)") if label == "UI" else label
                self.source_combo.addItem(text, str(path))
        self.source_combo.addItem(self.tr("Outra pasta…"), "")
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
        form.addRow(self.tr("Começar a partir de"), self.source_combo)
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
        layout.addWidget(explanation)
        layout.addWidget(buttons)
        self.source_dir: Path | None = None
        self.publish_folder = ""
        self.source_combo.currentIndexChanged.connect(self._suggest_name)

    def _suggest_name(self, _index: int = 0) -> None:
        text = self.source_combo.currentText()
        if text.startswith("UICustom/") and not self.name_edit.text().strip():
            self.name_edit.setText(text.split("/", 1)[1])

    def _accept(self) -> None:
        if not self.name_edit.text().strip():
            self.name_edit.setFocus()
            return
        data = self.source_combo.currentData()
        if not data:
            folder = QFileDialog.getExistingDirectory(self, self.tr("Pasta com os arquivos da UI"))
            if not folder:
                return
            data = folder
        self.source_dir = Path(data)
        text = self.source_combo.currentText()
        # Projeto vindo de uma UI de UICustom publica de volta nela (o launcher já a conhece).
        self.publish_folder = text.split("/", 1)[1] if text.startswith("UICustom/") else ""
        self.accept()


class PropertyPanel(QWidget):
    geometry_edited = Signal(tuple)
    root_mode_changed = Signal(str)
    atlas_requested = Signal()

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
        self.root_mode_combo = QComboBox()
        self.root_mode_combo.addItem(self.tr("Posição no jogo: automática"), "auto")
        self.root_mode_combo.addItem(self.tr("Posição no jogo: X e Y do XML"), "xml")
        self.root_mode_combo.addItem(self.tr("Posição no jogo: centralizada"), "center")
        self.root_mode_combo.setToolTip(
            self.tr("Como o preview posiciona esta janela na tela. Use se o jogo do seu servidor se comportar diferente do automático.")
        )
        self.root_mode_combo.setVisible(False)
        self.root_mode_combo.currentIndexChanged.connect(
            lambda _index: None if self._loading else self.root_mode_changed.emit(self.root_mode_combo.currentData())
        )
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

        self.atlas_button.setIcon(icon("image"))
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
        self.details_container = QWidget()
        details_layout = QVBoxLayout(self.details_container)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(12)
        details_layout.addWidget(
            self._card(self.tr("POSIÇÃO E TAMANHO"), geometry_grid, self.screen_position_label, self.root_mode_combo, self.anchor_hint)
        )
        details_layout.addWidget(self._card(self.tr("TEXTURA"), texture_form, self.atlas_button))
        details_layout.addWidget(self._card(self.tr("IDENTIFICAÇÃO"), details_form))
        details_layout.addWidget(self._card(self.tr("APARÊNCIA"), appearance_form, explanation))
        details_layout.addWidget(self._card(self.tr("NO EDITOR"), None, self.actions_row))
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

    def set_root_mode(self, mode: str | None) -> None:
        """Mostra o seletor só para a janela raiz (`mode` None esconde)."""
        self.root_mode_combo.setVisible(mode is not None)
        if mode is not None:
            with QSignalBlocker(self.root_mode_combo):
                self.root_mode_combo.setCurrentIndex(max(0, self.root_mode_combo.findData(mode)))

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
        self, lock_action: QAction, hide_action: QAction, isolate_action: QAction
    ) -> None:
        for button, action in zip(
            (self.lock_button, self.hide_button, self.isolate_button),
            (lock_action, hide_action, isolate_action),
            strict=True,
        ):
            button.setDefaultAction(action)

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
        elements_page = QWidget()
        elements_page.setObjectName("treePanel")
        tree_layout = QVBoxLayout(elements_page)
        tree_layout.setContentsMargins(10, 10, 10, 10)
        tree_layout.setSpacing(8)
        tree_layout.addWidget(self.search_edit)
        tree_layout.addWidget(self.tree)

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
        self.properties.root_mode_changed.connect(self.set_root_mode)
        self.properties.atlas_requested.connect(self.open_selected_atlas)
        properties_scroll = QScrollArea()
        properties_scroll.setObjectName("propertiesScroll")
        properties_scroll.setFrameShape(QFrame.Shape.NoFrame)
        properties_scroll.setWidgetResizable(True)
        properties_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        properties_scroll.setWidget(self.properties)

        self.empty_page = self._build_empty_page()
        self.center_stack = QStackedWidget()
        self.center_stack.addWidget(self.empty_page)
        self.center_stack.addWidget(self.view)
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
            self.lock_action, self.hide_action, self.isolate_action
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
        self.new_project_action.triggered.connect(self.new_project)
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
        self.textures_action = QAction(self.tr("Mostrar texturas"), self)
        self.textures_action.setCheckable(True)
        self.textures_action.setChecked(True)
        self.textures_action.setShortcut("T")
        self.textures_action.toggled.connect(self.set_textures_visible)
        self.atlas_action = QAction(self.tr("Abrir atlas DDS…"), self)
        self.atlas_action.setEnabled(False)
        self.atlas_action.triggered.connect(self.open_selected_atlas)
        self.reload_textures_action = QAction(self.tr("Recarregar texturas"), self)
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

    def _create_menus_and_toolbar(self) -> None:
        file_menu = self.menuBar().addMenu(self.tr("Arquivo"))
        file_menu.addAction(self.new_project_action)
        file_menu.addAction(self.open_project_action)
        file_menu.addSeparator()
        file_menu.addAction(self.open_action)
        file_menu.addAction(self.save_action)
        project_menu = self.menuBar().addMenu(self.tr("Projeto"))
        project_menu.addAction(self.test_action)
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
        view_menu = self.menuBar().addMenu(self.tr("Visualização"))
        view_menu.addAction(self.fit_action)
        view_menu.addAction(self.labels_action)
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
            QFrame#floatingBar {
                background: ${CHIP_BG};
                border: 1px solid ${BORDER_INPUT};
                border-radius: 10px;
            }
            QFrame#floatingBar QToolButton#pill { border-radius: 7px; padding: 4px 9px; color: ${TEXT_PRIMARY}; }
            QFrame#floatingBar QToolButton#pill:checked { background: ${ACCENT_SOFT_BG}; color: ${ACCENT_TEXT}; }
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
        if filename:
            self.open_document(Path(filename))

    def open_document(self, path: Path) -> None:
        try:
            document = UIDocument.load(path)
        except DocumentError as exc:
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

    def _rebuild_scene(self, *, load_textures: bool = True) -> None:
        assert self.document is not None and self.texture_cache is not None
        self.view.set_interaction_priority(None)
        self.scene.clear()
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
            item.set_texture_visible(self.textures_action.isChecked())
            item.set_preview_mode(self.preview_action.isChecked())
            self.scene.addItem(item)
            self.items[element.index] = item
        self.game_screen_item = None
        self._refresh_game_screen()

    def _refresh_game_screen(self) -> None:
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
            saved = None
            if section and game_dir is not None and self.saved_positions_action.isChecked():
                saved = load_user_positions(game_dir / "User.ini").get(section)
            screen_x, screen_y = root_screen_position(
                name, self.game_resolution, root.geometry, saved, mode=mode, game_dir=game_dir
            )
            self.game_screen_item.setPos(root.x - screen_x, root.y - screen_y)
            caption += " · " + self.tr("janela no jogo em ({x}, {y})").format(x=screen_x, y=screen_y)
            if mode != "auto":
                caption += " · " + self.tr("posição escolhida por você")
            elif rule_for(name) is None and saved_position_applies(self.game_resolution, root.geometry, saved):
                caption += " · " + self.tr("posição salva no User.ini [{section}]").format(section=section)
            elif rule_for(name) is not None:
                caption += " · " + self.tr("posição definida pelo cliente")
            elif is_centered(name, game_dir):
                caption += " · " + self.tr("centralizada pelo jogo")
        else:
            self.game_screen_item.setPos(0, 0)
        self.game_screen_item.set_caption(caption)
        self._keep_screen_in_place(before, before_in_view)
        self._sync_window_frame()
        self._refresh_screen_position()

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
        item = self.items[0]
        item.apply_element(root)
        offset = self._screen_offset()
        others = self.document.elements[1:]
        if offset is None or not others or not self._root_position_is_set_by_game():
            return
        bounds = QRectF()
        for element in others:
            bounds = bounds.united(QRectF(element.x, element.y, max(1, element.width), max(1, element.height)))
        item.set_content_frame(bounds, offset)

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
        self.properties.set_screen_position((element.x + offset[0], element.y + offset[1]))

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
        return self.document.path.parent.parent

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
        if self.document is None or index != 0:
            return None
        if self._root_mode() != "auto":
            return None
        if rule_for(self.document.path.name) is not None:
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
        self.properties.set_root_mode(self._root_mode() if index == 0 else None)
        self.properties.set_anchor_hint(self._anchor_hint_for(index))
        self.properties.set_enabled(index not in self.locked_indexes)
        if self.isolated_index is not None and self.isolated_index != index:
            previous_isolated_index = self.isolated_index
            self.isolated_index = index
            self._apply_visibility_state()
            self._refresh_tree_state(previous_isolated_index)
            self._refresh_tree_state(index)
        self._update_element_actions()
        suffix = self.tr(" · {count} selecionados").format(count=selection_count) if selection_count > 1 else ""
        self.statusBar().showMessage(
            self.tr("WindowID {id} · índice {index}").format(
                id=self.document.elements[index].window_id, index=index
            ) + suffix
        )

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
            geometry = (
                element.x - (geometry[0] - frame[0]), element.y - (geometry[1] - frame[1]), geometry[2], geometry[3]
            )
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
        if set(changes) == {0} and self._root_position_is_set_by_game():
            dx, dy = -dx, -dy
        root = self.document.elements[0].geometry
        return {**changes, 0: (root, (x + dx, y + dy, new[2], new[3]))}

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
        if self.document is None or self.texture_cache is None:
            return
        if self._textures_pending:
            self.statusBar().showMessage(self.tr("Aguarde o carregamento das texturas."), 4000)
            return
        self.texture_cache.invalidate()
        for index in self.items:
            self._refresh_element_texture(index)
        self._reload_open_atlas()
        self.statusBar().showMessage(self.tr("Texturas recarregadas do disco."), 4000)

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

    def toggle_selected_lock(self) -> None:
        if self.selected_index is None:
            return
        index = self.selected_index
        if index in self.locked_indexes:
            self.locked_indexes.remove(index)
        else:
            self.locked_indexes.add(index)
        self.items[index].set_locked(index in self.locked_indexes)
        self.properties.set_enabled(index not in self.locked_indexes)
        self._refresh_tree_state(index)
        self._update_element_actions()

    def toggle_selected_hidden(self) -> None:
        if self.selected_index is None:
            return
        index = self.selected_index
        if index in self.hidden_indexes:
            self.hidden_indexes.remove(index)
        else:
            self.hidden_indexes.add(index)
        self._apply_visibility_state()
        self._refresh_tree_state(index)
        self._update_element_actions()

    def toggle_isolation(self) -> None:
        if self.selected_index is None:
            return
        previous = self.isolated_index
        self.isolated_index = None if previous is not None else self.selected_index
        self._apply_visibility_state()
        if previous is not None:
            self._refresh_tree_state(previous)
        if self.selected_index is not None:
            self._refresh_tree_state(self.selected_index)
        self._update_element_actions()

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
        tree_item.setText(3, ", ".join(states))

    def _update_element_actions(self) -> None:
        enabled = self.selected_index is not None
        self.lock_action.setEnabled(enabled)
        self.hide_action.setEnabled(enabled)
        self.isolate_action.setEnabled(enabled)
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
            ("folder-plus", self.tr("Novo projeto"), self.tr("A partir da UI em uso, de uma UI do UICustom ou de outra pasta."), self.new_project, True),
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

    def _refresh_recent_projects(self) -> None:
        while self.recent_layout.count():
            widget = self.recent_layout.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        projects = sorted(
            list_projects(), key=lambda root: (root / "project.json").stat().st_mtime, reverse=True
        )[:5]
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
            button.clicked.connect(lambda _checked=False, path=root: self.open_project(path))
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
            self.center_stack.setCurrentWidget(self.view)

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
        game_dir = DEFAULT_UI_DIRECTORY.parent
        return game_dir if game_dir.is_dir() else None

    def new_project(self) -> None:
        if not self._confirm_discard_changes():
            return
        game_dir = self._game_dir()
        if game_dir is None:
            folder = QFileDialog.getExistingDirectory(self, self.tr("Pasta do Grand Fantasia Violet"))
            if not folder:
                return
            game_dir = Path(folder)
        dialog = NewProjectDialog(game_dir, self)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.source_dir is None:
            return
        try:
            name, source = dialog.name_edit.text().strip(), dialog.source_dir
            include_assets = dialog.assets_check.isChecked()
            publish_folder = dialog.publish_folder
            project = self._run_with_progress(
                self.tr("Copiando arquivos da UI para o projeto…"),
                lambda progress: Project.create(
                    name, source, game_dir, progress=progress, include_assets=include_assets,
                    publish_folder=publish_folder,
                ),
            )
        except FileExistsError as exc:
            QMessageBox.warning(
                self, self.tr("Projeto já existe"), self.tr("Já existe um projeto em {path}.").format(path=exc.args[0])
            )
            return
        except OSError as exc:
            QMessageBox.critical(self, self.tr("Não foi possível criar o projeto"), str(exc))
            return
        self.open_project(project.root)
        self.statusBar().showMessage(
            self.tr("Projeto criado com {count} arquivos.").format(count=len(project.base_hashes)), 8000
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
        QSettings("Local", "GF UI Editor").setValue("last_project", str(root))
        if self.follow_game_resolution:
            self.game_resolution = self._client_resolution()
            self._sync_resolution_actions()
            self._refresh_game_screen()
        self.test_action.setEnabled(project.game_dir is not None)
        self.export_action.setEnabled(True)
        self.publish_folder_action.setEnabled(project.game_dir is not None)
        self.project_folder_action.setEnabled(True)
        self.side_tabs.setCurrentIndex(0)
        self._refresh_files()
        self._update_title()
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
            self.project_paths_label.setText("\n".join(lines))
            self.project_paths_label.setToolTip(self.project_paths_label.text())
            self.project_paths_label.setVisible(True)

        else:
            self.project_label.setText(self.tr("Sem projeto"))
            self.project_paths_label.setVisible(directory is not None)
            if directory is not None:
                self.project_paths_label.setText(self.tr("Editando em: {path}").format(path=directory))
            self.project_path_label.setText(
                self.tr("Crie um projeto para editar fora da pasta do jogo e testar com F5.")
            )
            modified = set()
            files = []
            if directory is not None:
                files = sorted(
                    (path.relative_to(directory) for path in directory.glob("*.xml") if not is_backup_file(path.name)),
                    key=lambda item: item.as_posix().lower(),
                )
        current = os.path.normcase(str(self.document.path)) if self.document is not None else None
        bold = self.files_tree.font()
        bold.setBold(True)
        groups: list[tuple[str, list[Path]]] = []
        changed = [path for path in files if path.as_posix() in modified]
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
                item.setIcon(0, icon("file", COLORS["ACCENT_TEXT"] if key in modified else COLORS["TEXT_DISABLED"], 14))
                item.setForeground(1, QColor(COLORS["SELECTION_GOLD"]))
                item.setToolTip(1, self.tr("alterado") if key in modified else "")
                if current is not None and os.path.normcase(str(full_path)) == current:
                    item.setFont(0, bold)
                header.addChild(item)
            header.setExpanded(True)
        self._filter_files(self.file_filter_edit.text())

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

    def _file_activated(self, item: QTreeWidgetItem, _column: int = 0) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        path = Path(data)
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
