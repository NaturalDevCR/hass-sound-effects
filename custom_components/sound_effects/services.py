"""Home Assistant actions for cached selection, history reset, and catalog refresh."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN

if TYPE_CHECKING:
    from . import SoundEffectsConfigEntry


def _tags(value: object) -> list[str]:
    """Accept a list of strings or comma-separated tags."""
    if isinstance(value, str):
        return [tag.strip() for tag in value.split(",") if tag.strip()]
    return cast(list[str], vol.Schema([str])(value))


def _loaded_entry(hass: HomeAssistant) -> SoundEffectsConfigEntry:
    for entry in hass.config_entries.async_loaded_entries(DOMAIN):
        return cast("SoundEffectsConfigEntry", entry)
    raise ServiceValidationError(translation_domain=DOMAIN, translation_key="not_loaded")


async def async_register_services(hass: HomeAssistant) -> None:
    """Register each action once; resolve the current runtime on every call."""

    async def async_select(call: ServiceCall) -> ServiceResponse:
        manager = _loaded_entry(hass).runtime_data.manager
        result = await manager.async_select(
            category=call.data["category"],
            tags=call.data.get("tags"),
            season=call.data.get("season"),
            dry_run=call.data["dry_run"],
        )
        return result if call.return_response else None

    async def async_reset_history(call: ServiceCall) -> ServiceResponse:
        manager = _loaded_entry(hass).runtime_data.manager
        cleared = await manager.async_reset_history(call.data.get("category"))
        return {"cleared": cleared} if call.return_response else None

    async def async_refresh(call: ServiceCall) -> None:
        await _loaded_entry(hass).runtime_data.coordinator.async_refresh()

    if not hass.services.has_service(DOMAIN, "select"):
        hass.services.async_register(
            DOMAIN,
            "select",
            async_select,
            schema=vol.Schema(
                {
                    vol.Required("category"): str,
                    vol.Optional("tags"): _tags,
                    vol.Optional("season"): str,
                    vol.Optional("dry_run", default=False): cv.boolean,
                }
            ),
            supports_response=SupportsResponse.OPTIONAL,
        )
    if not hass.services.has_service(DOMAIN, "reset_history"):
        hass.services.async_register(
            DOMAIN,
            "reset_history",
            async_reset_history,
            schema=vol.Schema({vol.Optional("category"): str}),
            supports_response=SupportsResponse.OPTIONAL,
        )
    if not hass.services.has_service(DOMAIN, "refresh"):
        hass.services.async_register(DOMAIN, "refresh", async_refresh, schema=vol.Schema({}))
