"""Redacted diagnostics and the integration's distributable brand artwork."""

import importlib
import struct
from pathlib import Path

import pytest
from homeassistant.components.diagnostics import REDACTED

pytestmark = pytest.mark.integration


async def test_diagnostics_redacts_token_and_summarizes_runtime(hass, loaded_entry):
    diagnostics = importlib.import_module("custom_components.sound_effects.diagnostics")
    manager = loaded_entry.runtime_data.manager
    await manager.async_select(category="intro", season="regular")
    await hass.async_block_till_done(wait_background_tasks=True)
    before = manager._history_data()
    result = await diagnostics.async_get_config_entry_diagnostics(hass, loaded_entry)
    assert result["entry_data"] == {"host": "studio", "port": 8099, "token": REDACTED}
    assert result["options"] == dict(loaded_entry.options)
    assert result["catalog"] == {"revision": 7, "seasons": 2, "categories": 3, "sounds": 8}
    assert result["bags"] == {"intro|regular|": 2}
    assert result["connected"] is True
    assert "secret" not in repr(result)
    assert loaded_entry.data["token"] == "secret"
    assert manager._history_data() == before


async def test_diagnostics_offline(hass, loaded_entry):
    diagnostics = importlib.import_module("custom_components.sound_effects.diagnostics")
    loaded_entry.runtime_data.coordinator.data.connected = False
    result = await diagnostics.async_get_config_entry_diagnostics(hass, loaded_entry)
    assert result["connected"] is False
    assert result["bags"] == {}


def test_brand_png_dimensions_and_svg():
    brand = Path("custom_components/sound_effects/brand")
    raw = (brand / "icon.png").read_bytes()
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    assert raw[12:16] == b"IHDR"
    assert struct.unpack(">II", raw[16:24]) == (256, 256)
    svg = (brand / "icon.svg").read_text()
    assert 'viewBox="0 0 256 256"' in svg
    assert "#8b5cf6" in svg
