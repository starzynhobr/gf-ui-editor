"""Ponte: XML aberto em memória, edição, diff e salvar (dono: bloco 2, canvas).

Contrato em vault/web-bridge.md e web/src/doc/store.ts. O documento em memória é a fonte
da verdade das duas listas do front (canvas e árvore/painel). Regras do jogo e de gravação
ficam nos serviços sem Qt (xml_document, window_geometry, project…), não aqui.

Métodos previstos: doc_open(path), doc_edit(edits) -> documento, doc_diff() -> str,
doc_save(), doc_revert().
"""

from __future__ import annotations


class DocumentApi:
    """Métodos públicos viram window.pywebview.api.<nome>. Só tipos JSON."""
