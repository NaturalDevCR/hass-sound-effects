"""Pure data model and parser for the remote catalog."""

from __future__ import annotations

import math
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol, cast

from .const import REGULAR


@dataclass(frozen=True)
class SeasonDef:
    id: str
    name: str
    color: str
    icon: str
    start: str | None
    end: str | None
    priority: int


@dataclass(frozen=True)
class CategoryDef:
    id: str
    name: str
    icon: str
    color: str
    description: str
    sort_order: int


@dataclass(frozen=True)
class PublishedDef:
    revision: int
    filename: str
    duration: float
    mime_type: str


@dataclass(frozen=True)
class SoundDef:
    id: str
    category_id: str
    title: str
    key: str
    tags: tuple[str, ...]
    seasons: tuple[str, ...]
    all_seasons: bool
    enabled: bool
    published: PublishedDef


@dataclass(frozen=True)
class Catalog:
    revision: int
    seasons: tuple[SeasonDef, ...]
    categories: tuple[CategoryDef, ...]
    sounds: tuple[SoundDef, ...]

    def find_category(self, ref: str) -> CategoryDef | None:
        return _find(self.categories, ref)

    def find_season(self, ref: str) -> SeasonDef | None:
        return _find(self.seasons, ref)


class _Named(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def name(self) -> str: ...


def _find[T: _Named](items: tuple[T, ...], ref: str) -> T | None:
    for item in items:
        if item.id == ref:
            return item
    folded = ref.casefold()
    return next(
        (item for item in items if item.id.casefold() == folded or item.name.casefold() == folded),
        None,
    )


def _mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{context} must be an object")
    return cast(Mapping[str, Any], value)


def _field(
    data: Mapping[str, Any], name: str, expected: type | tuple[type, ...], context: str
) -> Any:
    value = data.get(name)
    if not isinstance(value, expected) or (expected is int and isinstance(value, bool)):
        raise ValueError(f"{context}.{name} is missing or invalid")
    return value


def parse_catalog(data: Mapping[str, Any]) -> Catalog:
    """Parse a catalog payload, rejecting missing or incorrectly typed fields."""
    root = _mapping(data, "catalog")
    revision = _field(root, "revision", int, "catalog")
    raw_seasons = _field(root, "seasons", list, "catalog")
    raw_categories = _field(root, "categories", list, "catalog")
    raw_sounds = _field(root, "sounds", list, "catalog")
    seasons = tuple(_parse_season(_mapping(item, "season")) for item in raw_seasons)
    categories = tuple(_parse_category(_mapping(item, "category")) for item in raw_categories)
    sounds = tuple(_parse_sound(_mapping(item, "sound")) for item in raw_sounds)
    return Catalog(revision, seasons, categories, sounds)


def _parse_season(data: Mapping[str, Any]) -> SeasonDef:
    season_id = _field(data, "id", str, "season")
    start = data.get("start")
    end = data.get("end")
    if season_id != REGULAR and (start is None or end is None):
        raise ValueError("non-regular season requires start and end")
    if (start is not None and not isinstance(start, str)) or (
        end is not None and not isinstance(end, str)
    ):
        raise ValueError("invalid season date")
    if (start is not None and re.fullmatch(r"[0-9]{2}-[0-9]{2}", start) is None) or (
        end is not None and re.fullmatch(r"[0-9]{2}-[0-9]{2}", end) is None
    ):
        raise ValueError("invalid season date")
    for value in (start, end):
        if value is not None:
            try:
                date(2000, int(value[:2]), int(value[3:]))
            except ValueError as err:
                raise ValueError("invalid season date") from err
    return SeasonDef(
        season_id,
        _field(data, "name", str, "season"),
        _field(data, "color", str, "season"),
        _field(data, "icon", str, "season"),
        start,
        end,
        _field(data, "priority", int, "season"),
    )


def _parse_category(data: Mapping[str, Any]) -> CategoryDef:
    return CategoryDef(
        _field(data, "id", str, "category"),
        _field(data, "name", str, "category"),
        _field(data, "icon", str, "category"),
        _field(data, "color", str, "category"),
        _field(data, "description", str, "category"),
        _field(data, "sort_order", int, "category"),
    )


def _parse_sound(data: Mapping[str, Any]) -> SoundDef:
    tags = _field(data, "tags", list, "sound")
    seasons = _field(data, "seasons", list, "sound")
    if not all(isinstance(tag, str) for tag in tags) or not all(
        isinstance(season, str) for season in seasons
    ):
        raise ValueError("invalid sound tags or seasons")
    published = _mapping(data.get("published"), "published")
    duration = _field(published, "duration", (int, float), "published")
    if isinstance(duration, bool) or duration < 0:
        raise ValueError("invalid published duration")
    if isinstance(duration, int):
        if duration > sys.float_info.max:
            raise ValueError("invalid published duration")
    elif not math.isfinite(duration):
        raise ValueError("invalid published duration")
    published_def = PublishedDef(
        _field(published, "revision", int, "published"),
        _field(published, "filename", str, "published"),
        float(duration),
        _field(published, "mime_type", str, "published"),
    )
    return SoundDef(
        _field(data, "id", str, "sound"),
        _field(data, "category_id", str, "sound"),
        _field(data, "title", str, "sound"),
        _field(data, "key", str, "sound"),
        tuple(tags),
        tuple(seasons),
        _field(data, "all_seasons", bool, "sound"),
        _field(data, "enabled", bool, "sound"),
        published_def,
    )


EMPTY_CATALOG = Catalog(0, (SeasonDef(REGULAR, "Regular", "", "", None, None, 0),), (), ())
