"""Ponte: XML aberto em memória, edição, diff e salvar (dono: bloco 2, canvas).

Contrato em vault/web-bridge.md e web/src/doc/store.ts. O documento em memória é a fonte
da verdade das duas listas do front (canvas e árvore/painel). Regras do jogo e de gravação
ficam nos serviços sem Qt (xml_document, window_geometry, project…), não aqui.

Métodos previstos: doc_open(path), doc_edit(edits) -> documento, doc_diff() -> str,
doc_save(), doc_revert().
"""

from __future__ import annotations

from pathlib import Path

from ..about import parse_resolution
from ..document_session import DocumentSession
from ..project import Project
from ..xml_source import SourceError


class DocumentApi:
    """Métodos públicos viram window.pywebview.api.<nome>. Só tipos JSON."""

    def _setup_document(self) -> None:
        self._document_session = DocumentSession()

    def doc_open(self, path: str | None, resolution: list[int] | None = None) -> dict | None:
        size = tuple(resolution) if resolution is not None else parse_resolution(self._prefs.game_resolution)
        target = Path(path).resolve() if path is not None else None
        project = self._project_for_path(target) if target is not None else None
        return self._document_session.open(
            target, size, saved_positions=self._prefs.canvas_saved_positions,
            project=project, standalone=project is None and target in self._standalone_paths,
        )

    def standalone_compare(self, path: str, source: str) -> str | None:
        return self._document_session.compare_standalone(Path(path).resolve(), self._project, self._game_dir(), source)

    def standalone_pick_project(self) -> str | None:
        folder = self._ask_path("folder", self._projects_root())
        return str(folder) if folder is not None else None

    def standalone_import(self, path: str, name: str | None, replace: bool, bring_textures: bool,
                          root: str | None = None) -> dict:
        target = Path(path).resolve()
        with self._standalone_lock:
            if self._open_path != target or target not in self._standalone_paths:
                raise ValueError("O arquivo avulso ativo mudou.")
            project = Project.load(Path(root)) if root is not None and not self._is_current(root) else self._require_project()
            try:
                result = self._document_session.import_standalone(
                    target, project, project.game_dir or self._game_dir(),
                    name=name, replace=replace, bring_textures=bring_textures,
                )
            except SourceError as exc:
                raise ValueError(f"{exc} Linha {exc.line}, coluna {exc.column}.") from exc
            if not result["conflict"]:
                if project is not self._project:
                    self._set_project(project)
                self._standalone_paths.pop(target)
                self._open_xml(Path(result["path"]))
                result["state"] = self.shell_state()
            return result

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
