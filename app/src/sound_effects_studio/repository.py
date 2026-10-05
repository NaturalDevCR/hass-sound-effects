"""SQLite-backed storage for seasons, categories, profiles, sounds and settings.

The repository is synchronous. It is called from async handlers on the event loop and from
worker threads; every access goes through :attr:`Database.lock`.

Every write to seasons, categories or sounds bumps ``meta.catalog_revision`` inside the same
transaction and calls ``on_catalog_change(revision)`` after the commit. The exceptions are
selection counters, the transient ``processing``/``rendering`` statuses, the preview flag,
settings and profiles: none of them change what the integration has to re-read.
"""

from __future__ import annotations

import json
import logging
import re
import secrets
import sqlite3
from collections.abc import Callable, Generator, Iterable
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from .db import Database
from .errors import ConflictError, InvalidError, NotFoundError
from .models import (
    BulkSet,
    Category,
    CategoryCreate,
    CategoryUpdate,
    OriginalInfo,
    Profile,
    ProfileCreate,
    ProfileUpdate,
    Published,
    Recipe,
    Season,
    SeasonCreate,
    SeasonUpdate,
    SelectionEvent,
    Settings,
    Sound,
    SoundStatus,
    SoundUpdate,
    slugify,
    utcnow_iso,
)
from .seasons import REGULAR

_LOGGER = logging.getLogger(__name__)

_MMDD = re.compile(r"\d{2}-\d{2}")
_EXPLICIT_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,47}")

_SEASON_ORDER = "ORDER BY id = 'regular' DESC, priority DESC, name COLLATE NOCASE, id"
_CATEGORY_ORDER = "ORDER BY sort_order, name COLLATE NOCASE, id"

_Table = Literal["seasons", "categories", "profiles", "sounds"]


def _dumps(value: object) -> str:
    return json.dumps(value, separators=(",", ":"))


