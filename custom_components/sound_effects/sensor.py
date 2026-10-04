"""Active season and the last selected sound in each catalog category."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_change

from . import SoundEffectsConfigEntry
from .catalog import CategoryDef
from .const import CONF_SEASON_ENTITY, DOMAIN
from .entity import SoundEffectsEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: SoundEffectsConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Keep category entities aligned with the catalog and local season inputs."""
    coordinator = entry.runtime_data.coordinator
    active = SoundEffectsActiveSeasonSensor(entry)
    categories: dict[str, SoundEffectsCategorySensor] = {}
    registry = er.async_get(hass)
    prefix = f"{entry.entry_id}_category_"

    @callback
    def sync_categories() -> None:
        current = {category.id: category for category in coordinator.data.catalog.categories}
        for registered in er.async_entries_for_config_entry(registry, entry.entry_id):
            if (
                registered.domain == "sensor"
                and registered.platform == DOMAIN
                and registered.unique_id.startswith(prefix)
                and registered.unique_id[len(prefix) :] not in current
            ):
                registry.async_remove(registered.entity_id)
        for category_id in categories.keys() - current.keys():
            del categories[category_id]
        added: list[SoundEffectsCategorySensor] = []
        for category_id, category in current.items():
            if category_id not in categories:
                sensor = SoundEffectsCategorySensor(entry, category)
                categories[category_id] = sensor
                added.append(sensor)
        if added:
            async_add_entities(added)

    @callback
    def update_season_inputs(
        event: datetime | Event[EventStateChangedData],
    ) -> None:
        for sensor in (active, *categories.values()):
            # Disabled registry entities are not attached to HA.
            if sensor.hass:
                sensor.async_refresh_state()

    async_add_entities([active])
    sync_categories()
    entry.async_on_unload(coordinator.async_add_listener(sync_categories))
    entry.async_on_unload(
        async_track_time_change(hass, update_season_inputs, hour=0, minute=0, second=5)
    )
    if season_entity := entry.options.get(CONF_SEASON_ENTITY):
        entry.async_on_unload(
            async_track_state_change_event(hass, season_entity, update_season_inputs)
        )


class SoundEffectsActiveSeasonSensor(SoundEffectsEntity, SensorEntity):
    """The active season and how it was chosen."""

    _attr_translation_key = "active_season"

    def __init__(self, entry: SoundEffectsConfigEntry) -> None:
        super().__init__(entry, "active_season")
        self._update_state()

    @callback
    def _update_state(self) -> None:
        season_id, source = self.manager.active_season()
        self._attr_native_value = season_id
        season = self.coordinator.data.catalog.find_season(season_id)
        self._attr_extra_state_attributes = {
            "name": season.name if season else season_id,
            "source": source,
            "color": season.color if season else None,
        }


class SoundEffectsCategorySensor(SoundEffectsEntity, SensorEntity):
    """The category's last sound, with its current eligible sound count."""

    def __init__(self, entry: SoundEffectsConfigEntry, category: CategoryDef) -> None:
        super().__init__(entry, f"category_{category.id}")
        self.category = category
        self._attr_name = category.name
        self._attr_icon = category.icon
        self._update_state()

    @callback
    def _update_state(self) -> None:
        category = self.coordinator.data.catalog.find_category(self.category.id)
        if category is not None:
            self.category = category
            self._attr_name = category.name
            self._attr_icon = category.icon
        last = self.manager.last_selection(self.category.id) or {}
        self._attr_native_value = str(last["title"]) if last else None
        self._attr_extra_state_attributes = {
            "category_id": self.category.id,
            **{
                key: last.get(key)
                for key in ("sound_id", "key", "url", "duration", "season", "selected_at")
            },
            "available": self.manager.available_count(self.category.id),
        }
