"""Traduções da interface; dados do jogo permanecem no idioma original."""

from pathlib import Path

from PySide6.QtCore import QCoreApplication, QTranslator


LANGUAGE_NAMES = (
    ("pt_BR", "Português (Brasil)"),
    ("en_US", "English"),
    ("es_ES", "Español"),
    ("fr_FR", "Français"),
)
LANGUAGES = tuple(code for code, _name in LANGUAGE_NAMES)
TRANSLATIONS_DIR = Path(__file__).resolve().parent / "translations"


def install_language(application: QCoreApplication, language: str) -> QTranslator | None:
    """Instala a tradução antes de criar janelas; português é a fonte padrão."""
    if language == "pt_BR":
        return None
    if language not in LANGUAGES:
        raise ValueError(f"Idioma não suportado: {language}")
    translator = QTranslator(application)
    if not translator.load(str(TRANSLATIONS_DIR / f"gf_ui_editor_{language}.qm")):
        raise RuntimeError(f"Tradução não encontrada: {language}")
    application.installTranslator(translator)
    return translator


def kind_label(kind: str, ctrl_type: str | None = None) -> str:
    """Converte o código estável do modelo em um rótulo localizado."""
    labels = {
        "multiline_text": QCoreApplication.translate("ElementKind", "Texto multilinha"),
        "text_field": QCoreApplication.translate("ElementKind", "Campo de texto"),
        "button": QCoreApplication.translate("ElementKind", "Botão"),
        "text": QCoreApplication.translate("ElementKind", "Texto"),
        "slot": QCoreApplication.translate("ElementKind", "Slot"),
        "progress": QCoreApplication.translate("ElementKind", "Progresso"),
        "slider": QCoreApplication.translate("ElementKind", "Controle deslizante"),
        "image": QCoreApplication.translate("ElementKind", "Imagem"),
        "panel": QCoreApplication.translate("ElementKind", "Painel"),
        "window": QCoreApplication.translate("ElementKind", "Janela"),
    }
    if kind == "control":
        return QCoreApplication.translate("ElementKind", "Controle {number}").format(
            number=ctrl_type or "?"
        )
    return labels.get(kind, kind)


def document_error_text(error: Exception) -> str:
    """Traduz erros do parser sem acoplar o modelo de XML ao Qt."""
    messages = {
        "element_count": QCoreApplication.translate("DocumentError", "Não foi possível relacionar todos os elementos ao texto original ({elements} elementos, {tags} tags)."),
        "uv_count": QCoreApplication.translate("DocumentError", "Não foi possível relacionar todos os recortes NorUV ao texto original ({cuts} recortes, {tags} tags)."),
        "read": QCoreApplication.translate("DocumentError", "Não foi possível ler {path}: {error}"),
        "decode": QCoreApplication.translate("DocumentError", "O arquivo não pôde ser decodificado como Big5: {error}"),
        "roundtrip": QCoreApplication.translate("DocumentError", "A leitura Big5 não preserva exatamente os bytes do arquivo."),
        "invalid_xml": QCoreApplication.translate("DocumentError", "XML inválido: {error}"),
        "reread": QCoreApplication.translate("DocumentError", "Não foi possível reler o arquivo antes de salvar: {error}"),
        "external_change": QCoreApplication.translate("DocumentError", "O XML foi alterado por outro programa desde que foi aberto. Reabra o arquivo para não sobrescrever mudanças externas."),
        "validation": QCoreApplication.translate("DocumentError", "A versão editada não passou pela validação: {error}"),
        "write": QCoreApplication.translate("DocumentError", "Falha ao criar backup ou gravar o XML: {error}"),
    }
    code = getattr(error, "code", "")
    return messages[code].format(**error.details) if code in messages else str(error)