def _clean_text(label: str, value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise InvalidError(f"The {label} must not be empty.")
    return cleaned


def _resolve_id(explicit: str | None, name: str) -> str:
    """Use the explicit id when given (it must be URL-safe), else slugify the name."""
    if explicit is None:
        return slugify(name)
    candidate = explicit.strip()
    if not _EXPLICIT_ID.fullmatch(candidate):
        raise InvalidError(
            f"Invalid id '{explicit}': use 1-48 lowercase letters, digits, '_' or '-'."
        )
    return candidate


def _validate_mmdd(label: str, value: str | None) -> str:
    if value is None:
        raise InvalidError(f"The season {label} date is required (MM-DD).")
    if not _MMDD.fullmatch(value):
        raise InvalidError(f"Invalid season {label} date '{value}': expected MM-DD.")
    try:
        # 2000 is a leap year, so 02-29 is accepted.
        date.fromisoformat(f"2000-{value}")
    except ValueError:
        raise InvalidError(f"Invalid season {label} date '{value}': no such day.") from None
    return value


def _normalize_tags(tags: Iterable[str]) -> list[str]:
    return sorted({slugify(tag) for tag in tags if tag.strip()})


def _dedupe(items: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(items))


# --- row access ------------------------------------------------------------------------------


def _get_row(conn: sqlite3.Connection, table: _Table, label: str, entity_id: str) -> sqlite3.Row:
    row: sqlite3.Row | None = conn.execute(
        f"SELECT * FROM {table} WHERE id = ?", (entity_id,)
    ).fetchone()
    if row is None:
        raise NotFoundError(f"{label} '{entity_id}' not found.")
    return row


def _season_from_row(row: sqlite3.Row) -> Season:
    return Season(
        id=row["id"],
        name=row["name"],
        color=row["color"],
        icon=row["icon"],
        start=row["start"],
        end=row["end"],
        priority=row["priority"],
        builtin=bool(row["builtin"]),
    )


def _category_from_row(row: sqlite3.Row) -> Category:
    return Category(
        id=row["id"],
        name=row["name"],
        icon=row["icon"],
        color=row["color"],
        description=row["description"],
        sort_order=row["sort_order"],
        default_profile_id=row["default_profile_id"],
    )


def _profile_from_row(row: sqlite3.Row) -> Profile:
    return Profile(
        id=row["id"],
        name=row["name"],
        target_lufs=row["target_lufs"],
        true_peak=row["true_peak"],
        lra=row["lra"],
    )


def _sound_from_row(row: sqlite3.Row) -> Sound:
    original: str | None = row["original"]
    published: str | None = row["published"]
    return Sound(
        id=row["id"],
        category_id=row["category_id"],
        title=row["title"],
        key=row["key"],
        tags=json.loads(row["tags"]),
        seasons=json.loads(row["seasons"]),
        all_seasons=bool(row["all_seasons"]),
        enabled=bool(row["enabled"]),
        notes=row["notes"],
        original=OriginalInfo.model_validate_json(original) if original else None,
        recipe=Recipe.model_validate_json(row["recipe"]),
        published=Published.model_validate_json(published) if published else None,
        status=row["status"],
        error=row["error"],
        selection_count=row["selection_count"],
        last_selected_at=row["last_selected_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        has_preview=bool(row["has_preview"]),
    )


def _get_sound(conn: sqlite3.Connection, sound_id: str) -> Sound:
    return _sound_from_row(_get_row(conn, "sounds", "Sound", sound_id))


def _list_categories(conn: sqlite3.Connection) -> list[Category]:
    rows = conn.execute(f"SELECT * FROM categories {_CATEGORY_ORDER}").fetchall()
    return [_category_from_row(row) for row in rows]


# --- validation shared by several writes -----------------------------------------------------


def _check_profile(conn: sqlite3.Connection, profile_id: str | None) -> None:
    if profile_id is None:
        return
    if conn.execute("SELECT 1 FROM profiles WHERE id = ?", (profile_id,)).fetchone() is None:
        raise InvalidError(f"Profile '{profile_id}' does not exist.")


def _check_placement(
    conn: sqlite3.Connection, category_id: str, seasons: list[str], all_seasons: bool
) -> None:
    if conn.execute("SELECT 1 FROM categories WHERE id = ?", (category_id,)).fetchone() is None:
        raise InvalidError(f"Category '{category_id}' does not exist.")
    known = {row["id"] for row in conn.execute("SELECT id FROM seasons").fetchall()}
    unknown = [season for season in seasons if season not in known]
    if unknown:
        raise InvalidError(f"Unknown season(s): {', '.join(unknown)}.")
    if not seasons and not all_seasons:
        raise InvalidError("Pick at least one season, or enable all seasons.")


def _sounds_using_profile(conn: sqlite3.Connection, profile_id: str) -> list[str]:
    rows = conn.execute(
        "SELECT id FROM sounds WHERE json_extract(recipe, '$.profile_id') = ? ORDER BY rowid",
        (profile_id,),
    ).fetchall()
    return [row["id"] for row in rows]


def _update_sound_fields(
    conn: sqlite3.Connection,
    sound: Sound,
    *,
    title: str | None = None,
    category_id: str | None = None,
    key: str | None = None,
    tags: Iterable[str] | None = None,
    seasons: Iterable[str] | None = None,
    all_seasons: bool | None = None,
    enabled: bool | None = None,
    notes: str | None = None,
) -> None:
    """Apply the given metadata (None means unchanged) after validating the result.

    Nothing is written when the result equals the sound as it is.
    """
    new_title = _clean_text("title", title) if title is not None else sound.title
    new_key = _clean_text("key", key) if key is not None else sound.key
    new_category = category_id if category_id is not None else sound.category_id
    new_tags = _normalize_tags(tags) if tags is not None else sound.tags
    new_seasons = _dedupe(seasons) if seasons is not None else sound.seasons
    new_all_seasons = all_seasons if all_seasons is not None else sound.all_seasons
    new_enabled = enabled if enabled is not None else sound.enabled
    new_notes = notes if notes is not None else sound.notes
    _check_placement(conn, new_category, new_seasons, new_all_seasons)
    unchanged = (new_title, new_key, new_category, new_tags, new_seasons, new_all_seasons) == (
        sound.title,
        sound.key,
        sound.category_id,
        sound.tags,
        sound.seasons,
        sound.all_seasons,
    ) and (new_enabled, new_notes) == (sound.enabled, sound.notes)
    if unchanged:
        return
    conn.execute(
        "UPDATE sounds SET title = ?, key = ?, category_id = ?, tags = ?, seasons = ?,"
        " all_seasons = ?, enabled = ?, notes = ?, updated_at = ? WHERE id = ?",
        (
            new_title,
            new_key,
            new_category,
            _dumps(new_tags),
            _dumps(new_seasons),
            int(new_all_seasons),
            int(new_enabled),
            new_notes,
            utcnow_iso(),
            sound.id,
        ),
    )


def _increment_revision(conn: sqlite3.Connection) -> int:
    revision = _read_revision(conn) + 1
    conn.execute("UPDATE meta SET value = ? WHERE key = 'catalog_revision'", (str(revision),))
    return revision


def _read_revision(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT value FROM meta WHERE key = 'catalog_revision'").fetchone()
    return int(row["value"]) if row else 0


# Superseded or deleted publications stay on disk this long after retirement, as a
# safety net for cached catalogs (Home Assistant may fail to persist its snapshot).
RETIREMENT_GRACE = timedelta(days=7)


class Repository:
    def __init__(
        self, db: Database, on_catalog_change: Callable[[int], None] | None = None
    ) -> None:
        self._db = db
        self._on_catalog_change = on_catalog_change

    # --- plumbing ---------------------------------------------------------------------------

    @contextmanager
    def _read(self) -> Generator[sqlite3.Connection]:
        with self._db.lock:
            yield self._db.connection

    @contextmanager
    def _write(self, *, bump: bool = True) -> Generator[sqlite3.Connection]:
        """Run a write transaction; bump the catalog revision and notify after the commit.

        The bump is skipped when the block modified no rows (a no-op update).
        """
        revision: int | None = None
        with self._db.transaction() as conn:
            changes_before = conn.total_changes
            yield conn
            if bump and conn.total_changes != changes_before:
                revision = _increment_revision(conn)
        if revision is not None and self._on_catalog_change is not None:
            try:
                self._on_catalog_change(revision)
            except Exception:
                _LOGGER.exception("Catalog change listener failed for revision %s", revision)

    # --- seasons ----------------------------------------------------------------------------

    def list_seasons(self) -> list[Season]:
        with self._read() as conn:
            rows = conn.execute(f"SELECT * FROM seasons {_SEASON_ORDER}").fetchall()
        return [_season_from_row(row) for row in rows]

    def get_season(self, season_id: str) -> Season:
        with self._read() as conn:
            return _season_from_row(_get_row(conn, "seasons", "Season", season_id))

    def create_season(self, data: SeasonCreate) -> Season:
        name = _clean_text("season name", data.name)
        season_id = _resolve_id(data.id, name)
        start = _validate_mmdd("start", data.start)
        end = _validate_mmdd("end", data.end)
        with self._write() as conn:
            if conn.execute("SELECT 1 FROM seasons WHERE id = ?", (season_id,)).fetchone():
                raise ConflictError(f"Season '{season_id}' already exists.")
            conn.execute(
                'INSERT INTO seasons (id, name, color, icon, start, "end", priority, builtin)'
                " VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
                (season_id, name, data.color, data.icon, start, end, data.priority),
            )
            return _season_from_row(_get_row(conn, "seasons", "Season", season_id))

    def update_season(self, season_id: str, data: SeasonUpdate) -> Season:
        with self._write() as conn:
            current = _season_from_row(_get_row(conn, "seasons", "Season", season_id))
            name = _clean_text("season name", data.name) if data.name is not None else current.name
            color = data.color if data.color is not None else current.color
            icon = data.icon if data.icon is not None else current.icon
            priority = data.priority if data.priority is not None else current.priority
            start = data.start if "start" in data.model_fields_set else current.start
            end = data.end if "end" in data.model_fields_set else current.end
            if current.builtin:
                if (start, end, priority) != (current.start, current.end, current.priority):
                    raise InvalidError(
                        "The regular season only allows changing its name, color and icon."
                    )
            else:
                start = _validate_mmdd("start", start)
                end = _validate_mmdd("end", end)
            conn.execute(
                'UPDATE seasons SET name = ?, color = ?, icon = ?, start = ?, "end" = ?,'
                " priority = ? WHERE id = ?",
                (name, color, icon, start, end, priority, season_id),
            )
            return _season_from_row(_get_row(conn, "seasons", "Season", season_id))

    def delete_season(self, season_id: str) -> None:
        with self._write() as conn:
            season = _season_from_row(_get_row(conn, "seasons", "Season", season_id))
            if season.builtin:
                raise InvalidError("The regular season cannot be deleted.")
            now = utcnow_iso()
            for row in conn.execute("SELECT id, seasons FROM sounds").fetchall():
                seasons: list[str] = json.loads(row["seasons"])
                if season_id not in seasons:
                    continue
                remaining = [item for item in seasons if item != season_id] or [REGULAR]
                conn.execute(
                    "UPDATE sounds SET seasons = ?, updated_at = ? WHERE id = ?",
                    (_dumps(remaining), now, row["id"]),
                )
            conn.execute("DELETE FROM seasons WHERE id = ?", (season_id,))

    # --- categories -------------------------------------------------------------------------

    def list_categories(self) -> list[Category]:
        with self._read() as conn:
            return _list_categories(conn)

    def get_category(self, category_id: str) -> Category:
        with self._read() as conn:
            return _category_from_row(_get_row(conn, "categories", "Category", category_id))

    def create_category(self, data: CategoryCreate) -> Category:
        name = _clean_text("category name", data.name)
        category_id = _resolve_id(data.id, name)
        with self._write() as conn:
            if conn.execute("SELECT 1 FROM categories WHERE id = ?", (category_id,)).fetchone():
                raise ConflictError(f"Category '{category_id}' already exists.")
            _check_profile(conn, data.default_profile_id)
            sort_order: int = conn.execute(
                "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM categories"
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO categories (id, name, icon, color, description, sort_order,"
                " default_profile_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    category_id,
                    name,
                    data.icon,
                    data.color,
                    data.description,
                    sort_order,
                    data.default_profile_id,
                ),
            )
            return _category_from_row(_get_row(conn, "categories", "Category", category_id))

    def update_category(self, category_id: str, data: CategoryUpdate) -> Category:
        with self._write() as conn:
            current = _category_from_row(_get_row(conn, "categories", "Category", category_id))
            name = (
                _clean_text("category name", data.name) if data.name is not None else current.name
            )
            icon = data.icon if data.icon is not None else current.icon
            color = data.color if data.color is not None else current.color
            description = data.description if data.description is not None else current.description
            default_profile_id = (
                data.default_profile_id
                if "default_profile_id" in data.model_fields_set
                else current.default_profile_id
            )
            _check_profile(conn, default_profile_id)
            conn.execute(
                "UPDATE categories SET name = ?, icon = ?, color = ?, description = ?,"
                " default_profile_id = ? WHERE id = ?",
                (name, icon, color, description, default_profile_id, category_id),
            )
            return _category_from_row(_get_row(conn, "categories", "Category", category_id))

    def delete_category(self, category_id: str) -> None:
        with self._write() as conn:
            _get_row(conn, "categories", "Category", category_id)
            count: int = conn.execute(
                "SELECT COUNT(*) FROM sounds WHERE category_id = ?", (category_id,)
            ).fetchone()[0]
            if count:
                raise ConflictError(f"Category '{category_id}' still has {count} sound(s).")
            conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))

    def reorder_categories(self, ids: list[str]) -> list[Category]:
        """Put the listed categories first, in order; any unlisted ones follow as they were."""
        if len(set(ids)) != len(ids):
            raise InvalidError("The category order lists the same category twice.")
        with self._write() as conn:
            existing = [category.id for category in _list_categories(conn)]
            unknown = [category_id for category_id in ids if category_id not in existing]
            if unknown:
                raise NotFoundError(f"Category '{unknown[0]}' not found.")
            listed = set(ids)
            ordered = [
                *ids,
                *(category_id for category_id in existing if category_id not in listed),
            ]
            conn.executemany(
                "UPDATE categories SET sort_order = ? WHERE id = ?",
                [(position, category_id) for position, category_id in enumerate(ordered)],
            )
            return _list_categories(conn)

    # --- profiles ---------------------------------------------------------------------------

    def list_profiles(self) -> list[Profile]:
        with self._read() as conn:
            rows = conn.execute("SELECT * FROM profiles ORDER BY rowid").fetchall()
        return [_profile_from_row(row) for row in rows]

    def get_profile(self, profile_id: str) -> Profile:
        with self._read() as conn:
            return _profile_from_row(_get_row(conn, "profiles", "Profile", profile_id))

    def create_profile(self, data: ProfileCreate) -> Profile:
        name = _clean_text("profile name", data.name)
        profile_id = _resolve_id(data.id, name)
        with self._write(bump=False) as conn:
            if conn.execute("SELECT 1 FROM profiles WHERE id = ?", (profile_id,)).fetchone():
                raise ConflictError(f"Profile '{profile_id}' already exists.")
            conn.execute(
                "INSERT INTO profiles (id, name, target_lufs, true_peak, lra)"
                " VALUES (?, ?, ?, ?, ?)",
                (profile_id, name, data.target_lufs, data.true_peak, data.lra),
            )
            return _profile_from_row(_get_row(conn, "profiles", "Profile", profile_id))

    def update_profile(self, profile_id: str, data: ProfileUpdate) -> tuple[Profile, list[str]]:
        """Update a profile; also return the sounds whose recipe uses it (to be re-rendered)."""
        with self._write(bump=False) as conn:
            current = _profile_from_row(_get_row(conn, "profiles", "Profile", profile_id))
            name = _clean_text("profile name", data.name) if data.name is not None else current.name
            target_lufs = data.target_lufs if data.target_lufs is not None else current.target_lufs
            true_peak = data.true_peak if data.true_peak is not None else current.true_peak
            lra = data.lra if data.lra is not None else current.lra
            conn.execute(
                "UPDATE profiles SET name = ?, target_lufs = ?, true_peak = ?, lra = ?"
                " WHERE id = ?",
                (name, target_lufs, true_peak, lra, profile_id),
            )
            profile = _profile_from_row(_get_row(conn, "profiles", "Profile", profile_id))
            return profile, _sounds_using_profile(conn, profile_id)

    def delete_profile(self, profile_id: str) -> None:
        with self._write(bump=False) as conn:
            _get_row(conn, "profiles", "Profile", profile_id)
            if _sounds_using_profile(conn, profile_id):
                raise ConflictError(f"Profile '{profile_id}' is used by a sound recipe.")
            if conn.execute(
                "SELECT 1 FROM categories WHERE default_profile_id = ?", (profile_id,)
            ).fetchone():
                raise ConflictError(f"Profile '{profile_id}' is the default of a category.")
            conn.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))

    def sounds_using_profile(self, profile_id: str) -> list[str]:
        with self._read() as conn:
            return _sounds_using_profile(conn, profile_id)

    # --- sounds -----------------------------------------------------------------------------

    def list_sounds(self) -> list[Sound]:
        with self._read() as conn:
            rows = conn.execute("SELECT * FROM sounds ORDER BY rowid").fetchall()
        return [_sound_from_row(row) for row in rows]

    def get_sound(self, sound_id: str) -> Sound:
        with self._read() as conn:
            return _get_sound(conn, sound_id)

    def create_sound(
        self,
        *,
        category_id: str,
        title: str,
        key: str,
        tags: list[str],
        seasons: list[str],
        all_seasons: bool,
        recipe: Recipe,
        original: OriginalInfo | None,
    ) -> Sound:
        clean_title = _clean_text("title", title)
        clean_key = _clean_text("key", key)
        season_ids = _dedupe(seasons)
        sound_id = secrets.token_hex(6)
        now = utcnow_iso()
        with self._write() as conn:
            _check_placement(conn, category_id, season_ids, all_seasons)
            _check_profile(conn, recipe.profile_id)
            conn.execute(
                "INSERT INTO sounds (id, category_id, title, key, tags, seasons, all_seasons,"
                " original, recipe, status, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'processing', ?, ?)",
                (
                    sound_id,
                    category_id,
                    clean_title,
                    clean_key,
                    _dumps(_normalize_tags(tags)),
                    _dumps(season_ids),
                    int(all_seasons),
                    original.model_dump_json() if original else None,
                    recipe.model_dump_json(),
                    now,
                    now,
                ),
            )
            return _get_sound(conn, sound_id)

    def update_sound(self, sound_id: str, data: SoundUpdate) -> Sound:
        with self._write() as conn:
            sound = _get_sound(conn, sound_id)
            _update_sound_fields(
                conn,
                sound,
                title=data.title,
                category_id=data.category_id,
                key=data.key,
                tags=data.tags,
                seasons=data.seasons,
                all_seasons=data.all_seasons,
                enabled=data.enabled,
                notes=data.notes,
            )
            return _get_sound(conn, sound_id)

    def set_recipe(self, sound_id: str, recipe: Recipe) -> Sound:
        with self._write() as conn:
            _get_row(conn, "sounds", "Sound", sound_id)
            _check_profile(conn, recipe.profile_id)
            conn.execute(
                "UPDATE sounds SET recipe = ?, updated_at = ? WHERE id = ?",
                (recipe.model_dump_json(), utcnow_iso(), sound_id),
            )
            return _get_sound(conn, sound_id)

    def set_original(self, sound_id: str, original: OriginalInfo) -> Sound:
        with self._write() as conn:
            _get_row(conn, "sounds", "Sound", sound_id)
            conn.execute(
                "UPDATE sounds SET original = ?, updated_at = ? WHERE id = ?",
                (original.model_dump_json(), utcnow_iso(), sound_id),
            )
            return _get_sound(conn, sound_id)

    def set_status(self, sound_id: str, status: SoundStatus, error: str | None = None) -> Sound:
        with self._write(bump=status in ("ready", "failed")) as conn:
            _get_row(conn, "sounds", "Sound", sound_id)
            conn.execute(
                "UPDATE sounds SET status = ?, error = ?, updated_at = ? WHERE id = ?",
                (status, error, utcnow_iso(), sound_id),
            )
            return _get_sound(conn, sound_id)

    def set_published(self, sound_id: str, published: Published) -> Sound:
        """Record a new published revision; the sound becomes ready and its error is cleared."""
        with self._write() as conn:
            sound = _get_sound(conn, sound_id)
            if sound.published is not None and sound.published.filename != published.filename:
                _retire_files(conn, sound_id, [sound.published.filename])
            conn.execute(
                "UPDATE sounds SET published = ?, status = 'ready', error = NULL,"
                " updated_at = ? WHERE id = ?",
                (published.model_dump_json(), utcnow_iso(), sound_id),
            )
            return _get_sound(conn, sound_id)

    def set_has_preview(self, sound_id: str, value: bool) -> None:
        with self._write(bump=False) as conn:
            _get_row(conn, "sounds", "Sound", sound_id)
            conn.execute("UPDATE sounds SET has_preview = ? WHERE id = ?", (int(value), sound_id))

    def delete_sound(self, sound_id: str, filenames: Iterable[str] = ()) -> None:
        with self._write() as conn:
            sound = _get_sound(conn, sound_id)
            publications = set(filenames)
            if sound.published is not None:
                publications.add(sound.published.filename)
            _retire_files(conn, sound_id, publications)
            conn.execute("DELETE FROM sounds WHERE id = ?", (sound_id,))

    def mark_catalog_served(self) -> None:
        """Remember that some catalog left the App, so grace-only cleanup no longer applies."""
        with self._write(bump=False) as conn:
            conn.execute("INSERT OR IGNORE INTO meta VALUES ('catalog_served', '1')")

    def acknowledge_catalog(self, revision: int) -> None:
        """Track the greatest served revision without changing the catalog itself."""
        with self._write(bump=False) as conn:
            conn.execute(
                "INSERT INTO meta VALUES ('catalog_revision_acknowledged', ?)"
                " ON CONFLICT(key) DO UPDATE SET value ="
                " CAST(MAX(CAST(value AS INTEGER), CAST(excluded.value AS INTEGER)) AS TEXT)",
                (str(revision),),
            )
            conn.execute(
                "INSERT INTO meta VALUES ('catalog_acknowledged_at', ?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (utcnow_iso(),),
            )

    def cleanup_retired_files(self, remove_file: Callable[[str], None]) -> list[str]:
        """Reclaim acknowledged publications after the retirement grace period.

        Once any catalog has been served, a retired file waits for the integration to
        acknowledge the revision that retired it; only an App that never served a catalog
        (no integration) falls back to the grace period alone.

        Hold the write lock through removal so a concurrent publish cannot make a
        candidate current between checking its reference and unlinking the file.
        """
        removed: list[str] = []
        with self._write(bump=False) as conn:
            row = conn.execute(
                "SELECT value FROM meta WHERE key = 'catalog_revision_acknowledged'"
            ).fetchone()
            acknowledged = int(row[0]) if row is not None else None
            served = (
                conn.execute("SELECT 1 FROM meta WHERE key = 'catalog_served'").fetchone()
                is not None
            )
            current: set[str] = set()
            for row in conn.execute("SELECT * FROM sounds WHERE published IS NOT NULL"):
                published = _sound_from_row(row).published
                if published is not None:
                    current.add(published.filename)
            cutoff = datetime.now(UTC) - RETIREMENT_GRACE
            for retired in conn.execute("SELECT * FROM retired_files").fetchall():
                filename = retired["filename"]
                if filename in current:
                    continue
                if acknowledged is None and served:
                    continue
                if acknowledged is not None and retired["retired_at_revision"] > acknowledged:
                    continue
                if datetime.fromisoformat(retired["retired_at"]) >= cutoff:
                    continue
                remove_file(filename)
                conn.execute("DELETE FROM retired_files WHERE filename = ?", (filename,))
                removed.append(filename)
        return removed

    def bulk_update(self, ids: list[str], data: BulkSet) -> int:
        """Apply metadata changes to many sounds at once; returns how many sounds matched.

        Unknown ids are skipped. The whole batch is validated and applied atomically, and
        nothing is written (or bumped) when no sound would actually change. The recipe
        profile (``data.profile_id``) is handled by the API layer, not here.
        """
        added = _normalize_tags(data.add_tags or [])
        removed = set(_normalize_tags(data.remove_tags or []))
        with self._write() as conn:
            matched = 0
            for sound_id in _dedupe(ids):
                row = conn.execute("SELECT * FROM sounds WHERE id = ?", (sound_id,)).fetchone()
                if row is None:
                    continue
                matched += 1
                sound = _sound_from_row(row)
                tags: list[str] | None = None
                if added or removed:
                    tags = [tag for tag in {*sound.tags, *added} if tag not in removed]
                _update_sound_fields(
                    conn,
                    sound,
                    category_id=data.category_id,
                    seasons=data.seasons,
                    all_seasons=data.all_seasons,
                    enabled=data.enabled,
                    tags=tags,
                )
            return matched

    def record_selections(self, events: list[SelectionEvent]) -> None:
        """Count selections reported by the integration; events for deleted sounds are dropped."""
        if not events:
            return
        with self._write(bump=False) as conn:
            conn.executemany(
                "UPDATE sounds SET selection_count = selection_count + 1,"
                " last_selected_at = CASE WHEN last_selected_at IS NULL OR last_selected_at < ?"
                " THEN ? ELSE last_selected_at END WHERE id = ?",
                [(event.selected_at, event.selected_at, event.sound_id) for event in events],
            )

    # --- settings and catalog ---------------------------------------------------------------

    def get_settings(self) -> Settings:
        with self._read() as conn:
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
        stored = {row["key"]: json.loads(row["value"]) for row in rows}
        # Older Studio versions allowed a media-player volume but never applied it.
        for target in stored.get("audition_targets", []):
            if target.get("kind") == "media_player":
                target["volume"] = None
        return Settings.model_validate(
            {k: v for k, v in stored.items() if k in Settings.model_fields}
        )

    def update_settings(self, data: Settings) -> Settings:
        with self._write(bump=False) as conn:
            conn.executemany(
                "INSERT INTO settings (key, value) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                [(key, _dumps(value)) for key, value in data.model_dump(mode="json").items()],
            )
        return self.get_settings()

    def catalog_revision(self) -> int:
        with self._read() as conn:
            return _read_revision(conn)

    def catalog_document(self) -> dict[str, object]:
        """The catalog served to the integration: published sounds only, no internal fields."""
        with self._read() as conn:
            revision = _read_revision(conn)
            seasons = [
                _season_from_row(row)
                for row in conn.execute(f"SELECT * FROM seasons {_SEASON_ORDER}").fetchall()
            ]
            categories = _list_categories(conn)
            sounds = [
                _sound_from_row(row)
                for row in conn.execute(
                    "SELECT * FROM sounds WHERE published IS NOT NULL ORDER BY rowid"
                ).fetchall()
            ]
        catalog_sounds: list[dict[str, object]] = []
        for sound in sounds:
            if sound.published is None:
                continue
            catalog_sounds.append(
                {
                    "id": sound.id,
                    "category_id": sound.category_id,
                    "title": sound.title,
                    "key": sound.key,
                    "tags": sound.tags,
                    "seasons": sound.seasons,
                    "all_seasons": sound.all_seasons,
                    "enabled": sound.enabled,
                    "published": {
                        "revision": sound.published.revision,
                        "filename": sound.published.filename,
                        "duration": sound.published.duration,
                        "mime_type": sound.published.mime_type,
                    },
                }
            )
        return {
            "revision": revision,
            "generated_at": utcnow_iso(),
            "seasons": [season.model_dump(exclude={"builtin"}) for season in seasons],
            "categories": [
                category.model_dump(exclude={"default_profile_id"}) for category in categories
            ],
            "sounds": catalog_sounds,
        }


def _retire_files(conn: sqlite3.Connection, sound_id: str, filenames: Iterable[str]) -> None:
    conn.executemany(
        "INSERT OR IGNORE INTO retired_files VALUES (?, ?, ?, ?)",
        [(filename, sound_id, _read_revision(conn) + 1, utcnow_iso()) for filename in filenames],
    )
