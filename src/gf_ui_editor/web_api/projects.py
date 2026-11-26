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

from .. import __version__, desktop, element_tree, file_list, home, new_project, publishing, release_notes, remote_manifest, storage, textures
from ..preferences import UI_LANGUAGES, UI_MODES, MemoryStore, Preferences
from ..project import (
    CHANGES_TTL,
    Project,
    ProjectNameTaken,
    configured_game_dir,
    create_from_source,
    convert_to_light,
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
        # Lido uma vez ao abrir (startup); manifest_notices espera por ele.
        self._manifest_ready = threading.Event()
        # Diálogos nativos: por padrão os do pywebview; os testes trocam por respostas prontas.
        self._dialogs = dialogs
        # XML com alterações não salvas (o front avisa): fechar a janela pergunta antes.
        self._unsaved = False
        self._force_close = False

    def _attach_projects(self, window: Any) -> None:
        """Fechar a janela com alterações não salvas: cancela e pede ao front para perguntar."""
        window.events.closing += self._on_closing

    def _on_closing(self) -> bool:
        if self._unsaved and not self._force_close:
            # Fora da thread da janela: o evaluate_js esperaria por ela e travaria.
            threading.Thread(target=self._emit, args=("close_requested",), daemon=True).start()
            return False
        return True

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

    def _project_for_path(self, path: Path) -> Project | None:
        project = getattr(self, "_project", None)
        return project if project is not None and project.contains(path) else None

    def _project_info(self) -> dict | None:
        project = self._project
        if project is None:
            return None
        return {
            "root": str(project.root),
            "name": project.name,
            "custom_name": project.custom_name,
            "ui_dir": str(project.ui_dir),
            "light": project.light,
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
        return project.ui_dir / last if last and project.resolve(last).is_file() else None

    def convert_project_to_light(self) -> dict:
        project = self._require_project()
        backup = convert_to_light(project, self._progress("convert"))
        self._sizes.forget(project.root)
        return {"backup": str(backup) if backup is not None else None, "state": self.shell_state()}

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
            "publish_on_save": self._prefs.publish_on_save,
        }

    def startup(self) -> dict:
        """Como a clássica: o XML da linha de comando, senão o último projeto (com o último XML)."""
        if not self._manifest_ready.is_set():
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
        """Como a clássica: só com "Verificar ao abrir" ligado; sem internet, segue sem ele."""
        try:
            manifest = remote_manifest.fetch() if self._prefs.auto_update_check else None
        except Exception:  # noqa: BLE001 - sem internet o editor segue sem o manifesto
            manifest = None
        if manifest is not None:
            self._manifest = manifest
        self._manifest_ready.set()

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
                light=bool(form.get("light")),
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
            if project.read_path(focus).is_file():
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
        project = self._project_for_path(target)
        if not (project.read_path(target) if project is not None else target).is_file():
            raise FileNotFoundError(path)
        self._open_xml(target)
        return self.shell_state()

    def open_in_text_editor(self, path: str) -> str:
        target = Path(path)
        project = self._project_for_path(target)
        return desktop.open_in_text_editor(project.materialize(target) if project is not None else target)

    def text_editor_name(self) -> str:
        """Nome do editor de texto para o menu ("Notepad++" ou "Bloco de Notas")."""
        return desktop.text_editor_name()

    # ---- enviar para o jogo (F5) e exportar ------------------------------------------------
    def publish_info(self) -> dict:
        """O que a confirmação da primeira vez mostra."""
        project = self._require_project()
        if project.game_dir is None:
            raise ValueError("Projeto sem pasta do jogo.")
        diffs = getattr(self, "_official_diffs", {}) if getattr(self, "_official_root", None) == project.root else {}
        return {
            "confirmed": self._prefs.publish_confirmed,
            "custom_dir": str(project.game_dir / "UICustom" / project.custom_name),
            "custom_name": project.custom_name,
            # Arquivos sem os controles que a atualização do jogo trouxe (aviso antes do F5).
            "new_controls": publishing.pending_new_controls(diffs.values()),
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
        # Cópias dos arquivos da pasta UI editados fora (banner "Ver" depois do envio).
        self._game_backups = [(relative, backup) for relative, backup in result.game_backups]
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

    def pick_export_target(self) -> str | None:
        """Onde salvar o .zip (Documentos/<pasta de envio>.zip sugerido). None se cancelou."""
        project = self._require_project()
        target = self._ask_path("save", Path.home() / "Documents", ("UI do launcher (*.zip)",), f"{project.custom_name}.zip")
        if target is None:
            return None
        return str(target if target.suffix.lower() == ".zip" else target.with_name(target.name + ".zip"))

    def export_zip(self, target: str) -> dict:
        """Exportar .zip. {"empty": True} se nada difere do oficial; erro de disco sobe."""
        project = self._require_project()
        try:
            path = project.export_zip(Path(target), progress=self._progress("export"))
        except ValueError:
            return {"empty": True}
        count, skipped = getattr(project, "last_export", (0, 0))
        return {"path": str(path), "count": count, "skipped": skipped}

    # ---- documento aberto: avisos da casca --------------------------------------------------
    def set_unsaved(self, unsaved: bool) -> None:
        """O front avisa quando o XML aberto passa a ter (ou deixa de ter) alterações."""
        self._unsaved = bool(unsaved)

    def close_window(self) -> None:
        """Fecha de verdade (o usuário já respondeu salvar/descartar)."""
        self._force_close = True
        window = getattr(self, "_window", None)
        if window is not None:
            window.destroy()

    # ---- árvore de elementos ---------------------------------------------------------------
    def element_tree(self, path: str, kinds: list[str]) -> list[dict]:
        """Rótulo do jogo, WindowText e texto do filtro de cada elemento do XML."""
        return element_tree.tree_rows(Path(path), list(kinds))

    def tree_columns(self) -> list[str]:
        return element_tree.hidden_columns(self._prefs.tree_hidden_columns)

    def set_tree_columns(self, hidden: list[str]) -> list[str]:
        columns = element_tree.hidden_columns([str(column) for column in hidden])
        self._prefs.tree_hidden_columns = columns
        return columns

    # ---- trocar a textura do controle ---------------------------------------------------------
    def texture_names(self, xml_path: str) -> list[str]:
        """Texturas da pasta da UI do XML ("Usar outro .dds desta UI…")."""
        path = Path(xml_path)
        return textures.ui_texture_names(path.parent, self._project_for_path(path))

    def texture_copy_info(self, xml_path: str, current: str) -> dict:
        path = Path(xml_path)
        return {
            "exists": textures.find_texture(path.parent, current, self._project_for_path(path)) is not None,
            "suggestion": textures.copy_suggestion(current),
        }

    def copy_texture(self, xml_path: str, current: str, name: str) -> dict:
        """Cópia editável de `current`. {"error": "exists"} se o nome já existe."""
        try:
            path = Path(xml_path)
            target = textures.copy_for_edit(path.parent, current, name, self._project_for_path(path))
        except FileExistsError as exc:
            return {"error": "exists", "name": str(exc.args[0])}
        self._refresh_project_files()
        return {"name": target.name}

    def pick_texture(self, xml_path: str) -> dict | None:
        """Trazer .dds de outra pasta: o arquivo escolhido e se substitui um da UI."""
        chosen = self._ask_path("open", None, ("Texturas (*.dds;*.tga)",))
        if chosen is None:
            return None
        path = Path(xml_path)
        target, replacing = textures.bring_target(path.parent, chosen, self._project_for_path(path))
        return {"path": str(chosen), "name": target.name, "replacing": replacing}

    def bring_texture(self, xml_path: str, source: str) -> dict:
        project = self._project if self._project is not None and self._project.contains(Path(xml_path)) else None
        target = textures.bring_texture(project, Path(xml_path).parent, Path(source))
        self._refresh_project_files()
        return {"name": target.name}

    def _refresh_project_files(self) -> None:
        if self._project is not None:
            self._project.files(refresh=True)

    # ---- menu de contexto da lista de arquivos ---------------------------------------------
    def file_history(self, path: str) -> dict:
        """Backups (mais recente primeiro, com a data do nome) e o original, se houver."""
        backups, original = file_list.history_entries(self._project, Path(path))
        entries = []
        for backup in backups:
            stamp = file_list.backup_stamp(backup)
            entries.append({"path": str(backup), "name": backup.name, "stamp": stamp.isoformat() if stamp else None})
        folder = backups[0].parent if backups else (original.parent if original is not None else None)
        return {
            "backups": entries,
            "original": str(original) if original is not None else None,
            "folder": str(folder) if folder is not None else None,
            "in_project": self._project is not None and self._project.contains(Path(path)),
        }

    def rename_check(self, path: str, name: str) -> dict:
        """Antes de renomear: nome inválido, destino, se substitui outro e quantos XMLs usam a textura."""
        if file_list.has_invalid_chars(name):
            return {"invalid": True}
        source = Path(path)
        target, replacing = file_list.rename_target(source, name.strip(), self._require_project())
        users = len(file_list.xml_using_texture(self._require_project(), source.name)) if file_list.is_texture(source) else 0
        return {"target": str(target), "name": target.name, "replacing": replacing, "texture_users": users}

    def rename_file(self, path: str, name: str) -> dict:
        project = self._require_project()
        target, _replacing = file_list.rename_target(Path(path), name.strip())
        new_path, _backup = project.rename_file(Path(path), target.name)
        project.files(refresh=True)
        if self._open_path is not None and home.is_same_root(self._open_path, Path(path)):
            self._open_path = None
        return {"path": str(new_path), "name": new_path.name}

    def retarget_texture(self, old: str, new: str) -> int:
        """Troca BGmap="old" por "new" nos XMLs do projeto que ainda usam o nome antigo."""
        project = self._require_project()
        users = file_list.xml_using_texture(project, old)
        file_list.retarget_texture(project, users, old, new)
        return len(users)

    def delete_file_info(self, path: str) -> dict:
        warning = file_list.delete_warning(self._require_project(), Path(path))
        return {"official": warning.official, "texture_users": warning.texture_users}

    def delete_file(self, path: str) -> None:
        project = self._require_project()
        project.delete_file(Path(path))
        project.files(refresh=True)
        if self._open_path is not None and home.is_same_root(self._open_path, Path(path)):
            self._open_path = None

    def restore_preview(self, path: str, source: str, current_label: str, restored_label: str) -> str:
        """Diff entre o arquivo e a versão a restaurar ('' se iguais). Os rótulos vêm traduzidos."""
        target = Path(path)
        project = self._project_for_path(target)
        return file_list.restore_diff(project.read_path(target) if project is not None else target, Path(source), current_label, restored_label)

    def restore_file(self, path: str, source: str) -> None:
        file_list.restore_file(self._project, Path(path), Path(source))
        if self._project is not None:
            self._project.invalidate_changes()
