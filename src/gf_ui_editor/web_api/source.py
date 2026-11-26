"""Ponte: "Ver código XML" — o XML aberto no estado atual, com as edições não salvas.

Só leitura: lê o documento da sessão do documento (`web_api/document.py`) sem mudá-lo. O
texto e as linhas dos elementos vêm do serviço `xml_source`.
"""

from __future__ import annotations

from ..xml_source import source_view


class SourceApi:
    """Métodos públicos viram window.pywebview.api.<nome>. Só tipos JSON."""

    def doc_source(self) -> dict | None:
        session = getattr(self, "_document_session", None)
        if session is None:
            return None
        with session._lock:  # noqa: SLF001 - leitura sob a mesma trava da sessão
            document = session._document  # noqa: SLF001
            return source_view(document) if document is not None else None
