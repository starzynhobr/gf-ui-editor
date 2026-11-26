"""Ponte: ferramentas do projeto da interface nova (dono: casca, bloco 3).

Versões, Puxar da pasta do jogo, Limpar, UI oficial de referência (guardar, comparar,
controles novos), resolver erro do jogo, exportar textos e as cópias que o F5 guarda dos
arquivos editados fora. Só chama os serviços sem Qt (versions, game_sync, cleanup,
game_updates, text_data, game_texts); a clássica usa os mesmos.

Projeto: cada método recebe a raiz (`root`) e usa o projeto aberto quando é o mesmo
(ProjectsApi._project), como o `_project_for` da clássica.

Eventos (Python -> front):
- "official_scan" {"root", "diffs": {arquivo: {"relative", "new_ids", "other_ids"}}}: a
  comparação com a UI oficial terminou (banner de controles novos, aviso do F5).
"""

from __future__ import annotations

from pathlib import Path
import threading
from typing import Any

from .. import cleanup, game_sync, game_texts, game_updates, home, remote_manifest, text_data, versions
from ..project import Project, ProjectNameTaken, selected_ui

LAUNCHER_DEFAULT_UI = "UI Padrão"  # nome da UI oficial no launcher (no Launcher.ini é "padrao")


def _version(version: versions.Version) -> dict:
    return {
        "path": str(version.path),
        "title": versions.version_title(version),
        "label": version.label,
        "created": version.created.isoformat(timespec="seconds"),
        "files": version.files,
        "size": home.human_size(version.size),
    }


def _candidate(item: game_sync.PullCandidate) -> dict:
    return {"relative": item.relative, "source": str(item.source), "new": item.new, "origin": item.origin, "origin_ui": item.origin_ui}


def _diff(diff: game_updates.FileDiff) -> dict:
    return {"relative": diff.relative, "new_ids": list(diff.new_ids), "other_ids": list(diff.other_ids)}


