from __future__ import annotations

import random

import pytest

from custom_components.sound_effects.catalog import parse_catalog
from custom_components.sound_effects.selection import (
    BagState,
    NoEligibleSoundError,
    bag_key,
    draw,
    eligible_sounds,
    select,
)

pytestmark = pytest.mark.integration


def test_eligibility_and_tags(catalog_payload: dict[str, object]) -> None:
    catalog = parse_catalog(catalog_payload)
    assert [s.id for s in eligible_sounds(catalog, "intro", "regular", [])] == [
        "fox",
        "universal",
        "pirates",
    ]
    assert [s.id for s in eligible_sounds(catalog, "bath", "regular", ["es"])] == ["bath_es"]
    assert [s.id for s in eligible_sounds(catalog, "lion", "halloween", [])] == ["roar"]
    outcome = select(
        catalog,
        category_id="bath",
        season_id="regular",
        tags=["es"],
        bags={},
        rng=random.Random(99),
    )
    assert outcome.sound.id == "bath_es"
    assert outcome.season_id == "regular"
    assert outcome.bag_key == "bath|regular|es"


def test_draw_rounds_avoid_previous_pick_and_reshuffle() -> None:
    rng = random.Random(4)
    bag = BagState([], [], None)
    picks = []
    for _ in range(3):
        pick, bag = draw(bag, ["a", "b", "c"], rng)
        picks.append(pick)
    assert set(picks) == {"a", "b", "c"}
    for _ in range(200):
        previous = bag.last
        pick, bag = draw(bag, ["a", "b", "c"], rng)
        assert pick != previous


def test_draw_single_sound_repeats() -> None:
    pick, _ = draw(BagState(remaining=[], played=["only"], last="only"), ["only"], random.Random(1))
    assert pick == "only"


def test_new_eligible_id_joins_current_round() -> None:
    pick, _ = draw(BagState(["a"], ["b"], "b"), ["a", "b", "c"], random.Random(1))
    assert pick in {"a", "c"}


def test_removed_id_disappears() -> None:
    _, bag = draw(BagState(["a"], ["b"], "b"), ["a"], random.Random(1))
    assert "b" not in bag.remaining and "b" not in bag.played


def test_season_fallback_keeps_requested_season(catalog_payload: dict[str, object]) -> None:
    outcome = select(
        parse_catalog(catalog_payload),
        category_id="bath",
        season_id="halloween",
        tags=[],
        bags={},
        rng=random.Random(1),
    )
    assert outcome.sound.id in {"bath_es", "bath_en"}
    assert outcome.season_fallback is True
    assert outcome.requested_season == "halloween"
    assert outcome.season_id == "regular"
    assert outcome.bag_key == "bath|regular|"


def test_all_seasons_sound_does_not_trigger_fallback(catalog_payload: dict[str, object]) -> None:
    assert not select(
        parse_catalog(catalog_payload),
        category_id="lion",
        season_id="halloween",
        tags=[],
        bags={},
        rng=random.Random(1),
    ).season_fallback


def test_tags_are_not_relaxed(catalog_payload: dict[str, object]) -> None:
    with pytest.raises(NoEligibleSoundError, match=r"category=bath season=regular tags=\['fr'\]"):
        select(
            parse_catalog(catalog_payload),
            category_id="bath",
            season_id="regular",
            tags=["fr"],
            bags={},
            rng=random.Random(1),
        )


def test_select_does_not_mutate_bags(catalog_payload: dict[str, object]) -> None:
    bags = {"intro|regular|": BagState(["fox"], ["pirates"], "pirates")}
    before = bags["intro|regular|"].to_dict()
    select(
        parse_catalog(catalog_payload),
        category_id="intro",
        season_id="regular",
        tags=[],
        bags=bags,
        rng=random.Random(1),
    )
    assert bags["intro|regular|"].to_dict() == before


def test_bag_key_sorts_and_deduplicates_tags() -> None:
    assert bag_key("bath", "regular", ["es", "en", "es"]) == "bath|regular|en,es"


def test_bag_state_round_trip_and_validation() -> None:
    bag = BagState(["a"], ["b"], "b")
    assert BagState.from_dict(bag.to_dict()) == bag
    with pytest.raises(ValueError):
        BagState.from_dict({"remaining": [1]})
