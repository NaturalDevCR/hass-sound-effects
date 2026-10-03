"""SQLite connection, schema and first-run seeds."""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from .models import Settings

SCHEMA_VERSION = 1

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    """CREATE TABLE IF NOT EXISTS seasons (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, color TEXT NOT NULL, icon TEXT NOT NULL,
        start TEXT, "end" TEXT, priority INTEGER NOT NULL DEFAULT 0,
        builtin INTEGER NOT NULL DEFAULT 0)""",
    """CREATE TABLE IF NOT EXISTS profiles (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, target_lufs REAL NOT NULL,
        true_peak REAL NOT NULL, lra REAL NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS categories (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, icon TEXT NOT NULL, color TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '', sort_order INTEGER NOT NULL DEFAULT 0,
        default_profile_id TEXT REFERENCES profiles(id))""",
    """CREATE TABLE IF NOT EXISTS sounds (
        id TEXT PRIMARY KEY, category_id TEXT NOT NULL REFERENCES categories(id),
        title TEXT NOT NULL, key TEXT NOT NULL, tags TEXT NOT NULL DEFAULT '[]',
        seasons TEXT NOT NULL DEFAULT '["regular"]', all_seasons INTEGER NOT NULL DEFAULT 0,
        enabled INTEGER NOT NULL DEFAULT 1, notes TEXT NOT NULL DEFAULT '',
        original TEXT, recipe TEXT NOT NULL, published TEXT, status TEXT NOT NULL,
        error TEXT, selection_count INTEGER NOT NULL DEFAULT 0, last_selected_at TEXT,
        has_preview INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL)""",
)

_SEED_PROFILES = (
    ("standard", "Standard", -16.0, -1.5, 11.0),
    ("loud", "Loud", -13.0, -1.0, 11.0),
    ("soft", "Soft", -20.0, -1.5, 11.0),
    ("voice", "Voice / announcement", -18.0, -1.5, 7.0),
)


class Database:
    """One shared SQLite connection, serialized by a re-entrant lock.

    The connection is created with ``check_same_thread=False`` and every access must hold
    :attr:`lock`, so it is safe to use from the event loop and from worker threads alike.
    """

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        # Autocommit mode: transactions are explicit (see ``transaction``).
        self.connection = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode = WAL")
        self.connection.execute("PRAGMA foreign_keys = ON")
        self._initialise()

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection]:
        """Hold the lock and run the block in one write transaction (rolled back on error)."""
        with self.lock:
            self.connection.execute("BEGIN IMMEDIATE")
            try:
                yield self.connection
                self.connection.execute("COMMIT")
            except BaseException:
                if self.connection.in_transaction:
                    self.connection.execute("ROLLBACK")
                raise

    def close(self) -> None:
        with self.lock:
            self.connection.close()

    def _initialise(self) -> None:
        with self.transaction() as conn:
            version: int = conn.execute("PRAGMA user_version").fetchone()[0]
            for statement in _SCHEMA:
                conn.execute(statement)
            if version < 1:
                _seed(conn)
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def _seed(conn: sqlite3.Connection) -> None:
    conn.execute(
        'INSERT OR IGNORE INTO seasons (id, name, color, icon, start, "end", priority, builtin)'
        " VALUES ('regular', 'Regular', '#64748b', 'mdi:calendar-blank', NULL, NULL, 0, 1)"
    )
    conn.executemany(
        "INSERT OR IGNORE INTO profiles (id, name, target_lufs, true_peak, lra)"
        " VALUES (?, ?, ?, ?, ?)",
        _SEED_PROFILES,
    )
    conn.execute(
        "INSERT OR IGNORE INTO categories (id, name, icon, color, description, sort_order,"
        " default_profile_id) VALUES ('general', 'General', 'mdi:music-note', '#8b5cf6', '', 0,"
        " NULL)"
    )
    conn.execute("INSERT OR IGNORE INTO meta (key, value) VALUES ('catalog_revision', '0')")
    conn.executemany(
        "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
        [
            (key, json.dumps(value, separators=(",", ":")))
            for key, value in Settings().model_dump(mode="json").items()
        ],
    )
