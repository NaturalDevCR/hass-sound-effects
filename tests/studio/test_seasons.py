from dataclasses import dataclass
from datetime import date

import pytest

from sound_effects_studio.seasons import REGULAR, resolve_calendar_season, season_matches

pytestmark = pytest.mark.studio


@dataclass
class _Season:
    id: str
    start: str | None
    end: str | None
    priority: int = 0


@pytest.mark.parametrize(
    ("start", "end", "mmdd", "expected"),
    [
        ("10-01", "10-31", "10-01", True),
        ("10-01", "10-31", "10-31", True),
        ("10-01", "10-31", "11-01", False),
        ("10-01", "10-31", "09-30", False),
        ("12-01", "01-06", "12-01", True),
        ("12-01", "01-06", "12-31", True),
        ("12-01", "01-06", "01-01", True),
        ("12-01", "01-06", "01-06", True),
        ("12-01", "01-06", "01-07", False),
        ("12-01", "01-06", "11-30", False),
        ("02-29", "02-29", "02-29", True),
        (None, None, "06-01", False),
        ("10-01", None, "10-05", False),
        (None, "10-31", "10-05", False),
    ],
)
def test_season_matches(start: str | None, end: str | None, mmdd: str, expected: bool) -> None:
    assert season_matches(start, end, mmdd) is expected


def test_resolve_prefers_priority_then_id() -> None:
    seasons = [
        _Season("b", "05-01", "05-31", 5),
        _Season("a", "05-10", "05-20", 5),
        _Season("top", "05-12", "05-14", 9),
    ]
    assert resolve_calendar_season(seasons, date(2026, 5, 13)) == "top"
    assert resolve_calendar_season(seasons, date(2026, 5, 15)) == "a"
    assert resolve_calendar_season(seasons, date(2026, 5, 25)) == "b"


def test_resolve_falls_back_to_regular() -> None:
    assert resolve_calendar_season([], date(2026, 1, 1)) == REGULAR
    assert resolve_calendar_season([_Season("regular", None, None)], date(2026, 1, 1)) == "regular"
