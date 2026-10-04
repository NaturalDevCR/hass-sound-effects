import re

import pytest
from pydantic import ValidationError

from sound_effects_studio.models import (
    AuditionTarget,
    Category,
    Job,
    OriginalInfo,
    Profile,
    Published,
    Recipe,
    SeasonCreate,
    SeasonUpdate,
    SelectionBatch,
    SelectionEvent,
    Settings,
    Sound,
    slugify,
    utcnow_iso,
)

pytestmark = pytest.mark.studio


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Intro Entrada", "intro_entrada"),
        ("León Infinito", "leon_infinito"),
        ("  --Hello,   World!--  ", "hello_world"),
        ("Ünïcödé", "unicode"),
        ("", "item"),
        ("!!!", "item"),
        ("a" * 80, "a" * 48),
        ("a" * 47 + " b", "a" * 47),
    ],
)
def test_slugify(text: str, expected: str) -> None:
    assert slugify(text) == expected


def test_utcnow_iso_format() -> None:
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", utcnow_iso())


def test_input_models_forbid_extra_fields() -> None:
    with pytest.raises(ValidationError):
        SeasonCreate.model_validate({"name": "x", "start": "01-01", "end": "01-02", "nope": 1})
    with pytest.raises(ValidationError):
        Recipe.model_validate({"gain": 1})


def test_recipe_ranges() -> None:
    for bad in ({"trim_start": -1}, {"gain_db": 25}, {"gain_db": -25}, {"fade_in": -0.1}):
        with pytest.raises(ValidationError):
            Recipe.model_validate(bad)


def test_selection_batch_limit() -> None:
    event = {
        "sound_id": "a",
        "category_id": "b",
        "season_id": "regular",
        "selected_at": "2026-10-03T12:00:00Z",
    }
    assert len(SelectionBatch.model_validate({"events": [event] * 500}).events) == 500
    with pytest.raises(ValidationError):
        SelectionBatch.model_validate({"events": [event] * 501})
    assert SelectionEvent.model_validate(event).sound_id == "a"


def test_json_shapes_match_shared_api() -> None:
    assert set(Recipe().model_dump()) == {
        "trim_start",
        "trim_end",
        "gain_db",
        "fade_in",
        "fade_out",
        "profile_id",
    }
    assert set(Category.model_fields) == {
        "id",
        "name",
        "icon",
        "color",
        "description",
        "sort_order",
        "default_profile_id",
    }
    assert set(Profile.model_fields) == {"id", "name", "target_lufs", "true_peak", "lra"}
    assert set(OriginalInfo.model_fields) == {
        "filename",
        "size",
        "format",
        "codec",
        "duration",
        "sample_rate",
        "channels",
    }
    assert set(Published.model_fields) == {
        "revision",
        "filename",
        "duration",
        "loudness_lufs",
        "true_peak_db",
        "size",
        "published_at",
        "mime_type",
    }
    assert set(Sound.model_fields) == {
        "id",
        "category_id",
        "title",
        "key",
        "tags",
        "seasons",
        "all_seasons",
        "enabled",
        "notes",
        "original",
        "recipe",
        "published",
        "status",
        "error",
        "selection_count",
        "last_selected_at",
        "created_at",
        "updated_at",
        "has_preview",
    }
    assert set(Job.model_fields) == {
        "id",
        "kind",
        "sound_id",
        "sound_title",
        "status",
        "progress",
        "error",
        "created_at",
        "started_at",
        "finished_at",
    }
    assert set(Settings().model_dump()) == {
        "max_upload_mb",
        "max_duration_s",
        "audition_targets",
        "media_base_url",
    }
    assert set(AuditionTarget.model_fields) == {"id", "label", "kind", "entity_id", "volume"}


def test_season_priority_is_bounded() -> None:
    for priority in (1001, -1001, 10**30):
        with pytest.raises(ValidationError):
            SeasonCreate(name="x", start="01-01", end="01-02", priority=priority)
        with pytest.raises(ValidationError):
            SeasonUpdate(priority=priority)
    assert SeasonCreate(name="x", start="01-01", end="01-02", priority=-1000).priority == -1000
    assert SeasonUpdate(priority=1000).priority == 1000


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-10-03T12:00:00Z", "2026-10-03T12:00:00Z"),
        ("2026-10-03T12:00:00z", "2026-10-03T12:00:00Z"),
        ("2026-10-03T12:00:00.987Z", "2026-10-03T12:00:00Z"),
        ("2026-10-03T14:30:00+02:00", "2026-10-03T12:30:00Z"),
        ("2026-10-03T12:00:00+00:00", "2026-10-03T12:00:00Z"),
        ("2026-10-03T12:00:00", "2026-10-03T12:00:00Z"),
    ],
)
def test_selected_at_is_normalized_to_utc(raw: str, expected: str) -> None:
    event = SelectionEvent(sound_id="a", category_id="b", season_id="regular", selected_at=raw)
    assert event.selected_at == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "t",
        "yesterday",
        "2026-13-01T00:00:00Z",
        "12:00:00Z",
        "0001-01-01T00:00:00+05:00",
        "9999-12-31T23:59:59-05:00",
    ],
)
def test_selected_at_rejects_non_timestamps(raw: str) -> None:
    with pytest.raises(ValidationError):
        SelectionEvent(sound_id="a", category_id="b", season_id="regular", selected_at=raw)
