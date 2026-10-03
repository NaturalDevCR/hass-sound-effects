from __future__ import annotations

from datetime import date

import pytest

from custom_components.sound_effects.catalog import parse_catalog
from custom_components.sound_effects.seasons import UnknownSeasonError, resolve_effective_season

pytestmark = pytest.mark.integration


def test_source_precedence(catalog_payload: dict[str, object]) -> None:
    catalog = parse_catalog(catalog_payload)
    day = date(2026, 10, 15)
    base = {
        "catalog": catalog,
        "day": day,
        "action_season": None,
        "override": None,
        "entity_state": None,
    }
    assert resolve_effective_season(
        **(base | {"action_season": "regular", "override": "halloween"})
    ) == ("regular", "action")
    assert resolve_effective_season(
        **(base | {"override": "halloween", "entity_state": "Regular"})
    ) == ("halloween", "override")
    assert resolve_effective_season(**(base | {"entity_state": "Regular"})) == ("regular", "entity")
    assert resolve_effective_season(**(base | {"override": "regular"})) == ("regular", "override")


@pytest.mark.parametrize("state", ["unknown", "unavailable", "", "Christmas"])
def test_ignored_entity_states_fall_through_to_calendar(
    catalog_payload: dict[str, object], state: str
) -> None:
    result = resolve_effective_season(
        parse_catalog(catalog_payload),
        date(2026, 10, 15),
        action_season=None,
        override=None,
        entity_state=state,
    )
    assert result == ("halloween", "calendar")


def test_no_calendar_match_uses_default(catalog_payload: dict[str, object]) -> None:
    assert resolve_effective_season(
        parse_catalog(catalog_payload),
        date(2026, 7, 1),
        action_season=None,
        override=None,
        entity_state=None,
    ) == ("regular", "default")


def test_unknown_action_is_error(catalog_payload: dict[str, object]) -> None:
    with pytest.raises(UnknownSeasonError):
        resolve_effective_season(
            parse_catalog(catalog_payload),
            date.today(),
            action_season="nope",
            override=None,
            entity_state=None,
        )
