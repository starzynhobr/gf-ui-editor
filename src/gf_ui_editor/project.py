"""Projetos de UI: cópia de trabalho fora da pasta do jogo, histórico e publicação.

Um projeto é uma pasta com:

- `project.db` (SQLite, ver storage.py): nome, pasta do jogo, camadas, hashes dos
  arquivos na criação e textos editados. Projetos antigos em `project.json` são
  importados na primeira abertura;
- `ui/`: os arquivos da interface que estão sendo editados;
- `.history/`: backups automáticos de cada salvamento.

O launcher novo extrai cada UI importada em `<jogo>/UICustom/<nome>/` e, ao clicar
em Jogar, copia a UI escolhida (`UI=`/`UIAplicada=` no `Launcher.ini`) por cima de
`<jogo>/UI/`. "Testar no jogo" reproduz esse fluxo sem passar pelo .zip.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import os
import time
from pathlib import Path
import re
import shutil
import tempfile
import zipfile

from . import gamedata, storage
from .game_layout import normalize_game_dir

PROJECTS_ROOT = Path.home() / "Documents" / "GF UI Projects"
CHANGES_TTL = 2.0
ORIGINAL_NAME = "original"
HISTORY_LIMIT = 20

# Recebe (feitos, total) durante operações longas.
Progress = Callable[[int, int], None] | None

# Cópias de segurança deixadas na pasta da UI pelo editor ou à mão.
_BACKUP_PATTERNS = (
    re.compile(r"\.before-", re.IGNORECASE),
    re.compile(r" - c[oó]pia", re.IGNORECASE),
    re.compile(r"[_.](old|bak|bac|backup|original)(\.|$)", re.IGNORECASE),
    re.compile(r"\.(bak|tmp)$", re.IGNORECASE),
    re.compile(r"\.gf-ui-editor\.tmp$", re.IGNORECASE),
)


# Pastas de recursos do jogo (ícones de itens, skills, telas de carregamento):
# ~18 mil arquivos. Ficam fora do projeto, a menos que ele as inclua de propósito.
GAME_ASSET_FOLDERS = {"itemicon", "skillicon", "uiicon", "loadingframe", "loading_705", "original", "dm"}
# Minimapas e mapas do mundo (~163 MB): o jogo os carrega pelo código, nenhum XML aponta para eles
# e o editor só lê texturas da raiz da UI. Projetos novos não os copiam (a pasta UI do jogo já
# tem); projetos antigos que os têm continuam listando, e "Limpar projeto" tira os oficiais.
MAP_FOLDER = "map"


def is_backup_file(name: str) -> bool:
    return any(pattern.search(name) for pattern in _BACKUP_PATTERNS)


def safe_name(name: str) -> str:
    """Nome usado na pasta do projeto, no UICustom e no .zip."""
    cleaned = re.sub(r"[^\w\- ]+", "", name, flags=re.UNICODE).strip().replace(" ", "-")
    return cleaned or "UI-Projeto"


def _hash(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def _ui_files(directory: Path, include_assets: bool = False) -> list[Path]:
    """Arquivos da interface (relativos), sem backups nem arquivos ocultos.

    Usa os.walk e poda as pastas excluídas sem entrar nelas: com os ícones do
    jogo presentes, a varredura com pathlib levava segundos.
    """
    files: list[str] = []
    root = str(directory)
    for current, folders, names in os.walk(root):
        relative_dir = os.path.relpath(current, root)
        top_level = relative_dir == "."
        folders[:] = [
            folder for folder in folders
            if not folder.startswith(".")
            and (include_assets or not top_level or folder.lower() not in GAME_ASSET_FOLDERS)
        ]
        for name in names:
            if name.startswith(".") or is_backup_file(name):
                continue
            files.append(name if top_level else f"{relative_dir.replace(os.sep, '/')}/{name}")
    return [Path(item) for item in sorted(files, key=str.lower)]


@dataclass
class PublishResult:
    custom_dir: Path
    copied_to_ui: int
    launcher_updated: bool
    # Arquivos iguais ao oficial que ficaram fora de UICustom (o launcher completa com a pasta UI).
    skipped_official: int = 0
    # UI que estava selecionada no launcher antes de publicar (ex.: "custom:UI-Hero").
    previous_selection: str = ""
    # Launcher aberto: ele guarda a seleção na memória e pode reaplicar a UI antiga.
    launcher_running: bool = False
    # Arquivos da pasta UI editados fora do editor que o F5 substituiu: (relativo, cópia no .history).
    game_backups: list[tuple[str, Path]] = field(default_factory=list)


@dataclass
class Project:
    root: Path
    name: str
    game_dir: Path | None
    base_hashes: dict[str, str] = field(default_factory=dict)
    include_assets: bool = False
    # Escolha manual da posição da raiz no preview, por arquivo ("xml"/"center").
    root_modes: dict[str, str] = field(default_factory=dict)
    # Pasta já existente de UICustom adotada como destino (nome exato). Nela o
    # F5 só adiciona e atualiza arquivos; nunca apaga o que o usuário tem lá.
    publish_folder: str = ""
    # XMLs mostrados como camadas de referência no Preview do jogo (só para ver).
    reference_layers: list[str] = field(default_factory=list)
    # (tamanho, mtime) -> hash, para não reler arquivos que não mudaram.
    _hash_cache: dict[str, tuple[int, int, str]] = field(default_factory=dict, repr=False)
    _files: list[Path] | None = field(default=None, repr=False)
    changes_ttl: float = field(default=0.0, repr=False)
    _changes_memo: tuple[float, frozenset[str]] | None = field(default=None, repr=False)
    _unpublished_memo: tuple[float, frozenset[str]] | None = field(default=None, repr=False)

    @property
    def ui_dir(self) -> Path:
        return self.root / "ui"

    @property
    def history_dir(self) -> Path:
        return self.root / ".history"

    @property
    def custom_name(self) -> str:
        """Pasta de `UICustom` onde o projeto é publicado."""
        return self.publish_folder or safe_name(self.name)

    # ---- criação e leitura -------------------------------------------------
    @classmethod
    def create(
        cls,
        name: str,
        source_dir: Path,
        game_dir: Path | None,
        projects_root: Path = PROJECTS_ROOT,
        progress: Progress = None,
        include_assets: bool = False,
        publish_folder: str = "",
    ) -> "Project":
        root = projects_root / safe_name(name)
        if root.exists():
            raise FileExistsError(root)
        ui_dir = root / "ui"
        hashes: dict[str, str] = {}
        files = _ui_files(source_dir, include_assets)
        if not include_assets:
            files = [relative for relative in files if relative.parts[0].lower() != MAP_FOLDER or len(relative.parts) == 1]
        for done, relative in enumerate(files, 1):
            target = ui_dir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_dir / relative, target)
            hashes[relative.as_posix()] = _hash(target)
            if progress is not None:
                progress(done, len(files))
        project = cls(root, name, game_dir, hashes, include_assets, publish_folder=publish_folder)
        for key, digest in hashes.items():
            stat = (ui_dir / key).stat()
            project._hash_cache[key] = (stat.st_size, stat.st_mtime_ns, digest)
        project.save_manifest()
        store = storage.ProjectStore(root)
        store.save_base_hashes(hashes)
        store.save_file_hashes(project._hash_cache)
        return project

    @classmethod
    def load(cls, root: Path) -> "Project":
        storage.migrate_project_json(root)
        if not (root / storage.PROJECT_DB).is_file():
            raise FileNotFoundError(root / storage.PROJECT_DB)
        store = storage.ProjectStore(root)
        settings = store.settings()
        game_dir = settings.get("game_dir")
        return cls(
            root,
            str(settings.get("name") or root.name),
            Path(str(game_dir)) if game_dir else None,
            store.base_hashes(),
            bool(settings.get("include_assets", False)),
            store.root_modes(),
            str(settings.get("publish_folder") or ""),
            store.reference_layers(),
        )

    def save_manifest(self) -> None:
        """Grava as configurações do projeto (nome, pasta do jogo, camadas, modos)."""
        self.root.mkdir(parents=True, exist_ok=True)
        storage.ProjectStore(self.root).save_settings(
            {
                "name": self.name,
                "game_dir": str(self.game_dir) if self.game_dir else None,
                "include_assets": self.include_assets,
                "publish_folder": self.publish_folder,
            },
            self.root_modes,
            self.reference_layers,
        )

    # ---- estado ------------------------------------------------------------
    def files(self, refresh: bool = False) -> list[Path]:
        if refresh:
            self.invalidate_changes()
        """Lista em cache; `refresh=True` relê a pasta (arquivos criados/apagados fora)."""
        if refresh or self._files is None:
            self._files = _ui_files(self.ui_dir, self.include_assets)
        return self._files

    def invalidate_changes(self) -> None:
        """Esquece o resultado guardado de modified_files/unpublished_files (algo foi gravado)."""
        self._changes_memo = None
        self._unpublished_memo = None

    def modified_files(self) -> set[str]:
        """Arquivos alterados ou criados desde a criação do projeto.

        Olhar os ~700 arquivos custa caro e a tela pergunta várias vezes seguidas: o
        resultado vale por `changes_ttl` segundos (o app usa CHANGES_TTL; 0 = sempre exato)
        ou até invalidate_changes().
        """
        if self._changes_memo is not None and time.monotonic() - self._changes_memo[0] < self.changes_ttl:
            return set(self._changes_memo[1])
        changed = self._compute_modified_files()
        self._changes_memo = (time.monotonic(), frozenset(changed))
        return changed

    def _compute_modified_files(self) -> set[str]:
        if not self._hash_cache:
            self._hash_cache = storage.ProjectStore(self.root).file_hashes()
        before = dict(self._hash_cache)
        changed: set[str] = set()
        for relative in self.files():
            key = relative.as_posix()
            if self.base_hashes.get(key) != self._cached_hash(relative):
                changed.add(key)
        updated = {key: value for key, value in self._hash_cache.items() if before.get(key) != value}
        if updated:
            storage.ProjectStore(self.root).save_file_hashes(updated)
        return changed

    def _cached_hash(self, relative: Path) -> str:
        path = self.ui_dir / relative
        stat = os.stat(path)
        key = relative.as_posix()
        cached = self._hash_cache.get(key)
        if cached is not None and cached[:2] == (stat.st_size, stat.st_mtime_ns):
            return cached[2]
        digest = _hash(path)
        self._hash_cache[key] = (stat.st_size, stat.st_mtime_ns, digest)
        return digest

    # ---- histórico ---------------------------------------------------------
    def history_path_for(self, file_path: Path) -> Path:
        """Destino do backup de `file_path` antes de sobrescrevê-lo."""
        relative = file_path.resolve().relative_to(self.ui_dir.resolve())
        folder = self.history_dir / relative
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        candidate = folder / f"{stamp}{file_path.suffix}"
        number = 2
        while candidate.exists():
            candidate = folder / f"{stamp}-{number}{file_path.suffix}"
            number += 1
        return candidate

    def prune_history(self, file_path: Path, keep: int = HISTORY_LIMIT) -> None:
        backups = self.history(file_path)
        for old in backups[keep:] if keep else backups:
            old.unlink()

    def _history_folder(self, file_path: Path) -> Path:
        return self.history_dir / file_path.resolve().relative_to(self.ui_dir.resolve())

    def original_path_for(self, file_path: Path) -> Path:
        """Cópia do arquivo como era na criação do projeto (gravada no 1º salvamento)."""
        return self._history_folder(file_path) / f"{ORIGINAL_NAME}{file_path.suffix}"

    def base_bytes(self, relative: str) -> bytes | None:
        """O arquivo como era na criação do projeto, quando disponível."""
        path = self.ui_dir / relative
        original = self.original_path_for(path)
        try:
            if original.is_file():
                return original.read_bytes()
            data = path.read_bytes()
        except OSError:
            return None
        key = Path(relative).as_posix()
        return data if self.base_hashes.get(key) == hashlib.sha1(data).hexdigest() else None

    def history(self, file_path: Path) -> list[Path]:
        """Backups do arquivo, do mais recente ao mais antigo (sem o original)."""
        folder = self._history_folder(file_path)
        if not folder.is_dir():
            return []
        return sorted(
            (item for item in folder.iterdir() if item.is_file() and not item.stem.startswith(ORIGINAL_NAME)),
            key=lambda item: item.name,
            reverse=True,
        )

    def remember_original(self, file_path: Path) -> None:
        """Antes do 1º salvamento, guarda o original se o arquivo ainda não foi alterado."""
        original = self.original_path_for(file_path)
        key = file_path.resolve().relative_to(self.ui_dir.resolve()).as_posix()
        if original.exists() or self.base_hashes.get(key) != _hash(file_path):
            return
        original.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, original)

    def restore(self, file_path: Path, source: Path) -> Path:
        """Substitui o arquivo por `source`, guardando antes o estado atual no histórico."""
        self.invalidate_changes()
        backup = self.history_path_for(file_path)
        shutil.copy2(file_path, backup)
        temporary = file_path.with_name(f".{file_path.name}.gf-ui-editor.tmp")
        shutil.copy2(source, temporary)
        os.replace(temporary, file_path)
        self.prune_history(file_path)
        return backup

    def import_target(self, source: Path) -> Path:
        """Onde um arquivo avulso entra: no lugar do de mesmo nome, se houver; senão na raiz da UI."""
        matches = [relative for relative in self.files() if relative.name.lower() == source.name.lower()]
        if matches:
            return self.ui_dir / min(matches, key=lambda relative: len(relative.parts))
        return self.ui_dir / source.name

    def import_file(self, source: Path) -> tuple[Path, Path | None]:
        """Copia `source` para o projeto. Devolve o destino e o backup do arquivo substituído."""
        self.invalidate_changes()
        target = self.import_target(source)
        if target.exists():
            self.remember_original(target)
            backup = self.restore(target, source)
        else:
            shutil.copy2(source, target)
            backup = None
        self._files = None
        return target, backup

    def import_loose_files(self, sources: Iterable[Path], focus: Path | None = None) -> Path | None:
        """Importa os arquivos em ordem e devolve o caminho atualizado do arquivo em foco."""
        for source in sources:
            target, _backup = self.import_file(source)
            if focus is not None and source == focus:
                focus = target
        return focus

    def rename_file(self, file_path: Path, new_name: str) -> tuple[Path, Path | None]:
        """Renomeia na mesma pasta. Se já existir um arquivo com o nome novo, ele vai
        para o histórico antes de ser substituído. Devolve o destino e esse backup."""
        self.invalidate_changes()
        target = file_path.with_name(new_name)
        backup = None
        same_file = os.path.normcase(str(target)) == os.path.normcase(str(file_path))
        if target.exists() and not same_file:
            self.remember_original(target)
            backup = self.history_path_for(target)
            shutil.copy2(target, backup)
            target.unlink()
        os.replace(file_path, target)
        self._files = None
        return target, backup

    def delete_file(self, file_path: Path) -> Path:
        """Tira o arquivo do projeto, guardando uma cópia no histórico. Devolve a cópia."""
        self.invalidate_changes()
        self.remember_original(file_path)
        backup = self.history_path_for(file_path)
        shutil.copy2(file_path, backup)
        file_path.unlink()
        self._files = None
        return backup

    def contains(self, file_path: Path) -> bool:
        # Comparação de texto: Path.resolve() consulta o disco e era chamado centenas de vezes.
        root = os.path.normcase(os.path.abspath(self.ui_dir)) + os.sep
        return os.path.normcase(os.path.abspath(file_path)).startswith(root)

    def relative_key(self, file_path: Path) -> str:
        """Caminho de um arquivo do projeto relativo a ui/, com barras normais."""
        return Path(os.path.relpath(os.path.abspath(file_path), os.path.abspath(self.ui_dir))).as_posix()

    # ---- saída -------------------------------------------------------------
    def shipped_files(self, progress: Progress = None) -> tuple[list[Path], int]:
        """Arquivos que a UI leva para o jogo e o .zip, e quantos ficaram de fora.

        O launcher aplica uma UI copiando os arquivos dela por cima da pasta UI; o que ela não
        traz continua como está (vault/launcher.md). Então só vai o que difere do oficial
        (tamanho e CRC do GameDataFileList.txt): `map`, ícones e o que ninguém mexeu ficam de
        fora sozinhos. Sem a lista oficial (jogo não encontrado), vai tudo.
        """
        files = self.files(refresh=True)
        official = gamedata.official_ui_files(self.game_dir) if self.game_dir is not None else {}
        if not official:
            return files, 0
        shipped = []
        for done, relative in enumerate(files, 1):
            if not gamedata.is_official(self.ui_dir / relative, relative.as_posix(), official):
                shipped.append(relative)
            if progress is not None:
                progress(done, len(files))
        return shipped, len(files) - len(shipped)

    def export_zip(self, destination: Path, progress: Progress = None) -> Path:
        """Zip no formato dos presets oficiais: uma pasta raiz com os arquivos que diferem do oficial."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        files, skipped = self.shipped_files()
        if not files:
            raise ValueError("Nenhum arquivo do projeto difere da UI oficial: não há o que exportar.")
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
            for done, relative in enumerate(files, 1):
                archive.write(self.ui_dir / relative, f"{self.custom_name}/{relative.as_posix()}")
                if progress is not None:
                    progress(done, len(files))
        self.last_export = (len(files), skipped)
        return destination

    def publish(
        self, *, copy_to_ui: bool = True, select_in_launcher: bool = True, progress: Progress = None
    ) -> PublishResult:
        """Atualiza `UICustom/<nome>` (espelho exato) e, opcionalmente, `UI/`."""
        self.invalidate_changes()
        if self.game_dir is None:
            raise ValueError("Projeto sem pasta do jogo.")
        custom_dir = self.game_dir / "UICustom" / self.custom_name
        files = self.files(refresh=True)
        shipped, skipped = self.shipped_files()
        wanted = {relative.as_posix().lower() for relative in shipped}
        if custom_dir.exists() and not self.publish_folder:
            for existing in sorted(custom_dir.rglob("*"), reverse=True):
                relative = existing.relative_to(custom_dir).as_posix().lower()
                if existing.is_file() and relative not in wanted:
                    existing.unlink()
                elif existing.is_dir() and not any(existing.iterdir()):
                    existing.rmdir()
        from . import game_sync  # game_sync importa este módulo

        copied = 0
        ui_dir = self.game_dir / "UI"
        official = gamedata.official_ui_files(self.game_dir)
        sent = game_sync.load_sent(self.game_dir) if copy_to_ui else {}
        sent_now: dict[str, str] = {}
        backups: list[tuple[str, Path]] = []
        custom_dir.mkdir(parents=True, exist_ok=True)
        for done, relative in enumerate(files, 1):
            source = self.ui_dir / relative
            key = relative.as_posix()
            if key.lower() in wanted:
                _copy_if_different(source, custom_dir / relative)
            # A pasta UI recebe o projeto inteiro (só o que difere do que está lá): ela pode ter
            # arquivos de outra UI aplicada antes, e o jogo tem de ficar igual ao editor.
            if copy_to_ui:
                target = ui_dir / relative
                # Proteção sem atrito: o que foi editado fora do editor ganha uma cópia antes.
                if target.is_file() and not _same_content(source, target) and game_sync.edited_outside(
                    self.game_dir, key, target, official, sent
                ):
                    backup = game_sync.game_backup_path(self, source)
                    shutil.copy2(target, backup)
                    backups.append((key, backup))
                if _copy_if_different(source, target):
                    copied += 1
                if sent.get(key.lower()) != (crc := gamedata.file_crc(source)):
                    sent_now[key.lower()] = crc
            if progress is not None:
                progress(done, len(files))
        game_sync.remember_sent(self.game_dir, sent_now)
        launcher_ini = self.game_dir / "Launcher.ini"
        previous = selected_ui(launcher_ini)
        launcher_updated = False
        if select_in_launcher:
            launcher_updated = select_custom_ui(launcher_ini, self.custom_name)
        return PublishResult(
            custom_dir,
            copied,
            launcher_updated,
            skipped,
            previous,
            process_running(self.game_dir / "Launcher.exe"),
            backups,
        )

    def unpublished_files(self) -> set[str]:
        """Arquivos alterados no projeto cujo conteúdo difere do que está na pasta UI do jogo."""
        if self.game_dir is None:
            return set()
        if self._unpublished_memo is not None and time.monotonic() - self._unpublished_memo[0] < self.changes_ttl:
            return set(self._unpublished_memo[1])
        pending = self._compute_unpublished_files()
        self._unpublished_memo = (time.monotonic(), frozenset(pending))
        return pending

    def _compute_unpublished_files(self) -> set[str]:
        assert self.game_dir is not None
        pending: set[str] = set()
        for key in self.modified_files():
            source = self.ui_dir / key
            target = self.game_dir / "UI" / key
            try:
                if not target.is_file() or source.read_bytes() != target.read_bytes():
                    pending.add(key)
            except OSError:
                pending.add(key)
        return pending


