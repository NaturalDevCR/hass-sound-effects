import sqlite3
from pathlib import Path

import pytest

from sound_effects_studio.config import Paths
from sound_effects_studio.db import Database

pytestmark = pytest.mark.studio


def test_pragmas_and_schema_version(paths: Paths) -> None:
    db = Database(paths.database_path)
    conn = db.connection
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    tables = {
        row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert {"meta", "settings", "seasons", "profiles", "categories", "sounds"} <= tables
    db.close()


def test_seeds_once(paths: Paths) -> None:
    db = Database(paths.database_path)
    with db.transaction() as conn:
        conn.execute("DELETE FROM categories")
    db.close()
    reopened = Database(paths.database_path)
    count = reopened.connection.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
    assert count == 0
    reopened.close()


def test_transaction_rolls_back_on_error(paths: Paths) -> None:
    db = Database(paths.database_path)
    with pytest.raises(RuntimeError), db.transaction() as conn:
        conn.execute("DELETE FROM profiles")
        raise RuntimeError("boom")
    assert db.connection.execute("SELECT COUNT(*) FROM profiles").fetchone()[0] == 4
    db.close()


def test_foreign_keys_enforced(paths: Paths) -> None:
    db = Database(paths.database_path)
    with pytest.raises(sqlite3.IntegrityError), db.transaction() as conn:
        conn.execute(
            "INSERT INTO sounds (id, category_id, title, key, recipe, status, created_at,"
            " updated_at) VALUES ('x', 'missing', 't', 'k', '{}', 'ready', 'now', 'now')"
        )
    db.close()


def test_existing_schema_version_is_left_alone(paths: Paths) -> None:
    Database(paths.database_path).close()
    raw = sqlite3.connect(paths.database_path)
    raw.execute("DELETE FROM profiles")
    raw.commit()
    raw.close()
    reopened = Database(paths.database_path)
    assert reopened.connection.execute("PRAGMA user_version").fetchone()[0] == 1
    assert reopened.connection.execute("SELECT COUNT(*) FROM profiles").fetchone()[0] == 0
    reopened.close()


def test_newer_schema_version_is_refused_and_connection_closed(
    paths: Paths, monkeypatch: pytest.MonkeyPatch
) -> None:
    Database(paths.database_path).close()
    raw = sqlite3.connect(paths.database_path)
    raw.execute("PRAGMA user_version = 2")
    raw.close()

    opened: list[sqlite3.Connection] = []
    real_connect = sqlite3.connect

    def spy(path: Path, **kwargs: object) -> sqlite3.Connection:
        connection = real_connect(path, **kwargs)  # type: ignore[arg-type]
        opened.append(connection)
        return connection

    monkeypatch.setattr("sound_effects_studio.db.sqlite3.connect", spy)
    with pytest.raises(RuntimeError, match="newer"):
        Database(paths.database_path)
    assert len(opened) == 1
    with pytest.raises(sqlite3.ProgrammingError):
        opened[0].execute("SELECT 1")
    # The refused database is untouched.
    check = real_connect(paths.database_path)
    assert check.execute("PRAGMA user_version").fetchone()[0] == 2
    check.close()
