from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from custom_components.sound_effects.catalog import EMPTY_CATALOG, parse_catalog

pytestmark = pytest.mark.integration


def test_parsed_fields_and_lookups(catalog_payload: dict[str, Any]) -> None:
    catalog = parse_catalog(catalog_payload)
    assert catalog.revision == 7
    sound = catalog.sounds[0]
    assert sound.tags == () and isinstance(sound.tags, tuple)
    assert sound.seasons == ("regular",) and isinstance(sound.seasons, tuple)
    assert sound.published.revision == 1
    assert sound.published.filename == "fox-r1.mp3"
    assert sound.published.duration == 2.5
    assert sound.published.mime_type == "audio/mpeg"
    assert catalog.categories[1].id == "lion"
    assert catalog.categories[1].sort_order == 1
    assert catalog.seasons[1].start == "10-01"
    assert catalog.seasons[1].end == "10-31"
    assert catalog.seasons[1].priority == 10
    assert catalog.find_category("león") is catalog.categories[1]
    assert catalog.find_season("HALLOWEEN") is catalog.seasons[1]
    assert catalog.find_category("absent") is None
    assert catalog.find_season("absent") is None


def test_exact_id_precedes_casefold_name_match() -> None:
    payload: dict[str, Any] = {
        "revision": 1,
        "seasons": [
            {
                "id": "regular",
                "name": "Regular",
                "color": "",
                "icon": "",
                "start": None,
                "end": None,
                "priority": 0,
            }
        ],
        "categories": [
            {
                "id": "different",
                "name": "same",
                "icon": "",
                "color": "",
                "description": "",
                "sort_order": 1,
            },
            {
                "id": "same",
                "name": "Other",
                "icon": "",
                "color": "",
                "description": "",
                "sort_order": 0,
            },
        ],
        "sounds": [],
    }
    assert parse_catalog(payload).find_category("same").id == "same"  # type: ignore[union-attr]


def test_empty_catalog() -> None:
    assert EMPTY_CATALOG.revision == 0
    assert [season.id for season in EMPTY_CATALOG.seasons] == ["regular"]
    assert EMPTY_CATALOG.categories == () and EMPTY_CATALOG.sounds == ()


@pytest.mark.parametrize(
    "mutation",
    ["missing_sounds", "bool_revision", "non_string_tag", "missing_published", "negative_duration"],
)
def test_invalid_catalog_inputs(catalog_payload: dict[str, Any], mutation: str) -> None:
    payload = deepcopy(catalog_payload)
    if mutation == "missing_sounds":
        del payload["sounds"]
    elif mutation == "bool_revision":
        payload["revision"] = True
    elif mutation == "non_string_tag":
        payload["sounds"][0]["tags"] = [4]
    elif mutation == "missing_published":
        del payload["sounds"][0]["published"]
    else:
        payload["sounds"][0]["published"]["duration"] = -1
    with pytest.raises(ValueError):
        parse_catalog(payload)


@pytest.mark.parametrize(
    "invalid",
    ["99-99", "1-01", "٠١-٠١"],
)
def test_invalid_season_dates(catalog_payload: dict[str, Any], invalid: str) -> None:
    payload = deepcopy(catalog_payload)
    payload["seasons"][1]["start"] = invalid
    with pytest.raises(ValueError):
        parse_catalog(payload)


@pytest.mark.parametrize("duration", [float("nan"), float("inf"), True, 10**400])
def test_invalid_durations(catalog_payload: dict[str, Any], duration: int | float) -> None:
    payload = deepcopy(catalog_payload)
    payload["sounds"][0]["published"]["duration"] = duration
    with pytest.raises(ValueError):
        parse_catalog(payload)


def test_integer_duration_is_coerced_to_float(catalog_payload: dict[str, Any]) -> None:
    payload = deepcopy(catalog_payload)
    payload["sounds"][0]["published"]["duration"] = 3
    assert parse_catalog(payload).sounds[0].published.duration == 3.0
    assert isinstance(parse_catalog(payload).sounds[0].published.duration, float)