def _same_content(source: Path, target: Path) -> bool:
    try:
        return source.stat().st_size == target.stat().st_size and source.read_bytes() == target.read_bytes()
    except OSError:
        return False


def _copy_if_different(source: Path, target: Path) -> bool:
    if target.exists() and _same_content(source, target):
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.gf-ui-editor.tmp")
    shutil.copy2(source, temporary)
    os.replace(temporary, target)
    return True


def selected_ui(launcher_ini: Path) -> str:
    """Valor de `UI=` na seção [Config] do Launcher.ini ("" se não houver)."""
    try:
        lines = launcher_ini.read_text(encoding="latin-1").splitlines()
    except OSError:
        return ""
    in_config = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("["):
            in_config = stripped.lower() == "[config]"
        elif in_config and stripped.lower().startswith("ui="):
            return stripped.split("=", 1)[1].strip()
    return ""


def process_running(executable: Path) -> bool:
    """Há um processo rodando a partir deste executável? (Windows; False se não der para saber.)"""
    if os.name != "nt":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        wanted = os.path.normcase(str(executable.resolve()))
        psapi = ctypes.WinDLL("psapi")
        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
        ]
        ids = (wintypes.DWORD * 4096)()
        needed = wintypes.DWORD()
        if not psapi.EnumProcesses(ids, ctypes.sizeof(ids), ctypes.byref(needed)):
            return False
        for index in range(needed.value // ctypes.sizeof(wintypes.DWORD)):
            handle = kernel32.OpenProcess(0x1000, False, ids[index])  # PROCESS_QUERY_LIMITED_INFORMATION
            if not handle:
                continue
            try:
                buffer = ctypes.create_unicode_buffer(1024)
                size = wintypes.DWORD(len(buffer))
                if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                    if os.path.normcase(buffer.value) == wanted:
                        return True
            finally:
                kernel32.CloseHandle(handle)
    except (OSError, AttributeError, ValueError):
        return False
    return False


def select_custom_ui(launcher_ini: Path, custom_name: str) -> bool:
    """Marca a UI customizada como escolhida, como o launcher faz ao selecioná-la."""
    if not launcher_ini.is_file():
        return False
    raw = launcher_ini.read_bytes()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    lines = raw.decode("latin-1").splitlines()
    value = f"custom:{custom_name}"
    wanted = {"UI": value, "UIAplicada": value}
    output: list[str] = []
    in_config = False
    seen: set[str] = set()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("["):
            if in_config:
                output.extend(f"{key}={val}" for key, val in wanted.items() if key not in seen)
                seen.update(wanted)
            in_config = stripped.lower() == "[config]"
        elif in_config and "=" in line:
            key = line.split("=", 1)[0].strip()
            if key in wanted:
                line = f"{key}={wanted[key]}"
                seen.add(key)
        output.append(line)
    if in_config:
        output.extend(f"{key}={val}" for key, val in wanted.items() if key not in seen)
    text = newline.join(output) + newline
    if text.encode("latin-1") == raw:
        return False
    launcher_ini.write_bytes(text.encode("latin-1"))
    return True


def extract_ui_zip(archive_path: Path, destination: Path) -> Path:
    """Extrai um .zip de UI e devolve a pasta que contém os arquivos.

    Os presets vêm com uma pasta raiz dentro do .zip; outros trazem os arquivos soltos.
    """
    destination = destination.resolve()
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            target = (destination / member.filename).resolve()
            if destination != target and destination not in target.parents:
                raise ValueError(f"Caminho inválido no .zip: {member.filename}")
        archive.extractall(destination)
    root = destination
    while True:
        entries = list(root.iterdir())
        if len(entries) == 1 and entries[0].is_dir():
            root = entries[0]
        else:
            break
    if not any(entry.suffix.lower() == ".xml" for entry in root.iterdir() if entry.is_file()):
        raise ValueError("O .zip não contém arquivos XML de UI.")
    return root


def create_from_source(
    name: str,
    source: Path,
    game_dir: Path | None,
    *,
    projects_root: Path = PROJECTS_ROOT,
    progress: Progress = None,
    include_assets: bool = False,
    publish_folder: str = "",
    loose_files: Iterable[Path] = (),
) -> Project:
    """Cria o projeto a partir de uma pasta ou .zip e importa os arquivos soltos."""
    if not source.exists():
        raise FileNotFoundError(str(source))

    def create(source_dir: Path) -> Project:
        return Project.create(
            name, source_dir, game_dir, projects_root=projects_root, progress=progress,
            include_assets=include_assets, publish_folder=publish_folder,
        )

    if source.is_file():
        with tempfile.TemporaryDirectory() as folder:
            project = create(extract_ui_zip(source, Path(folder)))
    else:
        project = create(source)
    project.import_loose_files(loose_files)
    return project


def configured_game_dir(saved: str, default_ui_directory: Path) -> Path | None:
    """Usa a pasta configurada, se válida, ou a raiz acima da UI padrão."""
    if saved and Path(saved).is_dir():
        return normalize_game_dir(Path(saved))
    game_dir = default_ui_directory.parent
    return game_dir if game_dir.is_dir() else None


def custom_ui_sources(game_dir: Path) -> list[tuple[str, Path]]:
    """Pastas que podem servir de base para um projeto novo."""
    sources: list[tuple[str, Path]] = []
    if (game_dir / "UI").is_dir():
        sources.append(("UI", game_dir / "UI"))
    custom_root = game_dir / "UICustom"
    if custom_root.is_dir():
        for folder in sorted(custom_root.iterdir()):
            if folder.is_dir():
                sources.append((f"UICustom/{folder.name}", folder))
    return sources


def projects_publishing_to(folder: str, exclude: Path | None = None, projects_root: Path | None = None) -> list[str]:
    """Nomes dos projetos cujo Enviar para o jogo escreve em UICustom/`folder`."""
    names = []
    for root in list_projects(projects_root or PROJECTS_ROOT):
        if exclude is not None and os.path.normcase(str(root)) == os.path.normcase(str(exclude)):
            continue
        # Só leitura: abrir cada projeto pelo caminho normal deixava todos presos a esta janela.
        settings = storage.peek_settings(root)
        if settings is None:
            continue
        name = str(settings.get("name") or root.name)
        custom_name = str(settings.get("publish_folder") or "") or safe_name(name)
        if custom_name.lower() == folder.lower():
            names.append(name)
    return names


# ---- gerenciar projetos (tela inicial) --------------------------------------------
class ProjectNameTaken(ValueError):
    """Já existe um projeto (pasta) com esse nome."""


def owned_custom_folder(project: "Project") -> Path | None:
    """Pasta UICustom que só este projeto publica (o F5 a criou); None se não existe ou é compartilhada."""
    if project.game_dir is None:
        return None
    folder = project.game_dir / "UICustom" / project.custom_name
    if not folder.is_dir():
        return None
    if projects_publishing_to(project.custom_name, exclude=project.root, projects_root=project.root.parent):
        return None
    return folder


def duplicate_project(root: Path, new_name: str) -> Path:
    """Cópia completa do projeto com outro nome; publica na própria pasta UICustom.

    Fica sem o histórico (.history) e sem as versões (.versions) do original: é um ponto de partida novo.
    """
    new_name = new_name.strip()
    target = root.parent / safe_name(new_name)
    if target.exists():
        raise ProjectNameTaken(str(target))
    storage.close_all()  # banco consolidado (sem -wal) antes de copiar
    shutil.copytree(
        root, target, ignore=shutil.ignore_patterns(".history", ".versions", f"{storage.PROJECT_DB}-wal", f"{storage.PROJECT_DB}-shm")
    )
    copy = Project.load(target)
    copy.name = new_name
    copy.publish_folder = ""
    copy.save_manifest()
    storage.close_all()
    return target


def rename_project(root: Path, new_name: str) -> Path:
    """Renomeia o projeto (nome e pasta). A pasta UICustom dele e a escolha no launcher acompanham."""
    new_name = new_name.strip()
    project = Project.load(root)
    old_custom = project.custom_name
    owned = owned_custom_folder(project)
    target = root.parent / safe_name(new_name)
    if os.path.normcase(str(target)) != os.path.normcase(str(root)) and target.exists():
        raise ProjectNameTaken(str(target))
    storage.close_all()  # o Windows não renomeia pasta com banco aberto
    if os.path.normcase(str(target)) != os.path.normcase(str(root)):
        os.replace(root, target)
    project = Project.load(target)
    project.name = new_name
    project.save_manifest()
    new_custom = project.custom_name
    if owned is not None and project.game_dir is not None and new_custom.lower() != old_custom.lower():
        new_folder = project.game_dir / "UICustom" / new_custom
        if not new_folder.exists():
            os.replace(owned, new_folder)
            launcher_ini = project.game_dir / "Launcher.ini"
            if selected_ui(launcher_ini).lower() == f"custom:{old_custom}".lower():
                select_custom_ui(launcher_ini, new_custom)
    storage.close_all()
    return target


def delete_project(root: Path, trash: Callable[[Path], bool], remove_custom: bool = False) -> list[Path]:
    """Manda o projeto (e, se pedido, a pasta UICustom só dele) para a Lixeira. Devolve o que saiu."""
    project = Project.load(root)
    custom = owned_custom_folder(project) if remove_custom else None
    storage.close_all()
    removed = []
    for path in (root, custom):
        if path is not None and path.exists():
            if not trash(path):
                raise OSError(f"Não foi possível mandar para a Lixeira: {path}")
            removed.append(path)
    return removed


def list_projects(projects_root: Path = PROJECTS_ROOT) -> list[Path]:
    if not projects_root.is_dir():
        return []
    return sorted(path for path in projects_root.iterdir() if storage.is_project(path))
