"""Redacted configuration and compact cached runtime diagnostics."""

from typing import Any

# HA's Mapping overload is unparameterized.
from homeassistant.components.diagnostics import (
    async_redact_data,  # pyright: ignore[reportUnknownVariableType]
)
from homeassistant.core import HomeAssistant

from . import SoundEffectsConfigEntry
from .const import CONF_TOKEN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SoundEffectsConfigEntry
) -> dict[str, Any]:
    """Summarize runtime state without audio history or credentials."""
    state = entry.runtime_data.coordinator.data
    return {
        "entry_data": async_redact_data(dict(entry.data), {CONF_TOKEN}),
        "options": dict(entry.options),
        "catalog": {
            "revision": state.catalog.revision,
            "seasons": len(state.catalog.seasons),
            "categories": len(state.catalog.categories),
            "sounds": len(state.catalog.sounds),
        },
        "bags": entry.runtime_data.manager.bag_sizes(),
        "connected": state.connected,
    }
