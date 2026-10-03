"""Pure sound eligibility and shuffle-bag selection."""

from __future__ import annotations

import random
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from .catalog import Catalog, SoundDef
from .const import REGULAR


@dataclass
class BagState:
    remaining: list[str]
    played: list[str]
    last: str | None

    def to_dict(self) -> dict[str, Any]:
        return {"remaining": self.remaining.copy(), "played": self.played.copy(), "last": self.last}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> BagState:
        raw_remaining: Any = data.get("remaining", [])
        raw_played: Any = data.get("played", [])
        last = data.get("last")
        if not isinstance(raw_remaining, list):
            raise ValueError("invalid remaining bag ids")
        remaining_values = cast(list[object], raw_remaining)
        if not all(isinstance(item, str) for item in remaining_values):
            raise ValueError("invalid remaining bag ids")
        if not isinstance(raw_played, list):
            raise ValueError("invalid played bag ids")
        played_values = cast(list[object], raw_played)
        if not all(isinstance(item, str) for item in played_values):
            raise ValueError("invalid played bag ids")
        if last is not None and not isinstance(last, str):
            raise ValueError("invalid last bag id")
        remaining = cast(list[str], raw_remaining)
        played = cast(list[str], raw_played)
        return cls(remaining.copy(), played.copy(), last)


class NoEligibleSoundError(Exception):
    """Raised when no sound meets the category, season, and tag constraints."""


@dataclass(frozen=True)
class SelectionOutcome:
    sound: SoundDef
    season_id: str
    requested_season: str
    season_fallback: bool
    bag_key: str
    bag: BagState


def bag_key(category_id: str, season_id: str, tags: Iterable[str]) -> str:
    return f"{category_id}|{season_id}|{','.join(sorted(set(tags)))}"


def eligible_sounds(
    catalog: Catalog, category_id: str, season_id: str, tags: Iterable[str]
) -> list[SoundDef]:
    required = set(tags)
    return [
        sound
        for sound in catalog.sounds
        if sound.enabled
        and sound.category_id == category_id
        and required.issubset(sound.tags)
        and (sound.all_seasons or season_id in sound.seasons)
    ]


def draw(bag: BagState, eligible_ids: Sequence[str], rng: random.Random) -> tuple[str, BagState]:
    eligible = list(dict.fromkeys(eligible_ids))
    if not eligible:
        raise NoEligibleSoundError("no eligible sound")
    members = set(eligible)
    remaining = [sid for sid in bag.remaining if sid in members]
    played = [sid for sid in bag.played if sid in members]
    for sid in eligible:
        if sid not in remaining and sid not in played:
            remaining.append(sid)
    if not remaining:
        remaining = [sid for sid in eligible if sid != bag.last] or eligible[:]
        played = []
    pick = rng.choice(remaining)
    remaining = [sid for sid in remaining if sid != pick]
    return pick, BagState(remaining=remaining, played=[*played, pick], last=pick)


def select(
    catalog: Catalog,
    *,
    category_id: str,
    season_id: str,
    tags: Iterable[str],
    bags: Mapping[str, BagState],
    rng: random.Random,
) -> SelectionOutcome:
    """Select an eligible sound without changing the caller's bag mapping."""
    normalized_tags = tuple(tags)
    chosen_season = season_id
    candidates = eligible_sounds(catalog, category_id, chosen_season, normalized_tags)
    fallback = False
    if not candidates and season_id != REGULAR:
        chosen_season = REGULAR
        candidates = eligible_sounds(catalog, category_id, chosen_season, normalized_tags)
        fallback = bool(candidates)
    if not candidates:
        raise NoEligibleSoundError("no eligible sound")
    key = bag_key(category_id, chosen_season, normalized_tags)
    bag = bags.get(key, BagState([], [], None))
    sound_id, next_bag = draw(bag, [sound.id for sound in candidates], rng)
    sound = next(sound for sound in candidates if sound.id == sound_id)
    return SelectionOutcome(sound, chosen_season, season_id, fallback, key, next_bag)
