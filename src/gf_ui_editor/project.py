"""Projetos de UI: cópia de trabalho fora da pasta do jogo, histórico e publicação.

Um projeto é uma pasta com:

- `project.json`: nome, pasta do jogo e hashes dos arquivos na criação;
- `ui/`: os arquivos da interface que estão sendo editados;
- `.history/`: backups automáticos de cada salvamento.

O launcher novo extrai cada UI importada em `<jogo>/UICustom/<nome>/` e, ao clicar
em Jogar, copia a UI escolhida (`UI=`/`UIAplicada=` no `Launcher.ini`) por cima de
`<jogo>/UI/`. "Testar no jogo" reproduz esse fluxo sem passar pelo .zip.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import zipfile


PROJECTS_ROOT = Path.home() / "Documents" / "GF UI Projects"
MANIFEST = "project.json"
HASH_CACHE = ".hash-cache.json"
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


@dataclass
class Project:
    root: Path
    name: str
    game_dir: Path | None
    base_hashes: dict[str, str] = field(default_factory=dict)
    include_assets: bool = False
    # (tamanho, mtime) -> hash, para não reler arquivos que não mudaram.
    _hash_cache: dict[str, tuple[int, int, str]] = field(default_factory=dict, repr=False)
    _files: list[Path] | None = field(default=None, repr=False)

    @property
    def ui_dir(self) -> Path:
        return self.root / "ui"

    @property
    def history_dir(self) -> Path:
        return self.root / ".history"

    @property
    def custom_name(self) -> str:
        return safe_name(self.name)

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
    ) -> "Project":
        root = projects_root / safe_name(name)
        if root.exists():
            raise FileExistsError(root)
        ui_dir = root / "ui"
        hashes: dict[str, str] = {}
        files = _ui_files(source_dir, include_assets)
        for done, relative in enumerate(files, 1):
            target = ui_dir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_dir / relative, target)
            hashes[relative.as_posix()] = _hash(target)
            if progress is not None:
                progress(done, len(files))
        project = cls(root, name, game_dir, hashes, include_assets)
        for key, digest in hashes.items():
            stat = (ui_dir / key).stat()
            project._hash_cache[key] = (stat.st_size, stat.st_mtime_ns, digest)
        project.save_manifest()
        return project

    @classmethod
    def load(cls, root: Path) -> "Project":
        data = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
        game_dir = data.get("game_dir")
        return cls(
            root,
            data.get("name", root.name),
            Path(game_dir) if game_dir else None,
            dict(data.get("base_hashes", {})),
            bool(data.get("include_assets", False)),
        )

    def save_manifest(self) -> None:
        data = {
            "name": self.name,
            "game_dir": str(self.game_dir) if self.game_dir else None,
            "include_assets": self.include_assets,
            "base_hashes": self.base_hashes,
        }
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / MANIFEST).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    # ---- estado ------------------------------------------------------------
    def files(self, refresh: bool = False) -> list[Path]:
        """Lista em cache; `refresh=True` relê a pasta (arquivos criados/apagados fora)."""
        if refresh or self._files is None:
            self._files = _ui_files(self.ui_dir, self.include_assets)
        return self._files

    def modified_files(self) -> set[str]:
        """Arquivos alterados ou criados desde a criação do projeto."""
        if not self._hash_cache:
            self._load_hash_cache()
        before = len(self._hash_cache), dict(self._hash_cache)
        changed: set[str] = set()
        for relative in self.files():
            key = relative.as_posix()
            if self.base_hashes.get(key) != self._cached_hash(relative):
                changed.add(key)
        if (len(self._hash_cache), self._hash_cache) != before:
            self._save_hash_cache()
        return changed

    def _load_hash_cache(self) -> None:
        try:
            data = json.loads((self.root / HASH_CACHE).read_text(encoding="utf-8"))
            self._hash_cache = {key: (int(size), int(mtime), digest) for key, (size, mtime, digest) in data.items()}
        except (OSError, ValueError, TypeError):
            self._hash_cache = {}

    def _save_hash_cache(self) -> None:
        try:
            (self.root / HASH_CACHE).write_text(
                json.dumps({key: list(value) for key, value in self._hash_cache.items()}), encoding="utf-8"
            )
        except OSError:
            pass

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
        backup = self.history_path_for(file_path)
        shutil.copy2(file_path, backup)
        temporary = file_path.with_name(f".{file_path.name}.gf-ui-editor.tmp")
        shutil.copy2(source, temporary)
        os.replace(temporary, file_path)
        self.prune_history(file_path)
        return backup

    def contains(self, file_path: Path) -> bool:
        try:
            file_path.resolve().relative_to(self.ui_dir.resolve())
        except ValueError:
            return False
        return True

    # ---- saída -------------------------------------------------------------
    def export_zip(self, destination: Path, progress: Progress = None) -> Path:
        """Zip no formato dos presets oficiais: uma pasta raiz com os arquivos."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
            files = self.files(refresh=True)
            for done, relative in enumerate(files, 1):
                archive.write(self.ui_dir / relative, f"{self.custom_name}/{relative.as_posix()}")
                if progress is not None:
                    progress(done, len(files))
        return destination

    def publish(
        self, *, copy_to_ui: bool = True, select_in_launcher: bool = True, progress: Progress = None
    ) -> PublishResult:
        """Atualiza `UICustom/<nome>` (espelho exato) e, opcionalmente, `UI/`."""
        if self.game_dir is None:
            raise ValueError("Projeto sem pasta do jogo.")
        custom_dir = self.game_dir / "UICustom" / self.custom_name
        files = self.files(refresh=True)
        wanted = {relative.as_posix().lower() for relative in files}
        if custom_dir.exists():
            for existing in sorted(custom_dir.rglob("*"), reverse=True):
                relative = existing.relative_to(custom_dir).as_posix().lower()
                if existing.is_file() and relative not in wanted:
                    existing.unlink()
                elif existing.is_dir() and not any(existing.iterdir()):
                    existing.rmdir()
        copied = 0
        ui_dir = self.game_dir / "UI"
        for done, relative in enumerate(files, 1):
            source = self.ui_dir / relative
            _copy_if_different(source, custom_dir / relative)
            if copy_to_ui and _copy_if_different(source, ui_dir / relative):
                copied += 1
            if progress is not None:
                progress(done, len(files))
        launcher_updated = False
        if select_in_launcher:
            launcher_updated = select_custom_ui(self.game_dir / "Launcher.ini", self.custom_name)
        return PublishResult(custom_dir, copied, launcher_updated)


def _copy_if_different(source: Path, target: Path) -> bool:
    if target.exists():
        source_stat, target_stat = source.stat(), target.stat()
        if source_stat.st_size == target_stat.st_size and source.read_bytes() == target.read_bytes():
            return False
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.gf-ui-editor.tmp")
    shutil.copy2(source, temporary)
    os.replace(temporary, target)
    return True


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


def list_projects(projects_root: Path = PROJECTS_ROOT) -> list[Path]:
    if not projects_root.is_dir():
        return []
    return sorted(path for path in projects_root.iterdir() if (path / MANIFEST).is_file())
