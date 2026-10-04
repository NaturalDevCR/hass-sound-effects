"""Persistent season override selector."""

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SoundEffectsConfigEntry
from .entity import SoundEffectsEntity

AUTO = "Auto"


async def async_setup_entry(
    hass: HomeAssistant, entry: SoundEffectsConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([SoundEffectsSeasonOverrideSelect(entry)])


class SoundEffectsSeasonOverrideSelect(SoundEffectsEntity, SelectEntity):
    """Choose automatic resolution or a named catalog season."""

    _attr_translation_key = "season_override"

    def __init__(self, entry: SoundEffectsConfigEntry) -> None:
        super().__init__(entry, "season_override")
        self._update_state()

    @callback
    def _update_state(self) -> None:
        self._attr_options = [
            AUTO,
            *(season.name for season in self.coordinator.data.catalog.seasons),
        ]
        override = self.manager.override_season
        season = self.coordinator.data.catalog.find_season(override) if override else None
        self._attr_current_option = season.name if season is not None else AUTO

    async def async_select_option(self, option: str) -> None:
        # The manager validates names and persists the corresponding season id.
        await self.manager.async_set_override(None if option == AUTO else option)
