"""Ponte do painel "Ver código XML" para a sessão do documento."""

from __future__ import annotations

class SourceApi:
    """Métodos públicos viram window.pywebview.api.<nome>. Só tipos JSON."""

    def doc_source(self) -> dict | None:
        session = getattr(self, "_document_session", None)
        return session.source() if session is not None else None

    def doc_apply_source(self, path: str, text: str, expected: str) -> dict:
        return self._document_session.apply_source(path, text, expected)

    def doc_source_history(self, redo: bool) -> dict:
        return self._document_session.move_source_history(redo)
