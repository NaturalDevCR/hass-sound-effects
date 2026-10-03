import sqlite3

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