class MaintenanceApi:
    """Métodos públicos viram window.pywebview.api.<nome>. Só tipos JSON."""

    def _emit(self, event: str, payload: Any = None) -> None:  # o WebApi sobrescreve
        pass

    def _project_for(self, root: str) -> Project:
        current = getattr(self, "_project", None)
        if current is not None and home.is_same_root(current.root, Path(root)):
            return current
        return Project.load(Path(root))

    def _after_project_change(self, project: Project) -> None:
        """Arquivos do projeto mudaram (puxar, limpar, restaurar): listas e tamanho relidos."""
        project.files(refresh=True)
        project.invalidate_changes()
        sizes = getattr(self, "_sizes", None)
        if sizes is not None:
            sizes.forget(project.root)

    # ---- versões ---------------------------------------------------------------------------
    def versions_list(self, root: str) -> list[dict]:
        return [_version(version) for version in versions.list_versions(self._project_for(root))]

    def version_save(self, root: str, label: str = "") -> dict:
        project = self._project_for(root)
        path = versions.save_version(project, label)
        self._after_project_change(project)
        return {"path": str(path), "size": home.human_size(path.stat().st_size)}

    def version_restore(self, root: str, version: str) -> dict:
        """Restaura (a versão atual é salva antes, "antes de restaurar")."""
        project = self._project_for(root)
        result = versions.restore_version(project, Path(version))
        self._after_project_change(project)
        return {"written": result.written, "reverted": result.reverted, "removed": result.removed, "unresolved": result.unresolved[:15]}

    def version_branch(self, root: str, version: str, name: str) -> dict:
        """Novo projeto a partir da versão. {"error": "taken"} se o nome já existe."""
        try:
            versions.project_from_version(self._project_for(root), Path(version), name)
        except ProjectNameTaken:
            return {"error": "taken", "name": name.strip()}
        return {"name": name.strip()}

    def version_delete(self, version: str) -> None:
        versions.delete_version(Path(version))

    def versions_folder(self, root: str) -> str:
        folder = versions.versions_dir(self._project_for(root))
        folder.mkdir(parents=True, exist_ok=True)
        return str(folder)

    # ---- puxar da pasta do jogo -------------------------------------------------------------
    def pull_sources(self, root: str) -> list[dict]:
        project = self._project_for(root)
        if project.game_dir is None:
            return []
        return [{"label": label, "path": str(path)} for label, path in game_sync.pull_sources(project.game_dir)]

    def pull_compare(self, root: str, source: str) -> list[dict]:
        """Arquivos da pasta que diferem do projeto, com a origem de cada um (progresso por evento)."""
        project = self._project_for(root)
        progress = getattr(self, "_progress", None)
        return [_candidate(item) for item in game_sync.compare(project, Path(source), progress("pull") if progress else None)]

    def pull_apply(self, root: str, items: list[list[str]]) -> dict:
        """Traz (relativo, origem) para o projeto. `open_affected`: o XML aberto foi trocado."""
        project = self._project_for(root)
        pairs = [(str(relative), Path(source)) for relative, source in items]
        open_path = getattr(self, "_open_path", None) if project is getattr(self, "_project", None) else None
        affected = home.pull_affects_open_file(project.ui_dir, pairs, open_path)
        count = game_sync.pull(project, pairs)
        self._after_project_change(project)
        return {"count": count, "open_affected": affected}

    def game_backups(self) -> list[dict]:
        """Cópias que o último F5 guardou de arquivos da pasta UI editados fora (para o Puxar)."""
        project = getattr(self, "_project", None)
        if project is None:
            return []
        return [
            _candidate(game_sync.PullCandidate(relative, backup, not project.resolve(relative).exists(), game_sync.EDITED_OUTSIDE))
            for relative, backup in getattr(self, "_game_backups", [])
            if backup.is_file()
        ]

    # ---- limpar -------------------------------------------------------------------------
    def cleanup_scan(self, root: str) -> dict:
        """O que dá para limpar, com tamanhos (o plano fica guardado para aplicar)."""
        project = self._project_for(root)
        progress = getattr(self, "_progress", None)
        plan = cleanup.scan(project, progress=progress("cleanup") if progress else None)
        if not hasattr(self, "_cleanup_plans"):
            self._cleanup_plans: dict[str, cleanup.CleanupPlan] = {}
        self._cleanup_plans[str(project.root)] = plan
        size = cleanup.size_of
        ui_size = cleanup.folder_size(project.ui_dir)
        history_size = cleanup.folder_size(project.history_dir)
        versions_size = cleanup.folder_size(versions.versions_dir(project))
        return {
            "name": project.name,
            "days": cleanup.OLD_DAYS,
            "total": home.human_size(ui_size + history_size + versions_size),
            "ui": home.human_size(ui_size),
            "history": home.human_size(history_size),
            "versions": home.human_size(versions_size),
            "history_old": {"count": len(plan.history_old), "size": size(plan.history_old)},
            "history_all": {"count": len(plan.history_all), "size": size(plan.history_all)},
            "icons": {"count": len(plan.icons), "size": size(plan.icons), "left": plan.icons_left},
            "maps": {"count": len(plan.maps), "size": size(plan.maps), "left": plan.maps_left},
            "custom": {
                "count": len(plan.custom), "size": size(plan.custom),
                "folder": plan.custom_dir.name if plan.custom_dir is not None else "",
            },
        }

    def human_size(self, size: int) -> str:
        return home.human_size(int(size))

    def cleanup_apply(self, root: str, history: str | None, icons: bool, maps: bool, custom: bool) -> dict:
        project = self._project_for(root)
        plan = getattr(self, "_cleanup_plans", {}).pop(str(project.root), None)
        if plan is None:
            plan = cleanup.scan(project)
        result = cleanup.apply(
            project, plan, history=history if history in ("old", "all") else None,
            icons=bool(icons), maps=bool(maps), custom=bool(custom),
        )
        self._after_project_change(project)
        return {"removed": result.removed, "freed": home.human_size(result.freed)}

    # ---- UI oficial de referência -------------------------------------------------------
    def _official_game_dir(self) -> Path | None:
        game_dir = getattr(self, "_game_dir", None)
        return game_dir() if callable(game_dir) else None

    def official_status(self) -> dict:
        """Chip e diálogo: há lista do launcher, quantos oficiais estão guardados, UI no launcher."""
        game_dir = self._official_game_dir()
        if game_dir is None:
            return {"game_dir": None, "has_list": False, "ready": False, "cached": 0, "total": 0, "launcher_ui": ""}
        cached, total = game_updates.cached_count(game_dir)
        current = selected_ui(game_dir / "Launcher.ini")
        name = LAUNCHER_DEFAULT_UI if current.lower() in ("", "padrao") else current.split(":", 1)[-1]
        return {
            "game_dir": str(game_dir),
            "has_list": (game_dir / "GameDataFileList.txt").is_file(),
            "ready": game_updates.reference_ready(game_dir),
            "cached": cached,
            "total": total,
            "launcher_ui": name,
        }

    def official_snapshot(self) -> dict:
        """Guarda os XMLs oficiais que estão na pasta UI agora; devolve o status novo."""
        game_dir = self._official_game_dir()
        if game_dir is not None:
            game_updates.snapshot_official_ui(game_dir)
        return self.official_status()

    def official_scan(self) -> None:
        """Compara o projeto aberto com a UI oficial em segundo plano (evento "official_scan")."""
        project = getattr(self, "_project", None)
        if project is None or project.game_dir is None:
            return
        game_dir, root, base_bytes = project.game_dir, project.root, project.base_bytes

        def work() -> None:
            try:
                game_updates.snapshot_official_ui(game_dir)
                diffs, _unavailable = game_updates.scan(game_dir, project.resolve, base_bytes)
            except Exception:  # noqa: BLE001 - a comparação é só um aviso
                return
            current = getattr(self, "_project", None)
            if current is None or current.root != root:
                return
            self._official_diffs, self._official_root = diffs, root
            self._emit("official_scan", {"root": str(root), "diffs": {key: _diff(diff) for key, diff in diffs.items()}})

        threading.Thread(target=work, name="gf-ui-official-scan", daemon=True).start()

    def _official_key(self, path: Path) -> str:
        project = getattr(self, "_project", None)
        if project is not None and project.contains(path):
            return project.relative_key(path).lower()
        return path.name.lower()

    def official_controls(self, path: str) -> dict:
        """Controles do oficial que o XML não tem: novos da atualização e outros, com tipo/textura/posição.

        {"unavailable": True} sem cópia oficial; {"complete": True} se já tem todos.
        """
        target = Path(path)
        game_dir = self._official_game_dir()
        key = self._official_key(target)
        official = game_updates.official_text_for(game_dir, key) if game_dir is not None else None
        if official is None:
            return {"unavailable": True, "file": target.name}
        project = getattr(self, "_project", None)
        source = project.read_path(target) if project is not None else target
        current = source.read_bytes().decode(game_updates.UIDocument.encoding, "replace")
        missing = game_updates.missing_controls(current, official)
        if not missing:
            return {"complete": True, "file": target.name}
        diff = getattr(self, "_official_diffs", {}).get(key)
        new_ids = [window_id for window_id in missing if diff is not None and window_id in diff.new_ids]
        infos = game_updates.control_info(official, missing)
        return {
            "file": target.name,
            "new_ids": new_ids,
            "other_ids": [window_id for window_id in missing if window_id not in new_ids],
            "infos": {
                window_id: {"kind": info.kind, "texture": info.texture, "position": list(info.position)}
                for window_id, info in infos.items()
            },
        }

    # ---- resolver erro do jogo ---------------------------------------------------------
    def locate_game_error(self, text: str) -> dict:
        """Do texto do erro até o XML: {"error": "invalid"} ou cpp, ID e arquivos candidatos."""
        project = getattr(self, "_project", None)
        located = game_updates.locate_error(self._official_game_dir, project.resolve if project is not None else None, text)
        if located is None:
            return {"error": "invalid"}
        cpp, window_id, candidates = located
        if project is not None:
            folder: Path | None = project.ui_dir
        else:
            open_path = getattr(self, "_open_path", None)
            folder = open_path.parent if open_path is not None else None
        return {
            "cpp": cpp,
            "id": window_id,
            "candidates": candidates,
            "folder": str(folder) if folder is not None else None,
            "paths": {name: str(folder / name) for name in candidates} if folder is not None else {},
            "exists": {name: (project.resolve(name) if project is not None else folder / name).is_file() for name in candidates} if folder is not None else {},
        }

    # ---- textos -------------------------------------------------------------------------
    def game_text_id(self, path: str, window_id: str) -> int | None:
        """TextID do T_TextIndex que o jogo escreve neste controle (duplo clique)."""
        return game_texts.text_ids_for(Path(path).name).get(str(window_id))

    def texts_export_info(self) -> dict:
        project = getattr(self, "_project", None)
        manifest = getattr(self, "_manifest", None)
        if project is None or project.game_dir is None:
            return {"available": False, "has_edits": False, "disabled": False}
        edits = text_data.load_edits(project.root)
        return {
            "available": True,
            "has_edits": any(edits.values()),
            "disabled": bool(manifest is not None and manifest.is_disabled(remote_manifest.EXPORT_TEXTS)),
        }

    def texts_pick_export(self) -> str | None:
        project = getattr(self, "_project", None)
        if project is None:
            return None
        target = self._ask_path("save", Path.home() / "Documents", ("Arquivos .zip (*.zip)",), f"{project.custom_name}-textos.zip")
        if target is None:
            return None
        return str(target if target.suffix.lower() == ".zip" else target.with_name(target.name + ".zip"))

    def texts_export(self, target: str) -> dict:
        """Zip com os .ini editados de data/Translate. names vazio = nada encontrado no jogo."""
        project = getattr(self, "_project", None)
        if project is None or project.game_dir is None:
            raise ValueError("Sem projeto ou sem pasta do jogo.")
        names, warnings = text_data.export_texts_zip(project.game_dir, text_data.load_edits(project.root), Path(target))
        return {"path": target, "names": names, "warnings": warnings[:20]}

    def _ask_path(self, *args, **kwargs):  # ProjectsApi implementa
        return None


__all__ = ["MaintenanceApi"]
