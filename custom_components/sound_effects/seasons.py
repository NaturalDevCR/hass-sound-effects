"""Yearly season calendar shared (by copy) with the sound_effects integration."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Protocol

from .catalog import Catalog

REGULAR = "regular"


class SeasonLike(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def start(self) -> str | None: ...

    @property
    def end(self) -> str | None: ...

    @property
    def priority(self) -> int: ...


def season_matches(start: str | None, end: str | None, mmdd: str) -> bool:
    """Return True when MM-DD falls inside an inclusive, possibly year-wrapping range."""
    if not start or not end:
        return False
    if start <= end:
        return start <= mmdd <= end
    return mmdd >= start or mmdd <= end


def resolve_calendar_season(seasons: Iterable[SeasonLike], day: date) -> str:
    """Pick the highest-priority season whose range contains the day, else regular."""
    mmdd = day.strftime("%m-%d")
    matches = [
        season
        for season in seasons
        if season.id != REGULAR and season_matches(season.start, season.end, mmdd)
    ]
    if not matches:
        return REGULAR
    matches.sort(key=lambda season: (-season.priority, season.id))
    return matches[0].id


class UnknownSeasonError(ValueError):
    """Raised when an action explicitly requests an unknown season."""


def resolve_effective_season(
    catalog: Catalog,
    day: date,
    *,
    action_season: str | None,
    override: str | None,
    entity_state: str | None,
) -> tuple[str, str]:
    """Resolve action, user override, entity, then calendar season."""
    if action_season is not None:
        season = catalog.find_season(action_season)
        if season is None:
            raise UnknownSeasonError(action_season)
        return season.id, "action"
    if override is not None:
        season = catalog.find_season(override)
        if season is not None:
            return season.id, "override"
    if entity_state is not None and entity_state.casefold() not in {"", "unknown", "unavailable"}:
        season = catalog.find_season(entity_state)
        if season is not None:
            return season.id, "entity"
    season_id = resolve_calendar_season(catalog.seasons, day)
    if season_id == REGULAR:
        return season_id, "default"
    return season_id, "calendar"
