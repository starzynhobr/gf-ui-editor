"""Ponte: casca, tela inicial, projetos, lista de arquivos, preferências (dono: bloco 1, casca).

Só chama os serviços sem Qt (`project`, `home`, `new_project`, `file_list`, `publishing`,
`preferences`, `desktop`…). Guarda o estado da sessão (projeto aberto, XML aberto) e
traduz exceções conhecidas em respostas que a interface sabe mostrar. Textos visíveis
ficam no front (i18n); aqui só vão chaves e dados.
"""

from __future__ import annotations

import json
from pathlib import Path
import threading
import time
from typing import Any, Callable
import zipfile

from .. import __version__, desktop, file_list, home, new_project, publishing, release_notes, remote_manifest, storage
from ..preferences import UI_LANGUAGES, UI_MODES, MemoryStore, Preferences
from ..project import (
    CHANGES_TTL,
    Project,
    ProjectNameTaken,
    configured_game_dir,
    create_from_source,
    delete_project,
    duplicate_project,
    list_projects,
    owned_custom_folder,
    rename_project,
)

PROGRESS_INTERVAL = 0.08  # segundos entre dois eventos de progresso (a cópia passa por ~18 mil arquivos)


class ProjectsApi:
    """Métodos públicos viram window.pywebview.api.<nome>. Só tipos JSON."""

    # ---- infraestrutura (chamada pelo web_shell) ---------------------------------------
    def _setup_projects(
        self,
        prefs: Preferences | None = None,
        default_ui_directory: Path | None = None,
        startup_xml: Path | None = None,
        dialogs: Any = None,
    ) -> None:
        self._prefs = prefs or Preferences(MemoryStore())
        self._default_ui_directory = default_ui_directory or Path(r"C:\Violet Games\Grand Fantasia Violet\UI")
        self._startup_xml = startup_xml
        self._project: Project | None = None
        self._open_path: Path | None = None
        self._loose_dir: Path | None = None
        self._sizes = home.SizeCache()
        self._manifest = remote_manifest.Manifest()
        # Diálogos nativos: por padrão os do pywebview; os testes trocam por respostas prontas.
        self._dialogs = dialogs

    def _emit(self, event: str, payload: Any = None) -> None:  # o WebApi sobrescreve
        pass

    def _progress(self, label: str) -> Callable[[int, int], None]:
        """Progresso como evento, no máximo a cada PROGRESS_INTERVAL (e sempre no último)."""
        last = [0.0]

        def report(done: int, total: int) -> None:
            now = time.monotonic()
            if done >= total or now - last[0] >= PROGRESS_INTERVAL:
                last[0] = now
                self._emit("progress", {"label": label, "done": done, "total": total})

        return report

    def _ask_path(self, kind: str, directory: Path | None = None, file_types: tuple[str, ...] = (), save_name: str = "") -> Path | None:
        if self._dialogs is not None:
            answer = self._dialogs(kind, directory, file_types, save_name)
            return Path(answer) if answer else None
        window = getattr(self, "_window", None)
        if window is None:
            return None
        import webview

        dialog = {"folder": webview.FileDialog.FOLDER, "open": webview.FileDialog.OPEN, "save": webview.FileDialog.SAVE}[kind]
        result = window.create_file_dialog(
            dialog, directory=str(directory) if directory is not None and directory.exists() else "",
            file_types=file_types, save_filename=save_name,
        )
        if not result:
            return None
        chosen = result if isinstance(result, str) else result[0]
        return Path(chosen) if chosen else None

    def _projects_root(self) -> Path:
        return new_project.projects_root()

    def _game_dir(self) -> Path | None:
        if self._project is not None and self._project.game_dir is not None:
            return self._project.game_dir
        return configured_game_dir(self._prefs.game_dir, self._default_ui_directory)

    def _is_current(self, root: Path | str) -> bool:
        return home.is_same_root(self._project.root if self._project is not None else None, Path(root))

    def _require_project(self) -> Project:
        if self._project is None:
            raise RuntimeError("Nenhum projeto aberto.")
        return self._project

    def _project_info(self) -> dict | None:
        project = self._project
        if project is None:
            return None
        return {
            "root": str(project.root),
            "name": project.name,
            "custom_name": project.custom_name,
            "ui_dir": str(project.ui_dir),
            "game_dir": str(project.game_dir) if project.game_dir is not None else None,
            "publish_dir": str(project.game_dir / "UICustom" / project.custom_name) if project.game_dir is not None else None,
        }

    def _pending(self) -> int:
        if self._project is None:
            return 0
        try:
            return len(self._project.unpublished_files())
        except OSError:
            return 0

    def _load_project(self, root: Path) -> None:
        project = Project.load(root)
        project.changes_ttl = CHANGES_TTL  # a tela pergunta várias vezes seguidas
        self._project = project
        self._loose_dir = None
        if self._open_path is not None and not project.contains(self._open_path):
            self._open_path = None
        self._prefs.last_project = str(root)

    def _last_file(self) -> Path | None:
        project = self._project
        if project is None:
            return None
        last = self._prefs.last_file(project.custom_name)
        return project.ui_dir / last if last and (project.ui_dir / last).is_file() else None

    # ---- casca ---------------------------------------------------------------------------
    def shell_state(self) -> dict:
        """Projeto e XML abertos, contador do F5 e preferências que a casca usa."""
        return {
            "version": __version__,
            "language": self._prefs.language if self._prefs.language in UI_LANGUAGES else "pt_BR",
            "ui_mode": self._prefs.ui_mode if self._prefs.ui_mode in UI_MODES else "classic",
            "project": self._project_info(),
            "open_path": str(self._open_path) if self._open_path is not None else None,
            "loose_dir": str(self._loose_dir) if self._loose_dir is not None else None,
            "pending": self._pending(),
            "publish_confirmed": self._prefs.publish_confirmed,
        }

    def startup(self) -> dict:
        """Como a clássica: o XML da linha de comando, senão o último projeto (com o último XML)."""
        threading.Thread(target=self._fetch_manifest, name="gf-ui-manifest", daemon=True).start()
        view = "home"
        if self._startup_xml is not None and self._startup_xml.is_file():
            self._open_loose(self._startup_xml)
            view = "workspace"
        else:
            last = self._prefs.last_project
            if last and storage.is_project(Path(last)):
                try:
                    self._load_project(Path(last))
                    self._open_path = self._last_file()
                    view = "workspace"
                except (OSError, ValueError):
                    self._project = None
        return {"view": view, **self.shell_state()}

    def _fetch_manifest(self) -> None:
        try:
            manifest = remote_manifest.fetch()
        except Exception:  # noqa: BLE001 - sem internet o editor segue sem o manifesto
            manifest = None
        if manifest is not None:
            self._manifest = manifest

    def set_language(self, language: str) -> dict:
        if language not in UI_LANGUAGES:
            raise ValueError(f"Idioma não suportado: {language}")
        self._prefs.language = language
        if hasattr(self, "_language"):
            self._language = language
        return self.shell_state()

    def set_ui_mode(self, mode: str) -> str:
        """Interface ao abrir na próxima vez (clássica ou nova)."""
        if mode not in UI_MODES:
            raise ValueError(f"Interface desconhecida: {mode}")
        self._prefs.ui_mode = mode
        return mode

    def open_folder(self, path: str) -> None:
        desktop.open_path(Path(path))

    def open_url(self, url: str) -> None:
        if not url.startswith("https://"):
            raise ValueError("Só links https.")
        desktop.open_url(url)

    # ---- tela inicial --------------------------------------------------------------------
    def home_data(self) -> dict:
        """Tudo da tela inicial; os tamanhos chegam depois pelo evento "project_size"."""
        roots = list_projects(self._projects_root())
        rows = home.project_rows(roots, self._project.root if self._project is not None else None)
        for row in rows:
            size = self._sizes.get(row["root"], row["edited"])
            row["size"] = home.human_size(size) if size is not None else None
        pending = self._sizes.pending(roots)
        if pending:
            def work() -> None:
                self._sizes.compute(
                    pending, lambda key, size: self._emit("project_size", {"root": key, "size": home.human_size(size)})
                )

            threading.Thread(target=work, name="gf-ui-project-sizes", daemon=True).start()
        project = self._project
        continue_card = home.continue_summary(project, self._prefs.last_file(project.custom_name)) if project is not None else None
        language = self._prefs.language
        return {
            "projects": rows,
            "continue": continue_card,
            "version": __version__,
            "news": home.news_titles(release_notes.bundled(), language),
            "how_to_url": home.how_to_url(language),
            "projects_root": str(self._projects_root()),
        }

    def whats_new(self) -> dict:
        notes = release_notes.bundled()
        sections = notes.for_language(self._prefs.language) if notes is not None else {}
        return {
            "version": notes.version if notes is not None else __version__,
            "date": notes.date if notes is not None else "",
            "sections": {name: [list(entry) for entry in sections.get(name, [])] for name in release_notes.SECTIONS},
        }

    def go_home(self) -> dict:
        """Tela inicial: fecha o XML aberto (o projeto continua aberto)."""
        self._open_path = None
        return self.shell_state()

    def open_project(self, root: str) -> dict:
        """Abre o projeto e o último XML dele (como a clássica). Erro se não for um projeto."""
        path = Path(root)
        if not storage.is_project(path):
            raise ValueError("not_a_project")
        if self._is_current(path) and self._project is not None:
            if self._open_path is None:
                self._open_path = self._last_file()
            return self.shell_state()
        self._load_project(path)
        self._open_path = self._last_file()
        return self.shell_state()

    def browse_project(self) -> dict | None:
        """Procurar a pasta de um projeto. None se cancelou; {"error": "not_a_project"} se não é."""
        root = self._projects_root()
        folder = self._ask_path("folder", root if root.exists() else Path.home())
        if folder is None:
            return None
        if not storage.is_project(folder):
            return {"error": "not_a_project"}
        return self.open_project(str(folder))

    def duplicate_project(self, root: str, name: str) -> dict:
        try:
            duplicate_project(Path(root), name)
        except ProjectNameTaken:
            return {"error": "taken", "name": name.strip()}
        return {"name": name.strip()}

    def rename_project(self, root: str, name: str) -> dict:
        current = self._is_current(root)
        old_custom = self._project.custom_name if current and self._project is not None else None
        try:
            new_root = rename_project(Path(root), name)
        except ProjectNameTaken:
            return {"error": "taken", "name": name.strip()}
        except OSError as exc:
            return {"error": "busy", "detail": str(exc)}
        if current:
            self._load_project(new_root)
            if old_custom is not None:
                self._prefs.move_last_file(old_custom, self._project.custom_name)
            if self._open_path is not None:
                self._open_path = None
        return {"name": name.strip(), "state": self.shell_state()}

    def delete_info(self, roots: list[str]) -> dict:
        """Nomes e pastas UICustom só deles, para a pergunta antes de excluir."""
        projects = []
        owned = []
        for root in roots:
            try:
                project = Project.load(Path(root))
            except (OSError, ValueError):
                continue
            projects.append({"root": str(project.root), "name": project.name})
            folder = owned_custom_folder(project)
            if folder is not None:
                owned.append(f"UICustom/{folder.name}")
            storage.close_all()
        return {"projects": projects, "owned": owned}

    def delete_projects(self, roots: list[str], remove_custom: bool) -> dict:
        """Manda para a Lixeira. Devolve os nomes que falharam (arquivo em uso)."""
        if any(self._is_current(root) for root in roots):
            self._project = None
            self._open_path = None
            self._prefs.remove("last_project")
        failed = []
        for root in roots:
            path = Path(root)
            try:
                title = storage.peek_project(path)[0] or path.name
                delete_project(path, desktop.move_to_trash, remove_custom=remove_custom)
            except OSError:
                failed.append(title)
            self._sizes.forget(path)
        return {"failed": failed, "state": self.shell_state()}

    # ---- novo projeto ------------------------------------------------------------------
    def new_project_form(self, game_dir: str | None = None, loose_dir: str | None = None) -> dict:
        """Pasta do jogo, origens possíveis e XMLs soltos que podem entrar por cima."""
        directory = new_project.chosen_game_dir(Path(game_dir)) if game_dir else self._game_dir()
        sources = new_project.sources(directory)
        loose = Path(loose_dir) if loose_dir else None
        loose_files = new_project.loose_files(loose, sources)
        default_source = next(
            (str(source.path) for source in sources if loose is not None and home.is_same_root(loose, source.path)),
            str(sources[0].path) if sources else None,
        )
        return {
            "game_dir": str(directory) if directory is not None else None,
            "game_dir_warning": new_project.game_dir_warning(directory),
            "sources": [{"label": source.label, "path": str(source.path)} for source in sources],
            "default_source": default_source,
            "loose_dir": str(loose) if loose is not None else None,
            "loose_files": [path.name for path in loose_files],
            "projects_root": str(self._projects_root()),
        }

    def new_project_targets(self, name: str, source_label: str, game_dir: str | None) -> list[dict]:
        """Pastas de envio possíveis, cada uma com o aviso que vale para ela."""
        directory = Path(game_dir) if game_dir else None
        targets = []
        for value, folder in new_project.publish_targets(name, source_label):
            warning = new_project.publish_warning(value, name, directory)
            targets.append({
                "value": value, "folder": folder, "warning": [warning[0], warning[1]] if warning is not None else None,
            })
        return targets

    def pick_game_dir(self, current: str | None = None) -> str | None:
        chosen = self._ask_path("folder", Path(current) if current else None)
        return str(new_project.chosen_game_dir(chosen)) if chosen is not None else None

    def pick_source(self, kind: str) -> dict | None:
        """"Outra pasta…" ou "Arquivo .zip…": caminho e nome sugerido."""
        chosen = self._ask_path("folder") if kind == "folder" else self._ask_path("open", file_types=("Arquivos .zip (*.zip)",))
        if chosen is None:
            return None
        return {"path": str(chosen), "suggested_name": new_project.suggested_name("", picked=chosen)}

    def create_project(self, form: dict) -> dict:
        """Cria e abre o projeto. {"error": "exists"} se a pasta já existe; outros erros sobem."""
        name = str(form.get("name", "")).strip()
        if not name:
            raise ValueError("Dê um nome ao projeto")
        game_dir = Path(form["game_dir"]) if form.get("game_dir") else None
        if game_dir is not None:
            self._prefs.game_dir = str(game_dir)
        loose_dir = Path(form["loose_dir"]) if form.get("loose_dir") else None
        loose = (
            new_project.loose_files(loose_dir, new_project.sources(game_dir))
            if loose_dir is not None and form.get("include_loose", True) else []
        )
        focus = Path(form["focus"]) if form.get("focus") else None
        try:
            project = create_from_source(
                name, Path(form["source"]), game_dir, projects_root=self._projects_root(),
                progress=self._progress("create"), include_assets=bool(form.get("include_assets")),
                publish_folder=str(form.get("publish_folder") or ""),
            )
        except FileExistsError as exc:
            return {"error": "exists", "path": str(exc.args[0])}
        except zipfile.BadZipFile as exc:
            raise ValueError(str(exc)) from exc
        focus = project.import_loose_files(loose, focus)
        self._open_path = None
        self._load_project(project.root)
        self._open_path = self._last_file()
        if focus is not None:
            if not project.contains(focus):
                focus = project.import_target(focus)
            if focus.is_file():
                self._open_xml(focus)
        return {"count": len(project.base_hashes), "state": self.shell_state()}

    # ---- XML solto -----------------------------------------------------------------------
    def pick_xml(self) -> dict | None:
        """Abrir um XML solto: caminho escolhido e se é para oferecer um projeto antes."""
        start = self._default_ui_directory if self._default_ui_directory.exists() else Path.home()
        chosen = self._ask_path("open", start, ("XML (*.xml)", "Todos os arquivos (*.*)"))
        if chosen is None:
            return None
        in_project = self._project is not None and self._project.contains(chosen)
        return {"path": str(chosen), "offer_project": not in_project and self._prefs.offer_project_on_open}

    def set_offer_project(self, enabled: bool) -> None:
        self._prefs.offer_project_on_open = bool(enabled)

    def _open_loose(self, path: Path) -> None:
        if self._project is not None and self._project.contains(path):
            self._open_xml(path)
            return
        self._project = None
        self._loose_dir = path.parent
        self._open_path = path

    def open_loose(self, path: str) -> dict:
        self._open_loose(Path(path))
        return self.shell_state()

    # ---- lista de arquivos ---------------------------------------------------------------
    def _files_directory(self) -> Path | None:
        if self._project is not None:
            return self._project.ui_dir
        return self._loose_dir

    def file_list(self, mode: str = "xml") -> dict:
        """Arquivos XML ou Texturas: arquivos (relativos), alterados, seções na ordem salva."""
        directory = self._files_directory()
        project = self._project
        if project is not None:
            listing = file_list.project_listing(project)
        else:
            listing = file_list.loose_listing(directory)
        layers = set(project.reference_layers) if project is not None else set()
        payload = file_list.sections_payload(
            listing, mode, layers, self._prefs.files_section_order, self._prefs.files_section_heights
        )
        payload["directory"] = str(directory) if directory is not None else None
        payload["in_project"] = project is not None
        return payload

    def set_section_order(self, order: list[str]) -> list[str]:
        if not file_list.is_valid_section_order(order):
            raise ValueError(f"Ordem inválida: {order}")
        self._prefs.files_section_order = ",".join(order)
        return order

    def move_section(self, kind: str, step: int, visible: list[str]) -> list[str]:
        """Sobe (-1) ou desce (+1) a seção entre as visíveis; devolve a ordem (igual se não deu)."""
        order = file_list.parse_section_order(self._prefs.files_section_order)
        moved = file_list.order_after_move(order, visible, kind, step)
        if moved is None:
            return order
        return self.set_section_order(moved)

    def set_section_heights(self, heights: dict) -> dict:
        saved = file_list.parse_section_heights(self._prefs.files_section_heights)
        saved.update({str(kind): int(value) for kind, value in heights.items() if kind in file_list.FILE_SECTIONS})
        self._prefs.files_section_heights = json.dumps(saved)
        return saved

    def _open_xml(self, path: Path) -> None:
        self._open_path = path
        project = self._project
        if project is not None and project.contains(path):
            self._prefs.set_last_file(project.custom_name, project.relative_key(path))

    def open_xml(self, path: str) -> dict:
        """Abre um XML da lista (o canvas recebe o caminho). Lembra o último do projeto."""
        target = Path(path)
        if not target.is_file():
            raise FileNotFoundError(path)
        self._open_xml(target)
        return self.shell_state()

    def open_in_text_editor(self, path: str) -> str:
        return desktop.open_in_text_editor(Path(path))

    # ---- enviar para o jogo (F5) e exportar ------------------------------------------------
    def publish_info(self) -> dict:
        """O que a confirmação da primeira vez mostra."""
        project = self._require_project()
        if project.game_dir is None:
            raise ValueError("Projeto sem pasta do jogo.")
        return {
            "confirmed": self._prefs.publish_confirmed,
            "custom_dir": str(project.game_dir / "UICustom" / project.custom_name),
            "custom_name": project.custom_name,
        }

    def confirm_publish(self) -> None:
        self._prefs.publish_confirmed = True

    def publish(self) -> dict:
        """Envia a UI e os textos. Erro de disco (OSError) vira rejeição no front."""
        project = self._require_project()
        outcome = publishing.publish_project(
            project, self._manifest.is_disabled(remote_manifest.PUBLISH_TEXTS), self._progress("publish")
        )
        result, texts = outcome.result, outcome.texts
        return {
            "copied": result.copied_to_ui,
            "texts_changed": texts.changed,
            "texts_blocked": texts.blocked,
            "text_warnings": texts.warnings[:20],
            "game_backups": len(result.game_backups),
            "select_in_launcher": publishing.needs_launcher_selection(result, project.custom_name),
            "custom_name": project.custom_name,
            "pending": self._pending(),
        }

    def export_zip(self) -> dict | None:
        """Exportar .zip: pergunta onde salvar. None se cancelou; {"empty": True} se nada difere do oficial."""
        project = self._require_project()
        default = Path.home() / "Documents"
        target = self._ask_path("save", default, ("UI do launcher (*.zip)",), f"{project.custom_name}.zip")
        if target is None:
            return None
        if target.suffix.lower() != ".zip":
            target = target.with_name(target.name + ".zip")
        try:
            path = project.export_zip(target, progress=self._progress("export"))
        except ValueError:
            return {"empty": True}
        count, skipped = getattr(project, "last_export", (0, 0))
        return {"path": str(path), "count": count, "skipped": skipped}

