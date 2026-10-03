from __future__ import annotations

import random

import pytest

from custom_components.sound_effects.catalog import parse_catalog
from custom_components.sound_effects.selection import (
    BagState,
    NoEligibleSoundError,
    draw,
    eligible_sounds,
    select,
)

pytestmark = pytest.mark.integration


def test_eligibility(catalog_payload: dict[str, object]) -> None:
    catalog = parse_catalog(catalog_payload)
    assert [s.id for s in eligible_sounds(catalog, "intro", "regular", [])] == [
        "fox",
        "universal",
        "pirates",
    ]
    assert [s.id for s in eligible_sounds(catalog, "bath", "regular", ["es"])] == ["bath_es"]
    assert [s.id for s in eligible_sounds(catalog, "lion", "halloween", [])] == ["roar"]


def test_draw_bag_rounds_and_membership_changes() -> None:
    rng = random.Random(4)
    bag = BagState([], [], None)
    picks: list[str] = []
    for _ in range(3):
        pick, bag = draw(bag, ["a", "b", "c"], rng)
        picks.append(pick)
    assert set(picks) == {"a", "b", "c"}
    for _ in range(200):
        previous = bag.last
        pick, bag = draw(bag, ["a", "b", "c"], rng)
        assert pick != previous
    pick, bag = draw(BagState(["a"], ["b"], "b"), ["a", "b", "c"], rng)
    assert pick in {"a", "c"}
    _, bag = draw(bag, ["a", "c"], rng)
    assert "b" not in bag.remaining and "b" not in bag.played
    assert draw(BagState([], [], None), ["only"], rng)[0] == "only"


def test_select_fallback_and_no_tag_relaxation(catalog_payload: dict[str, object]) -> None:
    catalog = parse_catalog(catalog_payload)
    outcome = select(
        catalog, category_id="bath", season_id="halloween", tags=[], bags={}, rng=random.Random(1)
    )
    assert (outcome.sound.id, outcome.season_fallback, outcome.requested_season) == (
        "bath_es",
        True,
        "halloween",
    )
    with pytest.raises(NoEligibleSoundError):
        select(
            catalog,
            category_id="bath",
            season_id="regular",
            tags=["fr"],
            bags={},
            rng=random.Random(1),
        )
    assert not select(
        catalog, category_id="lion", season_id="halloween", tags=[], bags={}, rng=random.Random(1)
    ).season_fallback


def test_select_does_not_mutate_bags(catalog_payload: dict[str, object]) -> None:
    catalog = parse_catalog(catalog_payload)
    bags = {"intro|regular|": BagState(["fox"], ["pirates"], "pirates")}
    before = bags["intro|regular|"].to_dict()
    select(
        catalog, category_id="intro", season_id="regular", tags=[], bags=bags, rng=random.Random(1)
    )
    assert bags["intro|regular|"].to_dict() == before
