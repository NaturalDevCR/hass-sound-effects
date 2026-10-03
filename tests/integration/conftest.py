"""Fixtures for the sound_effects integration tests."""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Make custom_components/ discoverable."""


@pytest.fixture
def catalog_payload() -> dict[str, Any]:
    def sound(
        sid: str,
        category: str,
        seasons: list[str],
        tags: list[str] | None = None,
        all_seasons: bool = False,
        enabled: bool = True,
    ) -> dict[str, Any]:
        return {
            "id": sid,
            "category_id": category,
            "title": sid.title(),
            "key": f"{sid}.mp3",
            "tags": tags or [],
            "seasons": seasons,
            "all_seasons": all_seasons,
            "enabled": enabled,
            "published": {
                "revision": 1,
                "filename": f"{sid}-r1.mp3",
                "duration": 2.5,
                "mime_type": "audio/mpeg",
            },
        }

    return {
        "revision": 7,
        "generated_at": "2026-10-03T12:00:00Z",
        "seasons": [
            {
                "id": "regular",
                "name": "Regular",
                "color": "#64748b",
                "icon": "mdi:calendar-blank",
                "start": None,
                "end": None,
                "priority": 0,
            },
            {
                "id": "halloween",
                "name": "Halloween",
                "color": "#f97316",
                "icon": "mdi:halloween",
                "start": "10-01",
                "end": "10-31",
                "priority": 10,
            },
        ],
        "categories": [
            {
                "id": "intro",
                "name": "Intro entrada",
                "icon": "mdi:door-open",
                "color": "#8b5cf6",
                "description": "",
                "sort_order": 0,
            },
            {
                "id": "lion",
                "name": "León",
                "icon": "mdi:paw",
                "color": "#eab308",
                "description": "",
                "sort_order": 1,
            },
            {
                "id": "bath",
                "name": "Baños",
                "icon": "mdi:bullhorn",
                "color": "#22c55e",
                "description": "",
                "sort_order": 2,
            },
        ],
        "sounds": [
            sound("fox", "intro", ["regular"]),
            sound("universal", "intro", ["regular"]),
            sound("pirates", "intro", ["regular"]),
            sound("boo", "intro", ["halloween"]),
            sound("roar", "lion", ["regular"], all_seasons=True),
            sound("bath_es", "bath", ["regular"], tags=["es"]),
            sound("bath_en", "bath", ["regular"], tags=["en"]),
            sound("off", "intro", ["regular"], enabled=False),
        ],
    }
