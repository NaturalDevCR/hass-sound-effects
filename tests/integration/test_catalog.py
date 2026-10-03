from __future__ import annotations

import pytest

from custom_components.sound_effects.catalog import parse_catalog

pytestmark = pytest.mark.integration


def test_catalog_round_trip_and_casefold_name(catalog_payload: dict[str, object]) -> None:
    catalog = parse_catalog(catalog_payload)
    assert catalog.revision == 7
    assert catalog.find_category("león") is catalog.categories[1]
    assert catalog.find_season("HALLOWEEN") is catalog.seasons[1]


def test_parse_rejects_missing_sounds(catalog_payload: dict[str, object]) -> None:
    del catalog_payload["sounds"]
    with pytest.raises(ValueError):
        parse_catalog(catalog_payload)
