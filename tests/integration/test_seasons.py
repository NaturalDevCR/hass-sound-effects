from __future__ import annotations

from datetime import date

import pytest

from custom_components.sound_effects.catalog import parse_catalog
from custom_components.sound_effects.seasons import UnknownSeasonError, resolve_effective_season

pytestmark = pytest.mark.integration


def test_precedence(catalog_payload: dict[str, object]) -> None:
    catalog = parse_catalog(catalog_payload)
    args = {
        "catalog": catalog,
        "day": date(2026, 7, 1),
        "action_season": None,
        "override": None,
        "entity_state": None,
    }
    assert resolve_effective_season(**(args | {"action_season": "halloween"})) == (
        "halloween",
        "action",
    )
    assert resolve_effective_season(**(args | {"override": "halloween"})) == (
        "halloween",
        "override",
    )
    assert resolve_effective_season(**(args | {"entity_state": "Halloween"})) == (
        "halloween",
        "entity",
    )
    assert resolve_effective_season(**(args | {"day": date(2026, 10, 15)})) == (
        "halloween",
        "calendar",
    )
    assert resolve_effective_season(**args) == ("regular", "default")
    assert resolve_effective_season(**(args | {"override": "nope"})) == ("regular", "default")


def test_unknown_action_is_error(catalog_payload: dict[str, object]) -> None:
    with pytest.raises(UnknownSeasonError):
        resolve_effective_season(
            parse_catalog(catalog_payload),
            date.today(),
            action_season="nope",
            override=None,
            entity_state=None,
        )
