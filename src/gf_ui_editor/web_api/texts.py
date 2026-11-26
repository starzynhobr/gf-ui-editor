"""Ponte: tela de Textos (Ctrl+4) da interface nova (dono: casca).

Só chama o serviço texts_session (o mesmo da aba Textos da clássica). O contexto vem do
projeto aberto (ProjectsApi._project). Textos visíveis ficam no front: aqui saem chaves.

Eventos (Python -> front):
- "texts_index_ready": o índice FTS5 do jogo ficou pronto (a busca fica mais rápida e completa).
- "text_edits_changed" {"project", "files"}: edições de texto gravadas no project.db. O canvas
  pode reabrir o documento para o modo de texto do jogo mostrar o texto novo (os rótulos vêm
  de storage.peek_preview_context, que lê essas edições).
"""

from __future__ import annotations

from pathlib import Path
import threading
from typing import Any

from .. import text_data, texts_session
from ..text_data import TextImport


class TextsApi:
    """Métodos públicos viram window.pywebview.api.<nome>. Só tipos JSON."""

    # ---- infraestrutura ---------------------------------------------------------------------
    def _texts(self) -> texts_session.TextsSession:
        """Sessão de textos (criada na primeira chamada) já no contexto do projeto aberto."""
        if not hasattr(self, "_texts_state"):
            self._texts_state = texts_session.TextsSession()
            self._texts_lock = threading.RLock()
            self._texts_plan: TextImport | None = None
        session = self._texts_state
        project = getattr(self, "_project", None)
        game_dir = project.game_dir if project is not None else None
        root = project.root if project is not None else None
        if (session.game_dir, session.project_root) != (game_dir, root):
            session.set_context(game_dir, root)
            self._texts_plan = None
            session.start_indexing(self._texts_index_done)
        return session

    def _texts_index_done(self, game_dir: Path) -> None:
        with self._texts_lock:
            ready = self._texts_state.index_finished(game_dir)
        if ready:
            self._emit("texts_index_ready", None)

    def _emit(self, event: str, payload: Any = None) -> None:  # o WebApi sobrescreve
        pass

    def _texts_changed(self, names: list[str]) -> None:
        session = self._texts_state
        self._emit("text_edits_changed", {"project": str(session.project_root), "files": sorted(set(names))})

    # ---- API -----------------------------------------------------------------------------
    def texts_state(self) -> dict:
        with self._lock_texts():
            session = self._texts()
            return {
                "available": session.game_dir is not None,
                "can_import": session.can_import,
                "index_ready": session.game_dir is not None and session.index_ready,
            }

    def _lock_texts(self) -> threading.RLock:
        self._texts()  # cria a sessão e o lock
        return self._texts_lock

    def texts_search(self, query: str, edited_only: bool) -> dict:
        """Resultados com estado (edited/updated/changed), total, resumo (chave + números)."""
        with self._lock_texts():
            found = self._texts().results(query, bool(edited_only))
        return {
            "rows": [
                {
                    "name": row.name,
                    "id": row.record_id,
                    "fields": row.fields,
                    "state": row.state,
                    "game_fields": row.game_fields,
                    "original": row.original,
                }
                for row in found.rows
            ],
            "total": found.total,
            "summary": found.summary,
            "values": found.values,
            "updates": found.updates,
            "limit": texts_session.RESULT_LIMIT,
        }

    def texts_open(self, name: str, record_id: str) -> dict | None:
        """Um registro para o editor: campos (com \\n), original, encoding e quebra de linha."""
        with self._lock_texts():
            opened = self._texts().open_record(name, str(record_id))
        if opened is None:
            return None
        plain = lambda values: [value.replace("\r\n", "\n") for value in values]  # noqa: E731
        return {
            "name": name,
            "id": str(record_id),
            "fields": plain(opened.fields),
            "original": plain(opened.original) if opened.original is not None else None,
            "can_restore": opened.can_restore,
            "encoding": opened.text_file.encoding,
            "newline": opened.newline,
        }

    def texts_save(self, name: str, record_id: str, values: list[str]) -> dict:
        """Grava a edição. {"error": "pipe"|"encoding", "encoding"} se o texto não pode ir para o jogo."""
        with self._lock_texts():
            session = self._texts()
            opened = session.open_record(name, str(record_id))
            if opened is None:
                raise ValueError(f"{name} · ID {record_id} não existe no jogo.")
            values = [str(value).replace("\r\n", "\n").replace("\n", opened.newline) for value in values]
            problem = texts_session.validate(values, opened.text_file.encoding)
            if problem is not None:
                return {"error": problem, "encoding": opened.text_file.encoding}
            session.save_record(opened, values)
        self._texts_changed([name])
        return {"saved": True}

    def texts_restore(self, name: str, record_id: str) -> dict:
        """Volta ao texto original (a edição fica, para o próximo envio regravar o original)."""
        with self._lock_texts():
            session = self._texts()
            opened = session.open_record(name, str(record_id))
            if opened is None:
                raise ValueError(f"{name} · ID {record_id} não existe no jogo.")
            session.save_record(opened, None)
        self._texts_changed([name])
        return {"saved": True}

    def texts_reload(self) -> None:
        """Os arquivos do jogo mudaram (o F5 enviou textos): relê e refaz o índice."""
        with self._lock_texts():
            session = self._texts()
            session.reload()
            session.start_indexing(self._texts_index_done)

    # ---- importar ------------------------------------------------------------------------
    def texts_pick_import(self) -> str | None:
        """Pasta com os T_*.ini alterados (diálogo nativo, começando ao lado do jogo)."""
        with self._lock_texts():
            session = self._texts()
            if not session.can_import:
                return None
            start = session.game_dir.parent
        ask = getattr(self, "_ask_path", None)
        chosen = ask("folder", start) if ask is not None else None
        return str(chosen) if chosen is not None else None

    def texts_plan_import(self, folder: str) -> dict:
        """O que a importação faria (números para a pergunta); guarda o plano para aplicar."""
        with self._lock_texts():
            session = self._texts()
            if not session.can_import:
                raise ValueError("Sem projeto ou sem pasta do jogo.")
            plan = session.plan_import(Path(folder))
            self._texts_plan = plan
        return {
            "count": plan.count,
            "missing_ids": plan.missing_ids,
            "unsupported": plan.unsupported,
            "unknown_files": list(plan.unknown_files),
            "replaced": plan.replaced,
            "per_file": [[name, len(records)] for name, records in sorted(plan.edits.items())],
            "folder": str(text_data.import_source_folder(Path(folder))),
        }

    def texts_apply_import(self) -> int:
        """Aplica o último plano (depois da confirmação). Devolve quantos textos entraram."""
        with self._lock_texts():
            plan = self._texts_plan
            if plan is None or not plan.count:
                return 0
            self._texts().apply_import(plan)
            self._texts_plan = None
        self._texts_changed(list(plan.edits))
        return plan.count
