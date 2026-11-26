"""Ponte: XML aberto em memória, edição, diff e salvar (dono: bloco 2, canvas).

Contrato em vault/web-bridge.md e web/src/doc/store.ts. O documento em memória é a fonte
da verdade das duas listas do front (canvas e árvore/painel). Regras do jogo e de gravação
ficam nos serviços sem Qt (xml_document, window_geometry, project…), não aqui.

Métodos previstos: doc_open(path), doc_edit(edits) -> documento, doc_diff() -> str,
doc_save(), doc_revert().
"""

from __future__ import annotations

from ..about import parse_resolution
from ..document_session import DocumentSession


class DocumentApi:
    """Métodos públicos viram window.pywebview.api.<nome>. Só tipos JSON."""

    def _setup_document(self) -> None:
        self._document_session = DocumentSession()

    def doc_open(self, path: str | None, resolution: list[int] | None = None) -> dict | None:
        size = tuple(resolution) if resolution is not None else parse_resolution(self._prefs.game_resolution)
        return self._document_session.open(path, size, saved_positions=self._prefs.canvas_saved_positions)

    def doc_edit(self, edits: list[dict]) -> dict:
        return self._document_session.edit(edits)

    def doc_canvas_edit(self, edits: list[dict], locked: list[int], preview: bool, root_background: bool) -> dict:
        return self._document_session.edit_canvas(edits, locked, preview, root_background)

    def doc_diff(self) -> str:
        return self._document_session.diff()

    def doc_save(self) -> dict:
        return self._document_session.save(getattr(self, "_project", None))

    def doc_revert(self) -> dict:
        return self._document_session.revert()

    def doc_external_change(self) -> str | None:
        return self._document_session.external_change()

    def doc_atlas_plan(self, path: str, index: int, before: dict, after: dict, resize: bool) -> list[dict]:
        return self._document_session.plan_atlas(path, index, before, after, resize)

    def doc_refresh_texts(self, project: str) -> dict | None:
        return self._document_session.refresh_texts(project)
