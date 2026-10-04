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


@pytest.fixture
async def loaded_entry(hass, aioclient_mock, catalog_payload):
    """Load a real runtime and always flush history/cancel its background work."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.sound_effects.const import DOMAIN

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"host": "studio", "port": 8099, "token": "secret"},
        unique_id="studio-id",
        options={"public_base_url": "https://ha.example/", "scan_interval": 3600},
    )
    entry.add_to_hass(hass)
    base = "http://studio:8099/api/v1"
    aioclient_mock.get(
        f"{base}/health",
        json={"status": "ok", "version": "1.0", "api_version": 1, "instance_id": "studio-id"},
    )
    aioclient_mock.get(f"{base}/catalog", json=catalog_payload)
    aioclient_mock.post(f"{base}/selections", status=204)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    yield entry
    if hass.config_entries.async_get_entry(entry.entry_id) is not None:
        assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
