from __future__ import annotations

import argparse
from pathlib import Path
import sys

from PySide6.QtCore import QFileSystemWatcher, QSignalBlocker, QTimer, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QFontDatabase,
    QKeySequence,
    QUndoCommand,
    QUndoStack,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGraphicsScene,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStyle,
    QTreeWidget,
    QTreeWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .editor_widgets import EditorView, ElementItem
from .atlas_dialog import AtlasDialog
from .texture_cache import TextureCache
from .theme import COLORS, stylesheet
from .xml_document import (
    DocumentError,
    ExternalModificationError,
    UIDocument,
    UIElement,
    UVRect,
)


DEFAULT_UI_DIRECTORY = Path(r"C:\Violet Games\Grand Fantasia Violet\UI")


class PropertyPanel(QWidget):
    geometry_edited = Signal(tuple)
    atlas_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("propertiesPanel")
        self._loading = False
        self.selection_title = QLabel("Nenhum elemento selecionado")
        self.selection_title.setObjectName("panelTitle")
        self.selection_subtitle = QLabel(
            "Selecione um item no canvas ou na lista para editar sua geometria."
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
        self.texture_value = QLineEdit()
        self.texture_value.setReadOnly(True)
        self.atlas_button = QPushButton("Abrir atlas…")
        self.atlas_button.setEnabled(False)
        self.atlas_button.clicked.connect(self.atlas_requested.emit)
        texture_row = QWidget()
        texture_layout = QHBoxLayout(texture_row)
        texture_layout.setContentsMargins(0, 0, 0, 0)
        texture_layout.setSpacing(6)
        texture_layout.addWidget(self.texture_value, 1)
        texture_layout.addWidget(self.atlas_button)
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
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
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
        self._add_field(details_form, "Tipo", self.kind_value)
        self._add_field(details_form, "ParentNode", self.parent_value)
        self._add_field(details_form, "CtrlType", self.ctrl_value)
        self._add_field(geometry_form, "Posição X", self.x_spin)
        self._add_field(geometry_form, "Posição Y", self.y_spin)
        self._add_field(geometry_form, "Largura", self.width_spin)
        self._add_field(geometry_form, "Altura", self.height_spin)
        self._add_field(appearance_form, "Visível no XML", self.visible_value)
        self._add_field(appearance_form, "Texto", self.text_value)
        self._add_field(appearance_form, "Textura", texture_row)
        self._add_field(appearance_form, "Recorte DDS", self.uv_value)
        self._add_field(appearance_form, "Fonte", self.font_value)
        self.x_spin.setToolTip("WindowLeft no XML")
        self.y_spin.setToolTip("WindowTop no XML")
        self.width_spin.setToolTip("WindowHeight no XML")
        self.height_spin.setToolTip("WindowWidth no XML")

        explanation = QLabel(
            "O formato do jogo usa WindowHeight como largura visual e WindowWidth como altura visual."
        )
        explanation.setWordWrap(True)
        explanation.setStyleSheet(f"color: {COLORS['TEXT_MUTED']}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        layout.addWidget(self.selection_title)
        layout.addWidget(self.selection_subtitle)
        layout.addWidget(self.actions_row)
        self.details_container = QWidget()
        details_layout = QVBoxLayout(self.details_container)
        details_layout.setContentsMargins(0, 12, 0, 0)
        details_layout.setSpacing(8)
        for title, form in (
            ("IDENTIFICAÇÃO", details_form),
            ("GEOMETRIA", geometry_form),
            ("APARÊNCIA", appearance_form),
        ):
            section = QLabel(title)
            section.setObjectName("sectionLabel")
            details_layout.addWidget(section)
            details_layout.addLayout(form)
            details_layout.addSpacing(10)
        details_layout.addWidget(explanation)
        layout.addWidget(self.details_container)
        layout.addStretch(1)
        self.details_container.setVisible(False)
        self.set_enabled(False)

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
                self.actions_row.setVisible(False)
                self.details_container.setVisible(False)
                self.selection_title.setText("Nenhum elemento selecionado")
                self.selection_subtitle.setText(
                    "Selecione um item no canvas ou na lista para editar sua geometria."
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
            self.selection_title.setText(f"WindowID {element.window_id}")
            self.actions_row.setVisible(True)
            self.details_container.setVisible(True)
            self.selection_subtitle.setText(element.kind)
            self.id_value.setText(element.window_id)
            self.kind_value.setText(element.kind)
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
        super().__init__(f"Mover/redimensionar WindowID {window.document.elements[index].window_id}")
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
        super().__init__(f"Mover {len(changes)} elementos")
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
            f"Alterar recorte DDS do WindowID {window.document.elements[index].window_id}"
        )
        self.window = window
        self.index = index
        self.old = old
        self.new = new

    def redo(self) -> None:
        self.window.apply_uv(self.index, self.new)

    def undo(self) -> None:
        self.window.apply_uv(self.index, self.old)


class EditorWindow(QMainWindow):
    def __init__(self, initial_path: Path | None = None):
        super().__init__()
        self.document: UIDocument | None = None
        self.texture_cache: TextureCache | None = None
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

        self.undo_stack = QUndoStack(self)
        self.scene = QGraphicsScene(self)
        self.view = EditorView(self.move_selected)
        self.view.setFrameShape(QFrame.Shape.NoFrame)
        self.view.setScene(self.scene)
        self.cursor_position_label = QLabel("Mouse: X — · Y —")
        self.cursor_position_label.setMinimumWidth(150)
        self.view.cursor_scene_moved.connect(
            lambda x, y: self.cursor_position_label.setText(
                f"Mouse: X {x} · Y {y}"
            )
        )
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Pesquisar WindowID, tipo, texto ou textura…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self.filter_tree)
        self.tree = QTreeWidget()
        self.tree.setObjectName("elementTree")
        self.tree.setHeaderLabels(["WindowID", "Tipo", "ParentNode", "Estado"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.tree.itemSelectionChanged.connect(self._tree_selection_changed)
        tree_panel = QWidget()
        tree_panel.setObjectName("treePanel")
        tree_layout = QVBoxLayout(tree_panel)
        tree_layout.setContentsMargins(12, 12, 12, 12)
        tree_layout.setSpacing(8)
        tree_title = QLabel("ELEMENTOS")
        tree_title.setObjectName("sectionLabel")
        tree_layout.addWidget(tree_title)
        tree_layout.addWidget(self.search_edit)
        tree_layout.addWidget(self.tree)
        self.properties = PropertyPanel()
        self.properties.geometry_edited.connect(self.edit_selected_geometry)
        self.properties.atlas_requested.connect(self.open_selected_atlas)
        properties_scroll = QScrollArea()
        properties_scroll.setObjectName("propertiesScroll")
        properties_scroll.setFrameShape(QFrame.Shape.NoFrame)
        properties_scroll.setWidgetResizable(True)
        properties_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        properties_scroll.setWidget(self.properties)

        canvas_panel = QWidget()
        canvas_panel.setObjectName("canvasPanel")
        canvas_layout = QVBoxLayout(canvas_panel)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.setSpacing(0)
        canvas_header = QWidget()
        canvas_header.setObjectName("canvasHeader")
        canvas_header_layout = QHBoxLayout(canvas_header)
        canvas_header_layout.setContentsMargins(14, 7, 14, 7)
        canvas_title = QLabel("CANVAS")
        canvas_title.setObjectName("sectionLabel")
        canvas_hint = QLabel(
            "Arraste para mover  •  roda para zoom"
        )
        canvas_hint.setObjectName("canvasHint")
        canvas_hint.setToolTip(
            "Ctrl + clique: seleção múltipla • alça: redimensionar • "
            "botão do meio: navegar pelo canvas"
        )
        canvas_header_layout.addWidget(canvas_title)
        canvas_header_layout.addStretch(1)
        canvas_header_layout.addWidget(canvas_hint)
        canvas_layout.addWidget(canvas_header)
        canvas_layout.addWidget(self.view)

        splitter = QSplitter()
        splitter.addWidget(tree_panel)
        splitter.addWidget(canvas_panel)
        splitter.addWidget(properties_scroll)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([300, 900, 300])
        self.setCentralWidget(splitter)

        self._create_actions()
        self.properties.set_context_actions(
            self.lock_action, self.hide_action, self.isolate_action
        )
        self._create_menus_and_toolbar()
        self._apply_theme()
        self.resize(1500, 900)
        self.setWindowTitle("GF UI Editor")
        self.statusBar().showMessage("Abra um XML da pasta UI para começar.")
        self.statusBar().addPermanentWidget(self.cursor_position_label)

        if initial_path is not None:
            self.open_document(initial_path)

    def _create_actions(self) -> None:
        self.open_action = QAction("Abrir XML…", self)
        self.open_action.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton)
        )
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_action.setIconText("Abrir")
        self.open_action.setToolTip("Abrir XML (Ctrl+O)")
        self.open_action.triggered.connect(self.choose_document)
        self.save_action = QAction("Salvar com backup", self)
        self.save_action.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton)
        )
        self.save_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_action.setIconText("Salvar")
        self.save_action.setToolTip("Salvar com backup (Ctrl+S)")
        self.save_action.setEnabled(False)
        self.save_action.triggered.connect(self.save_document)
        self.undo_action = self.undo_stack.createUndoAction(self, "Desfazer")
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.redo_action = self.undo_stack.createRedoAction(self, "Refazer")
        self.redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self.fit_action = QAction("Enquadrar", self)
        self.fit_action.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DesktopIcon)
        )
        self.fit_action.setShortcut("F")
        self.fit_action.triggered.connect(self.fit_scene)
        self.labels_action = QAction("Mostrar identificadores", self)
        self.labels_action.setCheckable(True)
        self.labels_action.setChecked(False)
        self.labels_action.setShortcut("I")
        self.labels_action.toggled.connect(self.set_labels_visible)
        self.textures_action = QAction("Mostrar texturas", self)
        self.textures_action.setCheckable(True)
        self.textures_action.setChecked(True)
        self.textures_action.setShortcut("T")
        self.textures_action.toggled.connect(self.set_textures_visible)
        self.atlas_action = QAction("Abrir atlas DDS…", self)
        self.atlas_action.setEnabled(False)
        self.atlas_action.triggered.connect(self.open_selected_atlas)
        self.reload_textures_action = QAction("Recarregar texturas", self)
        self.reload_textures_action.setShortcut(QKeySequence.StandardKey.Refresh)
        self.reload_textures_action.setEnabled(False)
        self.reload_textures_action.triggered.connect(self.reload_all_textures)
        self.watch_textures_action = QAction("Atualizar DDS automaticamente", self)
        self.watch_textures_action.setCheckable(True)
        self.watch_textures_action.setChecked(True)
        self.watch_textures_action.toggled.connect(self._watch_texture_files)
        self.lock_action = QAction("Bloquear selecionado", self)
        self.lock_action.setShortcut("Ctrl+Shift+L")
        self.lock_action.setIconText("Bloquear")
        self.lock_action.setEnabled(False)
        self.lock_action.triggered.connect(self.toggle_selected_lock)
        self.hide_action = QAction("Ocultar selecionado", self)
        self.hide_action.setShortcut("Ctrl+Shift+H")
        self.hide_action.setIconText("Ocultar")
        self.hide_action.setEnabled(False)
        self.hide_action.triggered.connect(self.toggle_selected_hidden)
        self.isolate_action = QAction("Isolar selecionado", self)
        self.isolate_action.setShortcut("Ctrl+Shift+I")
        self.isolate_action.setIconText("Isolar")
        self.isolate_action.setEnabled(False)
        self.isolate_action.triggered.connect(self.toggle_isolation)

    def _create_menus_and_toolbar(self) -> None:
        file_menu = self.menuBar().addMenu("Arquivo")
        file_menu.addAction(self.open_action)
        file_menu.addAction(self.save_action)
        edit_menu = self.menuBar().addMenu("Editar")
        edit_menu.addAction(self.undo_action)
        edit_menu.addAction(self.redo_action)
        view_menu = self.menuBar().addMenu("Visualização")
        view_menu.addAction(self.fit_action)
        view_menu.addAction(self.labels_action)
        view_menu.addAction(self.textures_action)
        view_menu.addAction(self.atlas_action)
        view_menu.addAction(self.reload_textures_action)
        view_menu.addAction(self.watch_textures_action)
        view_menu.addSeparator()
        view_menu.addAction(self.lock_action)
        view_menu.addAction(self.hide_action)
        view_menu.addAction(self.isolate_action)
        toolbar = self.addToolBar("Principal")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        toolbar.addAction(self.open_action)
        toolbar.addAction(self.save_action)
        toolbar.addSeparator()
        toolbar.addAction(self.undo_action)
        toolbar.addAction(self.redo_action)
        toolbar.addSeparator()
        toolbar.addAction(self.fit_action)
        toolbar.addAction(self.reload_textures_action)

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            stylesheet(
                """
            QMainWindow, QWidget {
                background: ${WINDOW_BG};
                color: ${TEXT_PRIMARY};
                font-size: 12px;
            }
            QMenuBar, QMenu, QToolBar, QStatusBar {
                background: ${CHROME_BG};
                color: ${TEXT_PRIMARY};
            }
            QMenuBar { border-bottom: 1px solid ${BORDER_CHROME}; }
            QMenuBar::item:selected, QMenu::item:selected { background: ${MENU_HOVER_BG}; }
            QToolBar {
                border: 0;
                border-bottom: 1px solid ${BORDER_CHROME};
                spacing: 4px;
                padding: 5px 7px;
            }
            QToolButton {
                border: 1px solid transparent;
                border-radius: 5px;
                padding: 5px 8px;
            }
            QToolButton:hover { background: ${BUTTON_HOVER_BG}; border-color: ${BUTTON_HOVER_BORDER}; }
            QToolButton:pressed { background: ${BUTTON_PRESSED_BG}; }
            QToolButton:disabled { color: ${TEXT_DISABLED}; }
            QWidget#treePanel, QWidget#propertiesPanel { background: ${PANEL_BG}; }
            QWidget#canvasHeader { background: ${PANEL_BG}; border-bottom: 1px solid ${BORDER_PANEL}; }
            QLabel#sectionLabel {
                color: ${TEXT_SECTION};
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 1px;
            }
            QLabel#panelTitle { color: ${TEXT_TITLE}; font-size: 17px; font-weight: 700; }
            QLabel#panelSubtitle, QLabel#canvasHint { color: ${TEXT_SUBTITLE}; }
            QLabel#fieldLabel { color: ${TEXT_SUBTITLE}; }
            QLabel#fieldValue { color: ${TEXT_BRIGHT}; font-weight: 600; }
            QToolButton#inspectorAction {
                background: ${INPUT_BG};
                color: ${TEXT_PRIMARY};
                border: 1px solid ${BORDER_PANEL};
                border-radius: 5px;
                padding: 6px 4px;
            }
            QToolButton#inspectorAction:hover { background: ${BUTTON_HOVER_BG}; border-color: ${BUTTON_HOVER_BORDER}; }
            QToolButton#inspectorAction:pressed { background: ${BUTTON_PRESSED_BG}; }
            QToolButton#inspectorAction:focus { border-color: ${FOCUS_BLUE}; }
            QLineEdit, QSpinBox, QPlainTextEdit {
                background: ${INPUT_BG};
                color: ${TEXT_BRIGHT};
                border: 1px solid ${BORDER_INPUT};
                border-radius: 5px;
                padding: 5px 7px;
                selection-background-color: ${SELECTION_BLUE};
            }
            QLineEdit:focus, QSpinBox:focus { border-color: ${FOCUS_BLUE}; }
            QLineEdit:read-only { color: ${TEXT_READONLY}; background: transparent; border-color: transparent; }
            QTreeWidget {
                background: ${PANEL_BG};
                alternate-background-color: ${TREE_ALTERNATE_BG};
                border: 1px solid ${BORDER_PANEL};
                border-radius: 6px;
                outline: 0;
            }
            QTreeWidget::item { min-height: 23px; }
            QTreeWidget::item:selected { background: ${TREE_SELECTED_BG}; color: ${WHITE}; }
            QTreeWidget::item:hover:!selected { background: ${TREE_HOVER_BG}; }
            QHeaderView::section {
                background: ${INPUT_BG};
                color: ${TEXT_HEADER};
                border: 0;
                border-bottom: 1px solid ${BORDER_INPUT};
                padding: 6px;
                font-weight: 600;
            }
            QSplitter::handle { background: ${BORDER_PANEL}; }
            QSplitter::handle:horizontal { width: 1px; }
            QScrollBar:vertical, QScrollBar:horizontal { background: ${WINDOW_BG}; border: 0; }
            QScrollBar::handle { background: ${SCROLLBAR_HANDLE}; border-radius: 4px; min-height: 24px; min-width: 24px; }
            QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
            QStatusBar { border-top: 1px solid ${BORDER_CHROME}; color: ${TEXT_STATUS}; }
            QToolTip { background: ${TOOLTIP_BG}; color: ${TEXT_BRIGHT}; border: 1px solid ${BORDER_TOOLTIP}; }
                """
            )
        )

    def choose_document(self) -> None:
        if not self._confirm_discard_changes():
            return
        initial = DEFAULT_UI_DIRECTORY if DEFAULT_UI_DIRECTORY.exists() else Path.home()
        filename, _ = QFileDialog.getOpenFileName(
            self, "Abrir XML de interface", str(initial), "XML (*.xml);;Todos os arquivos (*)"
        )
        if filename:
            self.open_document(Path(filename))

    def open_document(self, path: Path) -> None:
        try:
            document = UIDocument.load(path)
        except DocumentError as exc:
            QMessageBox.critical(self, "Não foi possível abrir", str(exc))
            return
        self.document = document
        ui_directory = document.path.parent.resolve()
        if (
            self.texture_cache is None
            or self.texture_cache.ui_directory != ui_directory
        ):
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
        self._rebuild_scene()
        self._rebuild_tree()
        self.save_action.setEnabled(True)
        self.reload_textures_action.setEnabled(True)
        self._watch_texture_files()
        self._update_element_actions()
        self._update_title()
        missing = len(self.texture_cache.missing)
        suffix = f" · {missing} textura(s) ausente(s)" if missing else ""
        self.statusBar().showMessage(f"{len(document.elements)} elementos carregados{suffix}")
        self.fit_scene()

    def _rebuild_scene(self) -> None:
        assert self.document is not None and self.texture_cache is not None
        self.view.set_interaction_priority(None)
        self.scene.clear()
        self.items.clear()
        for element in self.document.elements:
            pixmap = self.texture_cache.pixmap_for(element)
            item = ElementItem(
                element, pixmap, self._canvas_selection_changed, self.elements_dragged
            )
            item.set_labels_visible(self.labels_action.isChecked())
            item.set_texture_visible(self.textures_action.isChecked())
            self.scene.addItem(item)
            self.items[element.index] = item
        bounds = self.scene.itemsBoundingRect().adjusted(-50, -50, 50, 50)
        self.scene.setSceneRect(bounds)

    def _rebuild_tree(self) -> None:
        assert self.document is not None
        self.tree.clear()
        self.tree_items.clear()
        id_map: dict[str, QTreeWidgetItem] = {}
        pending: list[tuple[UIElement, QTreeWidgetItem]] = []
        for element in self.document.elements:
            item = QTreeWidgetItem(
                [element.window_id, element.kind, element.parent_id or "", ""]
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
        finally:
            self._syncing_selection = False

    def _set_primary_selection(self, index: int, selection_count: int) -> None:
        assert self.document is not None
        self.selected_index = index
        self.view.set_interaction_priority(self.items[index])
        self.properties.set_element(self.document.elements[index])
        self.properties.set_enabled(index not in self.locked_indexes)
        if self.isolated_index is not None and self.isolated_index != index:
            previous_isolated_index = self.isolated_index
            self.isolated_index = index
            self._apply_visibility_state()
            self._refresh_tree_state(previous_isolated_index)
            self._refresh_tree_state(index)
        self._update_element_actions()
        suffix = f" · {selection_count} selecionados" if selection_count > 1 else ""
        self.statusBar().showMessage(
            f"WindowID {self.document.elements[index].window_id} · índice {index}{suffix}"
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
        if changes:
            self.undo_stack.push(GeometryBatchCommand(self, changes))

    def edit_selected_geometry(self, geometry: tuple[int, int, int, int]) -> None:
        if self.document is None or self.selected_index is None:
            return
        if self.selected_index in self.locked_indexes:
            self.statusBar().showMessage("O elemento selecionado está bloqueado.", 3000)
            self.properties.set_element(self.document.elements[self.selected_index])
            self.properties.set_enabled(False)
            return
        element = self.document.elements[self.selected_index]
        if element.geometry != geometry:
            self.undo_stack.push(
                GeometryCommand(self, self.selected_index, element.geometry, geometry)
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
        if changes:
            self.undo_stack.push(GeometryBatchCommand(self, changes))
        else:
            self.statusBar().showMessage("Os elementos selecionados estão bloqueados.", 3000)

    def apply_geometry(self, index: int, geometry: tuple[int, int, int, int]) -> None:
        assert self.document is not None
        self.document.set_geometry(index, geometry)
        self.items[index].apply_element(self.document.elements[index])
        if self.selected_index == index:
            self.properties.set_element(self.document.elements[index])
        self._update_title()

    def edit_uv(self, index: int, uv: UVRect, resize_element: bool) -> None:
        if self.document is None:
            return
        if index in self.locked_indexes:
            self.statusBar().showMessage("O elemento selecionado está bloqueado.", 3000)
            return
        element = self.document.elements[index]
        if element.uv is None:
            return
        geometry = (element.x, element.y, uv.width, uv.height)
        uv_changed = element.uv != uv
        geometry_changed = resize_element and element.geometry != geometry
        if not uv_changed and not geometry_changed:
            return
        self.undo_stack.beginMacro(f"Alterar atlas do WindowID {element.window_id}")
        if uv_changed:
            self.undo_stack.push(UVCommand(self, index, element.uv, uv))
        if geometry_changed:
            self.undo_stack.push(
                GeometryCommand(self, index, element.geometry, geometry)
            )
        self.undo_stack.endMacro()

    def apply_uv(self, index: int, uv: UVRect) -> None:
        assert self.document is not None
        self.document.set_uv(index, uv)
        self._refresh_element_texture(index)
        if self.selected_index == index:
            self.properties.set_element(self.document.elements[index])
        self._update_title()

    def open_selected_atlas(self) -> None:
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
                "Este elemento não possui uma textura NorUV editável.", 4000
            )
            return
        pixmap = self.texture_cache.source_pixmap(element.texture_name)
        if pixmap is None:
            self.statusBar().showMessage(
                f"Não foi possível abrir {element.texture_name}.", 5000
            )
            return
        if self.atlas_dialog is not None:
            self.atlas_dialog.close()
        dialog = AtlasDialog(
            element.texture_name,
            pixmap,
            element.uv,
            lambda uv, resize, item_index=index: self.edit_uv(
                item_index, uv, resize
            ),
            self,
            progress_offset=element.progress_offset,
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
        self.items[index].set_pixmap(self.texture_cache.pixmap_for(element))

    def reload_all_textures(self) -> None:
        if self.document is None or self.texture_cache is None:
            return
        self.texture_cache.invalidate()
        for index in self.items:
            self._refresh_element_texture(index)
        self._reload_open_atlas()
        self.statusBar().showMessage("Texturas recarregadas do disco.", 4000)

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
                    f"A textura {texture_path.name} não está disponível.", 5000
                )
            return
        resolved = texture_path.resolve()
        self.texture_cache.invalidate(resolved)
        refreshed = 0
        for element in self.document.elements:
            if not element.texture_name:
                continue
            element_path = self.texture_cache.path_for(element.texture_name)
            if element_path is not None and element_path.resolve() == resolved:
                self._refresh_element_texture(element.index)
                refreshed += 1
        self._reload_open_atlas()
        self._watch_texture_files()
        self.statusBar().showMessage(
            f"{texture_path.name} atualizado automaticamente · {refreshed} elemento(s).",
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
            states.append("Bloqueado")
        if index in self.hidden_indexes:
            states.append("Oculto")
        if index == self.isolated_index:
            states.append("Isolado")
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
            self.lock_action.setText("Bloquear selecionado")
            self.lock_action.setIconText("Bloquear")
            self.hide_action.setText("Ocultar selecionado")
            self.hide_action.setIconText("Ocultar")
            self.isolate_action.setText("Isolar selecionado")
            self.isolate_action.setIconText("Isolar")
            return
        assert self.selected_index is not None
        self.lock_action.setText(
            "Desbloquear selecionado"
            if self.selected_index in self.locked_indexes
            else "Bloquear selecionado"
        )
        self.lock_action.setIconText(
            "Desbloquear" if self.selected_index in self.locked_indexes else "Bloquear"
        )
        self.hide_action.setText(
            "Mostrar selecionado"
            if self.selected_index in self.hidden_indexes
            else "Ocultar selecionado"
        )
        self.hide_action.setIconText(
            "Mostrar" if self.selected_index in self.hidden_indexes else "Ocultar"
        )
        self.isolate_action.setText(
            "Mostrar todos" if self.isolated_index is not None else "Isolar selecionado"
        )
        self.isolate_action.setIconText(
            "Mostrar todos" if self.isolated_index is not None else "Isolar"
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
                        element.kind,
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
        if not self.scene.items():
            return
        self.view.fitInView(self.scene.itemsBoundingRect().adjusted(-20, -20, 20, 20), Qt.AspectRatioMode.KeepAspectRatio)

    def save_document(self) -> None:
        if self.document is None:
            return
        if not self.document.is_dirty:
            self.statusBar().showMessage("Nenhuma alteração para salvar.", 4000)
            return
        if not self._confirm_diff_preview():
            return
        try:
            backup = self.document.save()
        except ExternalModificationError as exc:
            QMessageBox.warning(self, "Arquivo alterado externamente", str(exc))
            return
        except DocumentError as exc:
            QMessageBox.critical(self, "Falha ao salvar", str(exc))
            return
        self.undo_stack.clear()
        self._update_title()
        self.statusBar().showMessage(f"Salvo. Backup: {backup.name}", 10000)
        QMessageBox.information(
            self,
            "XML salvo",
            f"As alterações foram salvas.\n\nBackup exato:\n{backup}",
        )

    def _confirm_diff_preview(self) -> bool:
        assert self.document is not None
        dialog = QDialog(self)
        dialog.setWindowTitle("Confirmar alterações no XML")
        dialog.resize(1000, 650)
        explanation = QLabel(
            "Confira as linhas que serão alteradas. O backup exato será criado antes da gravação."
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
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout = QVBoxLayout(dialog)
        layout.addWidget(explanation)
        layout.addWidget(diff_view)
        layout.addWidget(buttons)
        return dialog.exec() == QDialog.DialogCode.Accepted

    def _update_title(self) -> None:
        if self.document is None:
            self.setWindowTitle("GF UI Editor")
            return
        marker = " *" if self.document.is_dirty else ""
        self.setWindowTitle(f"GF UI Editor — {self.document.path.name}{marker}")

    def _confirm_discard_changes(self) -> bool:
        if self.document is None or not self.document.is_dirty:
            return True
        result = QMessageBox.question(
            self,
            "Descartar alterações?",
            "Existem alterações não salvas. Deseja descartá-las?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return result == QMessageBox.StandardButton.Yes

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self._confirm_discard_changes():
            event.accept()
        else:
            event.ignore()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Editor visual dos XMLs de UI do Grand Fantasia")
    parser.add_argument("xml", nargs="?", type=Path, help="XML que será aberto ao iniciar")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    application = QApplication(sys.argv[:1])
    application.setApplicationName("GF UI Editor")
    application.setOrganizationName("Local")
    window = EditorWindow(args.xml)
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
