"""Season matching and effective season resolution."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Protocol

from .catalog import Catalog
from .const import REGULAR


class SeasonLike(Protocol):
    """The calendar fields needed to resolve a season."""

    @property
    def id(self) -> str: ...

    @property
    def start(self) -> str | None: ...

    @property
    def end(self) -> str | None: ...

    @property
    def priority(self) -> int: ...


class UnknownSeasonError(ValueError):
    """Raised when an action explicitly requests an unknown season."""


def _value(season: SeasonLike | Mapping[str, object], field: str) -> object:
    return season[field] if isinstance(season, Mapping) else getattr(season, field)


def season_matches(season: SeasonLike | Mapping[str, object], day: date) -> bool:
    """Return whether day is in the inclusive MM-DD range, including year wrapping."""
    season_id = _value(season, "id")
    start = _value(season, "start")
    end = _value(season, "end")
    if season_id == REGULAR or start is None or end is None:
        return False
    if not isinstance(start, str) or not isinstance(end, str):
        return False
    current = day.strftime("%m-%d")
    if start <= end:
        return start <= current <= end
    return current >= start or current <= end


def resolve_calendar_season(
    seasons: list[SeasonLike | Mapping[str, object]]
    | tuple[SeasonLike | Mapping[str, object], ...],
    day: date,
) -> str:
    """Resolve matching special seasons by priority, then lexicographic id."""
    matches = [season for season in seasons if season_matches(season, day)]
    if not matches:
        return REGULAR

    def sort_key(season: SeasonLike | Mapping[str, object]) -> tuple[int, str]:
        priority = _value(season, "priority")
        return (-priority if isinstance(priority, int) else 0, str(_value(season, "id")))

    winner = min(matches, key=sort_key)
    return str(_value(winner, "id"))


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
