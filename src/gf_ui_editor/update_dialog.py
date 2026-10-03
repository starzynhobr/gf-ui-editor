"""Diálogo de novidades: oferta de atualização ou notas da versão instalada."""

from __future__ import annotations

from html import escape

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .interaction import install_pointer_cursors
from .release_notes import SECTIONS, ReleaseNotes
from .theme import COLORS

UPDATE, LATER, SKIP = "update", "later", "skip"


def _section_title(name: str) -> str:
    return {
        "new": QCoreApplication.translate("WhatsNewDialog", "NOVO"),
        "improved": QCoreApplication.translate("WhatsNewDialog", "MELHORADO"),
        "fixed": QCoreApplication.translate("WhatsNewDialog", "CORRIGIDO"),
    }[name]


_SECTION_COLOR = {"new": "NOTE_NEW", "improved": "ACCENT_TEXT", "fixed": "SELECTION_GOLD"}


class WhatsNewDialog(QDialog):
    """`current_version` informado = oferta de atualização (com os três botões)."""

    def __init__(
        self,
        version: str,
        notes: ReleaseNotes | None,
        language: str,
        *,
        current_version: str | None = None,
        fallback_text: str = "",
        can_install: bool = True,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.choice = LATER
        offering = current_version is not None
        self.setWindowTitle(self.tr("Atualização disponível") if offering else self.tr("Novidades"))
        self.setMinimumWidth(600)

        header = QWidget()
        header.setObjectName("transparent")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(28, 24, 28, 18)
        header_layout.setSpacing(8)
        top = QHBoxLayout()
        top.setSpacing(8)
        if offering:
            old = QLabel(current_version)
            old.setObjectName("monoCaption")
            arrow = QLabel("→")
            arrow.setObjectName("monoCaption")
            top.addWidget(old)
            top.addWidget(arrow)
        chip = QLabel(version)
        chip.setObjectName("versionChip")
        top.addWidget(chip)
        top.addStretch(1)
        if notes is not None and notes.date:
            date = QLabel(notes.date)
            date.setObjectName("monoCaption")
            top.addWidget(date)
        title = QLabel(self.tr("O que chegou na {version}").format(version=version))
        title.setObjectName("heroTitle")
        header_layout.addLayout(top)
        header_layout.addWidget(title)

        body = QWidget()
        body.setObjectName("transparent")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(28, 18, 28, 18)
        body_layout.setSpacing(18)
        sections = notes.for_language(language) if notes is not None else {}
        for name in SECTIONS:
            entries = sections.get(name)
            if not entries:
                continue
            color = COLORS[_SECTION_COLOR[name]]
            heading = QLabel(_section_title(name))
            heading.setObjectName("sectionLabel")
            heading.setStyleSheet(f"color: {color};")
            block = QVBoxLayout()
            block.setSpacing(10)
            block.addWidget(heading)
            for entry_title, text in entries:
                row = QHBoxLayout()
                row.setSpacing(10)
                dot = QLabel("●")
                dot.setStyleSheet(f"color: {color}; font-size: 8px; background: transparent;")
                dot.setAlignment(Qt.AlignmentFlag.AlignTop)
                dot.setContentsMargins(0, 6, 0, 0)
                label = QLabel(
                    f"<span style='color:{COLORS['TEXT_BRIGHT']};font-weight:600'>{escape(entry_title)}</span> "
                    f"<span style='color:{COLORS['TEXT_PRIMARY']}'>{escape(text)}</span>"
                )
                label.setTextFormat(Qt.TextFormat.RichText)
                label.setWordWrap(True)
                label.setObjectName("noteEntry")
                row.addWidget(dot)
                row.addWidget(label, 1)
                block.addLayout(row)
            body_layout.addLayout(block)
        if not sections:
            # Release sem notas estruturadas: mostra o texto da página, sem interpretar.
            plain = QLabel(fallback_text or self.tr("Sem notas para esta versão."))
            plain.setTextFormat(Qt.TextFormat.PlainText)
            plain.setWordWrap(True)
            plain.setObjectName("noteEntry")
            body_layout.addWidget(plain)
        if offering:
            safety = QLabel(
                self.tr(
                    "Seu trabalho fica salvo antes de atualizar. O download é conferido por SHA-256 "
                    "antes de instalar, e nada é instalado sem a sua confirmação."
                )
                if can_install
                else self.tr("Você está rodando pelo código-fonte; a página da release será aberta.")
            )
            safety.setWordWrap(True)
            safety.setObjectName("noteBox")
            body_layout.addWidget(safety)
        body_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(body)
        scroll.setObjectName("propertiesScroll")
        scroll.setMinimumHeight(240)

        footer = QWidget()
        footer.setObjectName("transparent")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(28, 14, 28, 20)
        footer_layout.setSpacing(10)
        if offering:
            skip = QPushButton(self.tr("Pular esta versão"))
            skip.setObjectName("ghostPush")
            skip.clicked.connect(lambda: self._finish(SKIP))
            later = QPushButton(self.tr("Depois"))
            later.clicked.connect(lambda: self._finish(LATER))
            install = QPushButton(self.tr("Baixar e instalar") if can_install else self.tr("Abrir página da release"))
            install.setObjectName("accentPush")
            install.setDefault(True)
            install.clicked.connect(lambda: self._finish(UPDATE))
            footer_layout.addWidget(skip)
            footer_layout.addStretch(1)
            footer_layout.addWidget(later)
            footer_layout.addWidget(install)
        else:
            close = QPushButton(self.tr("Fechar"))
            close.setObjectName("accentPush")
            close.setDefault(True)
            close.clicked.connect(self.accept)
            footer_layout.addStretch(1)
            footer_layout.addWidget(close)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(header)
        layout.addWidget(self._line())
        layout.addWidget(scroll, 1)
        layout.addWidget(self._line())
        layout.addWidget(footer)
        install_pointer_cursors(self)
        self.resize(620, min(640, self.sizeHint().height() + 40))

    @staticmethod
    def _line() -> QFrame:
        line = QFrame()
        line.setObjectName("separatorLine")
        line.setFixedHeight(1)
        return line

    def _finish(self, choice: str) -> None:
        self.choice = choice
        self.accept()
