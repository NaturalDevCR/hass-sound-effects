"""Pydantic models and small helpers shared across the Studio.

The JSON shapes mirror the types in the shared API reference (snake_case, ISO-8601 UTC
timestamps with a trailing ``Z``). Models that accept client input forbid unknown fields.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .errors import InvalidError

SoundStatus = Literal["processing", "ready", "rendering", "failed"]
JobKind = Literal["import", "publish", "preview"]
JobStatus = Literal["queued", "running", "done", "failed"]

_SLUG_MAX_LENGTH = 48
# Players and encoders may report a trim end a hair past the real duration.
_TRIM_END_TOLERANCE_S = 0.05
# Slack for float rounding when comparing fade lengths against the clip length.
_FADE_TOLERANCE_S = 1e-6
# Keeps season priorities well inside SQLite's INTEGER range.
_PRIORITY_LIMIT = 1000


def slugify(text: str) -> str:
    """Lowercase ASCII slug: accents stripped, runs of other characters become ``_``."""
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "_", folded.lower()).strip("_")
    return slug[:_SLUG_MAX_LENGTH].rstrip("_") or "item"


def utcnow_iso() -> str:
    """Current UTC time as ``2026-10-03T12:00:00Z``."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize_timestamp(value: str) -> str:
    """Parse an ISO-8601 timestamp (naive means UTC) and return it as ``YYYY-MM-DDTHH:MM:SSZ``."""
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise ValueError("must be an ISO-8601 timestamp") from None
    if parsed.tzinfo is not None:
        try:
            parsed = parsed.astimezone(UTC)
        except OverflowError:
            raise ValueError("timestamp out of range") from None
    return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")


# --- seasons ---------------------------------------------------------------------------------


class Season(BaseModel):
    id: str
    name: str
    color: str
    icon: str
    start: str | None
    end: str | None
    priority: int
    builtin: bool = False


class SeasonCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    name: str
    color: str = "#f59e0b"
    icon: str = "mdi:calendar-star"
    start: str
    end: str
    priority: int = Field(default=0, ge=-_PRIORITY_LIMIT, le=_PRIORITY_LIMIT)


class SeasonUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    color: str | None = None
    icon: str | None = None
    start: str | None = None
    end: str | None = None
    priority: int | None = Field(default=None, ge=-_PRIORITY_LIMIT, le=_PRIORITY_LIMIT)


# --- categories ------------------------------------------------------------------------------


class Category(BaseModel):
    id: str
    name: str
    icon: str
    color: str
    description: str
    sort_order: int
    default_profile_id: str | None


class CategoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    name: str
    icon: str = "mdi:music-note"
    color: str = "#8b5cf6"
    description: str = ""
    default_profile_id: str | None = None


class CategoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    icon: str | None = None
    color: str | None = None
    description: str | None = None
    default_profile_id: str | None = None


# --- normalization profiles ------------------------------------------------------------------


class Profile(BaseModel):
    id: str
    name: str
    target_lufs: float
    true_peak: float
    lra: float


class ProfileCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    name: str
    target_lufs: float = Field(ge=-30, le=-5)
    true_peak: float = Field(ge=-9, le=0)
    lra: float = Field(ge=1, le=20)


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    target_lufs: float | None = Field(default=None, ge=-30, le=-5)
    true_peak: float | None = Field(default=None, ge=-9, le=0)
    lra: float | None = Field(default=None, ge=1, le=20)


# --- sounds ----------------------------------------------------------------------------------


class Recipe(BaseModel):
    """How a published file is derived from the original; the defaults are the identity."""

    model_config = ConfigDict(extra="forbid")

    trim_start: float = Field(default=0.0, ge=0)
    trim_end: float | None = Field(default=None, ge=0)
    gain_db: float = Field(default=0.0, ge=-24, le=24)
    fade_in: float = Field(default=0.0, ge=0)
    fade_out: float = Field(default=0.0, ge=0)
    profile_id: str | None = None

    def is_identity(self) -> bool:
        return self == Recipe()

    def validate_for(self, duration: float) -> None:
        """Check the recipe against the original's duration (seconds)."""
        if self.trim_end is not None:
            if self.trim_start >= self.trim_end:
                raise InvalidError("Trim start must be before trim end.")
            if self.trim_end > duration + _TRIM_END_TOLERANCE_S:
                raise InvalidError(
                    f"Trim end ({self.trim_end:g}s) is past the end of the audio ({duration:g}s)."
                )
        end = duration if self.trim_end is None else min(self.trim_end, duration)
        length = end - self.trim_start
        if length <= 0:
            raise InvalidError(
                f"Trim start ({self.trim_start:g}s) is at or past the end of the audio"
                f" ({duration:g}s)."
            )
        if self.fade_in + self.fade_out > length + _FADE_TOLERANCE_S:
            raise InvalidError(
                f"Fade in plus fade out ({self.fade_in + self.fade_out:g}s) is longer than the"
                f" clip ({length:g}s)."
            )


class OriginalInfo(BaseModel):
    filename: str
    size: int
    format: str
    codec: str
    duration: float
    sample_rate: int
    channels: int


class Published(BaseModel):
    revision: int
    filename: str
    duration: float
    loudness_lufs: float | None
    true_peak_db: float | None
    size: int
    published_at: str
    mime_type: Literal["audio/mpeg"] = "audio/mpeg"


class Sound(BaseModel):
    id: str
    category_id: str
    title: str
    key: str
    tags: list[str]
    seasons: list[str]
    all_seasons: bool
    enabled: bool
    notes: str
    original: OriginalInfo | None
    recipe: Recipe
    published: Published | None
    status: SoundStatus
    error: str | None
    selection_count: int
    last_selected_at: str | None
    created_at: str
    updated_at: str
    has_preview: bool


class SoundUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    category_id: str | None = None
    key: str | None = None
    tags: list[str] | None = None
    seasons: list[str] | None = None
    all_seasons: bool | None = None
    enabled: bool | None = None
    notes: str | None = None


class BulkSet(BaseModel):
    """Metadata changes applied to many sounds; ``profile_id`` is handled by the API layer."""

    model_config = ConfigDict(extra="forbid")

    category_id: str | None = None
    seasons: list[str] | None = None
    all_seasons: bool | None = None
    add_tags: list[str] | None = None
    remove_tags: list[str] | None = None
    enabled: bool | None = None
    profile_id: str | None = None


# --- settings --------------------------------------------------------------------------------


class AuditionTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    kind: Literal["media_player", "script"]
    entity_id: str
    volume: float | None = None


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_upload_mb: int = Field(default=100, ge=1)
    max_duration_s: int = Field(default=600, ge=1)
    audition_targets: list[AuditionTarget] = Field(default_factory=list[AuditionTarget])
    media_base_url: str = ""


# --- integration traffic and jobs ------------------------------------------------------------


class SelectionEvent(BaseModel):
    sound_id: str
    category_id: str
    season_id: str
    selected_at: str

    @field_validator("selected_at")
    @classmethod
    def _normalize_selected_at(cls, value: str) -> str:
        return _normalize_timestamp(value)


class SelectionBatch(BaseModel):
    events: list[SelectionEvent] = Field(max_length=500)


class Job(BaseModel):
    id: str
    kind: JobKind
    sound_id: str
    sound_title: str
    status: JobStatus = "queued"
    progress: float = 0.0
    error: str | None = None
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
