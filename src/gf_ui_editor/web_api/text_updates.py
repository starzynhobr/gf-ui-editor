"""Ponte: aviso de atualização dos textos do jogo (serviço game_text_updates).

A casca chama `text_updates_check()` ao abrir um projeto (e depois de voltar ao app): se
o launcher trocou os .ini, mostra o banner com IDs novos, textos oficiais alterados e
edições do projeto desfeitas; "Reenviar edições" é o F5 normal; "Entendi" chama
`text_updates_acknowledge()`.
"""

from __future__ import annotations

from .. import game_text_updates, text_data
from .. import project as project_module


class TextUpdatesApi:
    """Métodos públicos viram window.pywebview.api.<nome>. Só tipos JSON."""

    def _text_updates_context(self):
        project = getattr(self, "_project", None)
        game_dir = getattr(project, "game_dir", None)
        return project, game_dir

    def text_updates_check(self) -> dict | None:
        """None se não houve atualização dos textos desde o último aviso visto."""
        project, game_dir = self._text_updates_context()
        if game_dir is None:
            return None
        update = game_text_updates.check(game_dir, project_module.PROJECTS_ROOT)
        edits = text_data.load_edits(project.root) if project is not None else {}
        impact = game_text_updates.project_impact(game_dir, edits) if edits else game_text_updates.ProjectImpact()
        if update is None and not impact.reverted:
            return None
        return {
            "update": None if update is None else {
                "changed_files": update.changed_files,
                "unavailable": update.unavailable,
                "new_ids": update.new_ids,
                "changed_texts": update.changed_texts,
                "files": [
                    {
                        "name": item.name,
                        "new_ids": item.new_ids,
                        "removed_ids": item.removed_ids,
                        "changed": [{"id": rid, "before": before, "after": after} for rid, before, after in item.changed],
                    }
                    for item in update.files
                ],
            },
            "reverted": [{"file": name, "id": rid} for name, rid in impact.reverted],
            "official_changed": [
                {"file": name, "id": rid, "original": original, "official": official}
                for name, rid, original, official in impact.official_changed
            ],
            "missing": [{"file": name, "id": rid} for name, rid in impact.missing],
        }

    def text_updates_acknowledge(self) -> None:
        _project, game_dir = self._text_updates_context()
        if game_dir is not None:
            game_text_updates.acknowledge(game_dir, project_module.PROJECTS_ROOT)
