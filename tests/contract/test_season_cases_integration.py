from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from custom_components.sound_effects.seasons import resolve_calendar_season

CASES: list[dict[str, Any]] = json.loads(
    (Path(__file__).parents[2] / "contract/season_cases.json").read_text()
)


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_integration_calendar(case: dict[str, Any]) -> None:
    assert (
        resolve_calendar_season(case["seasons"], date.fromisoformat(case["date"]))
        == case["expected"]
    )
