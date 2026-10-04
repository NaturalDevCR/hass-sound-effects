"""The Sound Effects integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import Event, HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from .api import StudioClient
from .const import CONF_HOST, CONF_PORT, CONF_TOKEN, DOMAIN, EVENT_CATALOG_CHANGED, STORAGE_VERSION
from .coordinator import SoundEffectsCoordinator
from .manager import SoundEffectsManager
from .services import async_register_services

PLATFORMS: list[Platform] = []
# HA's schema factory leaves its dictionary parameters untyped.
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]


@dataclass
class SoundEffectsRuntime:
    client: StudioClient
    coordinator: SoundEffectsCoordinator
    manager: SoundEffectsManager


type SoundEffectsConfigEntry = ConfigEntry[SoundEffectsRuntime]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the integration's services once."""
    await async_register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: SoundEffectsConfigEntry) -> bool:
    """Connect to Studio, falling back to a persisted catalog when offline."""
    client = StudioClient(
        async_get_clientsession(hass),
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.data[CONF_TOKEN],
    )
    snapshot = Store[dict[str, Any]](hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}.catalog")
    coordinator = SoundEffectsCoordinator(hass, entry, client, snapshot)
    had_snapshot = await coordinator.async_load_snapshot()
    await coordinator.async_refresh()
    if isinstance(coordinator.last_exception, ConfigEntryAuthFailed):
        raise coordinator.last_exception
    if not coordinator.last_update_success and not had_snapshot:
        raise ConfigEntryNotReady("Studio is offline and no catalog snapshot is available")
    manager = SoundEffectsManager(hass, entry, coordinator)
    await manager.async_load()
    entry.runtime_data = SoundEffectsRuntime(client, coordinator, manager)
    entry.async_on_unload(coordinator.async_add_listener(lambda: None))
    setup_options = entry.options

    async def async_catalog_changed(event: Event) -> None:
        await coordinator.async_request_refresh()

    entry.async_on_unload(hass.bus.async_listen(EVENT_CATALOG_CHANGED, async_catalog_changed))

    async def async_options_updated(hass: HomeAssistant, entry: SoundEffectsConfigEntry) -> None:
        """Rebuild the runtime only when options change."""
        if entry.options != setup_options:
            await hass.config_entries.async_reload(entry.entry_id)

    entry.async_on_unload(entry.add_update_listener(async_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SoundEffectsConfigEntry) -> bool:
    """Unload platforms; Home Assistant then runs the registered cleanup hooks."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.manager.async_flush()
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: SoundEffectsConfigEntry) -> None:
    """Delete the persisted catalog and history when the Studio entry is removed."""
    await Store[dict[str, Any]](
        hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}.catalog"
    ).async_remove()
    await Store[dict[str, Any]](
        hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}.history"
    ).async_remove()
