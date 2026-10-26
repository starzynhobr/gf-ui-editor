"""Persistência em SQLite: um banco por projeto e um compartilhado entre projetos.

Todo acesso a disco de dados do editor passa por aqui. Cada banco guarda a versão do
esquema em ``PRAGMA user_version`` e sobe de versão aplicando MIGRATIONS em ordem: para
mudar o formato no futuro, acrescenta-se um passo à lista, sem reescrever o resto.

- ``project.db`` (na pasta do projeto): configurações, camadas, modo de posição por
  arquivo, hashes dos arquivos e textos editados.
- ``gf-ui-editor.db`` (na pasta de projetos): o que vale para todos, como as versões
  da UI oficial já vistas.

Projetos antigos em JSON são importados na primeira abertura (ver migrate_project_json);
os arquivos originais ficam com o sufixo ``.migrated``.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterable, Sequence
from contextlib import contextmanager
from pathlib import Path

PROJECT_DB = "project.db"
SHARED_DB = "gf-ui-editor.db"

PROJECT_MIGRATIONS: Sequence[str] = (
    # 1: tudo o que ficava em project.json, .hash-cache.json e data/text-edits.json.
    """
    CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE base_hashes (path TEXT PRIMARY KEY, digest TEXT NOT NULL);
    CREATE TABLE file_hashes (
        path TEXT PRIMARY KEY, size INTEGER NOT NULL, mtime_ns INTEGER NOT NULL, digest TEXT NOT NULL
    );
    CREATE TABLE root_modes (path TEXT PRIMARY KEY, mode TEXT NOT NULL);
    CREATE TABLE reference_layers (position INTEGER PRIMARY KEY, path TEXT NOT NULL);
    CREATE TABLE text_edits (
        file TEXT NOT NULL,
        record_id TEXT NOT NULL,
        fields TEXT NOT NULL,
        original TEXT NOT NULL,
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        PRIMARY KEY (file, record_id)
    );
    """,
)

SHARED_MIGRATIONS: Sequence[str] = (
    # 1: versões (CRC) de cada XML oficial já vistas, antes em .official-ui/versions.json.
    """
    CREATE TABLE official_versions (
        relative TEXT NOT NULL,
        crc TEXT NOT NULL,
        position INTEGER NOT NULL,
        seen_at TEXT NOT NULL DEFAULT (datetime('now')),
        PRIMARY KEY (relative, crc)
    );
    """,
)

_lock = threading.RLock()


class Database:
    """Conexão SQLite com migrações. Segura para a thread de comparação em segundo plano."""

    def __init__(self, path: Path, migrations: Sequence[str]):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=NORMAL")
        self._migrate(migrations)

    def _migrate(self, migrations: Sequence[str]) -> None:
        with _lock:
            version = self._connection.execute("PRAGMA user_version").fetchone()[0]
            for number, script in enumerate(migrations[version:], version + 1):
                with self.transaction() as connection:
                    _run_script(connection, script)
                    connection.execute(f"PRAGMA user_version = {number}")

    @contextmanager
    def transaction(self):
        with _lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                yield self._connection
            except BaseException:
                self._connection.execute("ROLLBACK")
                raise
            self._connection.execute("COMMIT")

    def query(self, sql: str, parameters: Iterable = ()) -> list[tuple]:
        with _lock:
            return self._connection.execute(sql, tuple(parameters)).fetchall()

    def close(self) -> None:
        with _lock:
            self._connection.close()


def _run_script(connection: sqlite3.Connection, script: str) -> None:
    # executescript faria COMMIT da transação aberta; executa comando por comando.
    for statement in script.split(";"):
        if statement.strip():
            connection.execute(statement)


_open: dict[str, Database] = {}


def _database(path: Path, migrations: Sequence[str]) -> Database:
    key = str(path.resolve())
    with _lock:
        database = _open.get(key)
        if database is None:
            database = _open[key] = Database(path, migrations)
        return database


def project_database(root: Path) -> Database:
    return _database(root / PROJECT_DB, PROJECT_MIGRATIONS)


def shared_database(projects_root: Path) -> Database:
    return _database(projects_root / SHARED_DB, SHARED_MIGRATIONS)


def close_all() -> None:
    """Fecha as conexões abertas (testes e pastas temporárias no Windows)."""
    with _lock:
        for database in _open.values():
            database.close()
        _open.clear()


def is_project(root: Path) -> bool:
    return (root / PROJECT_DB).is_file() or (root / "project.json").is_file()


def last_modified(root: Path) -> float:
    """Última gravação no projeto (com WAL, a escrita recente fica no arquivo -wal)."""
    times = []
    for name in (PROJECT_DB, PROJECT_DB + "-wal", "project.json"):
        try:
            times.append((root / name).stat().st_mtime)
        except OSError:
            continue
    return max(times, default=0.0)


# ---- projeto ------------------------------------------------------------------
class ProjectStore:
    def __init__(self, root: Path):
        self.db = project_database(root)

    def settings(self) -> dict[str, object]:
        return {key: json.loads(value) for key, value in self.db.query("SELECT key, value FROM settings")}

    def save_settings(self, values: dict[str, object], root_modes: dict[str, str], layers: list[str]) -> None:
        with self.db.transaction() as connection:
            connection.executemany(
                "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                [(key, json.dumps(value, ensure_ascii=False)) for key, value in values.items()],
            )
            connection.execute("DELETE FROM root_modes")
            connection.executemany("INSERT INTO root_modes (path, mode) VALUES (?, ?)", root_modes.items())
            connection.execute("DELETE FROM reference_layers")
            connection.executemany(
                "INSERT INTO reference_layers (position, path) VALUES (?, ?)", list(enumerate(layers))
            )

    def root_modes(self) -> dict[str, str]:
        return dict(self.db.query("SELECT path, mode FROM root_modes"))

    def reference_layers(self) -> list[str]:
        return [path for (path,) in self.db.query("SELECT path FROM reference_layers ORDER BY position")]

    def base_hashes(self) -> dict[str, str]:
        return dict(self.db.query("SELECT path, digest FROM base_hashes"))

    def save_base_hashes(self, hashes: dict[str, str]) -> None:
        with self.db.transaction() as connection:
            connection.execute("DELETE FROM base_hashes")
            connection.executemany("INSERT INTO base_hashes (path, digest) VALUES (?, ?)", hashes.items())

    def file_hashes(self) -> dict[str, tuple[int, int, str]]:
        return {
            path: (size, mtime_ns, digest)
            for path, size, mtime_ns, digest in self.db.query("SELECT path, size, mtime_ns, digest FROM file_hashes")
        }

    def save_file_hashes(self, changed: dict[str, tuple[int, int, str]], removed: Iterable[str] = ()) -> None:
        """Grava só as linhas que mudaram (antes o JSON inteiro era reescrito)."""
        with self.db.transaction() as connection:
            connection.executemany(
                "INSERT INTO file_hashes (path, size, mtime_ns, digest) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(path) DO UPDATE SET size = excluded.size, mtime_ns = excluded.mtime_ns, digest = excluded.digest",
                [(path, *value) for path, value in changed.items()],
            )
            connection.executemany("DELETE FROM file_hashes WHERE path = ?", [(path,) for path in removed])

    def text_edits(self) -> dict[str, dict[str, tuple[list[str], list[str]]]]:
        edits: dict[str, dict[str, tuple[list[str], list[str]]]] = {}
        for file, record_id, fields, original in self.db.query(
            "SELECT file, record_id, fields, original FROM text_edits ORDER BY file, record_id"
        ):
            edits.setdefault(file, {})[record_id] = (json.loads(fields), json.loads(original))
        return edits

    def replace_text_edits(self, edits: dict[str, dict[str, tuple[list[str], list[str]]]]) -> None:
        with self.db.transaction() as connection:
            existing = {
                (file, record_id): (fields, original)
                for file, record_id, fields, original in connection.execute(
                    "SELECT file, record_id, fields, original FROM text_edits"
                )
            }
            wanted = {
                (file, record_id): (json.dumps(fields, ensure_ascii=False), json.dumps(original, ensure_ascii=False))
                for file, records in edits.items()
                for record_id, (fields, original) in records.items()
            }
            connection.executemany(
                "DELETE FROM text_edits WHERE file = ? AND record_id = ?", [key for key in existing if key not in wanted]
            )
            # Só as edições novas ou alteradas ganham uma nova data em updated_at.
            connection.executemany(
                "INSERT INTO text_edits (file, record_id, fields, original) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(file, record_id) DO UPDATE SET fields = excluded.fields, original = excluded.original, "
                "updated_at = datetime('now')",
                [(*key, *value) for key, value in wanted.items() if existing.get(key) != value],
            )


def migrate_project_json(root: Path) -> bool:
    """Importa project.json, .hash-cache.json e data/text-edits.json para project.db.

    Os JSON ficam com o sufixo .migrated (nada é apagado). Devolve True se importou.
    """
    manifest = root / "project.json"
    if (root / PROJECT_DB).is_file() or not manifest.is_file():
        return False
    data = json.loads(manifest.read_text(encoding="utf-8"))
    store = ProjectStore(root)
    store.save_settings(
        {
            "name": data.get("name", root.name),
            "game_dir": data.get("game_dir"),
            "include_assets": bool(data.get("include_assets", False)),
            "publish_folder": str(data.get("publish_folder", "")),
        },
        {str(key): str(value) for key, value in data.get("root_modes", {}).items()},
        [str(name) for name in data.get("reference_layers", [])],
    )
    store.save_base_hashes({str(key): str(value) for key, value in data.get("base_hashes", {}).items()})
    hash_cache = root / ".hash-cache.json"
    if hash_cache.is_file():
        try:
            cached = json.loads(hash_cache.read_text(encoding="utf-8"))
            store.save_file_hashes({key: (int(size), int(mtime), str(digest)) for key, (size, mtime, digest) in cached.items()})
        except (ValueError, TypeError):
            pass  # cache: se estiver estragado, os hashes são recalculados
    edits_file = root / "data" / "text-edits.json"
    if edits_file.is_file():
        edits = json.loads(edits_file.read_text(encoding="utf-8"))
        store.replace_text_edits({
            name: {record_id: (list(entry["fields"]), list(entry.get("original", []))) for record_id, entry in records.items()}
            for name, records in edits.items()
        })
    for path in (manifest, hash_cache, edits_file):
        if path.is_file():
            path.replace(path.with_name(path.name + ".migrated"))
    return True


# ---- compartilhado --------------------------------------------------------------
class SharedStore:
    def __init__(self, projects_root: Path):
        self.db = shared_database(projects_root)

    def official_versions(self) -> dict[str, list[str]]:
        versions: dict[str, list[str]] = {}
        for relative, crc in self.db.query("SELECT relative, crc FROM official_versions ORDER BY relative, position"):
            versions.setdefault(relative, []).append(crc)
        return versions

    def add_official_version(self, relative: str, crc: str) -> None:
        with self.db.transaction() as connection:
            position = connection.execute(
                "SELECT COALESCE(MAX(position) + 1, 0) FROM official_versions WHERE relative = ?", (relative,)
            ).fetchone()[0]
            connection.execute(
                "INSERT OR IGNORE INTO official_versions (relative, crc, position) VALUES (?, ?, ?)",
                (relative, crc, position),
            )

    def import_official_versions(self, versions: dict[str, list[str]]) -> None:
        with self.db.transaction() as connection:
            for relative, crcs in versions.items():
                connection.executemany(
                    "INSERT OR IGNORE INTO official_versions (relative, crc, position) VALUES (?, ?, ?)",
                    [(relative.lower(), crc, position) for position, crc in enumerate(crcs)],
                )
