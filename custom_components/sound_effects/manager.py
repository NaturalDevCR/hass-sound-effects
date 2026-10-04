"""Select from the cached catalog without waiting for network or storage I/O."""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Callable
from copy import deepcopy
from typing import TYPE_CHECKING, Any, cast

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.network import NoURLAvailableError, get_url
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .api import StudioAuthError, StudioConnectionError
from .catalog import CategoryDef
from .const import (
    CONF_PUBLIC_BASE_URL,
    CONF_SEASON_ENTITY,
    DOMAIN,
    EVENT_SELECTED,
    PUBLISHED_PATH_PREFIX,
    REGULAR,
    STORAGE_VERSION,
)
from .coordinator import SoundEffectsCoordinator
from .seasons import UnknownSeasonError, resolve_effective_season
from .selection import BagState, NoEligibleSoundError, eligible_sounds, select

if TYPE_CHECKING:
    from . import SoundEffectsConfigEntry

_LOGGER = logging.getLogger(__name__)


class SoundEffectsManager:
    """Own in-memory shuffle bags, selection history, and the season override."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: SoundEffectsConfigEntry,
        coordinator: SoundEffectsCoordinator,
        rng: random.Random | None = None,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator
        self._rng = rng if rng is not None else random.Random()
        self._lock = asyncio.Lock()
        self._bags: dict[str, BagState] = {}
        self._last: dict[str, dict[str, Any]] = {}
        self._override: str | None = None
        self._listeners: list[Callable[[], None]] = []
        self._store = Store[dict[str, Any]](
            hass,
            STORAGE_VERSION,
            f"{DOMAIN}.{entry.entry_id}.history",
            serialize_in_event_loop=True,
        )

    async def async_load(self) -> None:
        """Restore history before the runtime is exposed to platforms/actions."""
        data = await self._store.async_load()
        if data is None:
            return
        raw_bags: Any = data.get("bags", {})
        if isinstance(raw_bags, dict):
            for key, value in cast(dict[str, Any], raw_bags).items():
                if not isinstance(value, dict):
                    continue
                try:
                    self._bags[key] = BagState.from_dict(cast(dict[str, Any], value))
                except ValueError:
                    _LOGGER.debug("Ignoring invalid selection bag %s", key)
        raw_last: Any = data.get("last", {})
        if isinstance(raw_last, dict):
            self._last = {
                key: deepcopy(cast(dict[str, Any], value))
                for key, value in cast(dict[str, Any], raw_last).items()
                if isinstance(value, dict)
            }
        override: Any = data.get("override")
        self._override = override if isinstance(override, str) else None

    @property
    def override_season(self) -> str | None:
        """Return the stored user override (None means automatic)."""
        return self._override

    async def async_set_override(self, season_id: str | None) -> None:
        """Validate and update the override, scheduling persistence."""
        async with self._lock:
            if season_id is not None:
                season = self.coordinator.data.catalog.find_season(season_id)
                if season is None:
                    raise ServiceValidationError(
                        translation_domain=DOMAIN, translation_key="unknown_season"
                    )
                season_id = season.id
            if self._override == season_id:
                return
            self._override = season_id
            self._schedule_save()
            self._notify_listeners()

    def _entity_state(self) -> str | None:
        entity_id = self.entry.options.get(CONF_SEASON_ENTITY)
        state = self.hass.states.get(entity_id) if entity_id else None
        if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return None
        return state.state

    def _resolve_season(self, action_season: str | None) -> tuple[str, str]:
        try:
            return resolve_effective_season(
                self.coordinator.data.catalog,
                dt_util.now().date(),
                action_season=action_season,
                override=self._override,
                entity_state=self._entity_state(),
            )
        except UnknownSeasonError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="unknown_season"
            ) from err

    def active_season(self) -> tuple[str, str]:
        """Return the effective season and its source without action overrides."""
        return self._resolve_season(None)

    def last_selection(self, category_id: str) -> dict[str, Any] | None:
        """Return a copy of the category's last response and UTC timestamp."""
        return deepcopy(self._last.get(category_id))

    def available_count(self, category_id: str) -> int:
        """Count eligible sounds, using regular when the active season is empty."""
        catalog = self.coordinator.data.catalog
        season_id, _ = self.active_season()
        sounds = eligible_sounds(catalog, category_id, season_id, ())
        if not sounds and season_id != REGULAR:
            sounds = eligible_sounds(catalog, category_id, REGULAR, ())
        return len(sounds)

    def _category(self, ref: str) -> CategoryDef:
        category = self.coordinator.data.catalog.find_category(ref)
        if category is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="unknown_category"
            )
        return category

    async def async_select(
        self,
        *,
        category: str,
        tags: list[str] | None = None,
        season: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Draw locally; only the in-memory lock is awaited on this call path."""
        async with self._lock:
            category_def = self._category(category)
            season_id, _ = self._resolve_season(season)
            rng = self._rng
            if dry_run:
                rng = random.Random()
                rng.setstate(self._rng.getstate())
            try:
                outcome = select(
                    self.coordinator.data.catalog,
                    category_id=category_def.id,
                    season_id=season_id,
                    tags=tags or [],
                    bags=self._bags,
                    rng=rng,
                )
            except NoEligibleSoundError as err:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="no_eligible_sound",
                    translation_placeholders={"category": category_def.name},
                ) from err
            sound = outcome.sound
            path = f"{PUBLISHED_PATH_PREFIX}{sound.published.filename}"
            response: dict[str, Any] = {
                "sound_id": sound.id,
                "key": sound.key,
                "title": sound.title,
                "category": sound.category_id,
                "tags": list(sound.tags),
                "season": outcome.season_id,
                "requested_season": outcome.requested_season,
                "season_fallback": outcome.season_fallback,
                "path": path,
                "url": f"{self.base_url().rstrip('/')}{path}",
                "duration": sound.published.duration,
                "revision": sound.published.revision,
                "mime_type": sound.published.mime_type,
            }
            if not dry_run:
                selected_at = dt_util.utcnow().isoformat().replace("+00:00", "Z")
                self._bags[outcome.bag_key] = outcome.bag
                self._last[category_def.id] = {**deepcopy(response), "selected_at": selected_at}
                self._schedule_save()
                self.hass.bus.async_fire(EVENT_SELECTED, deepcopy(response))
                self._notify_listeners()
                self.entry.async_create_background_task(
                    self.hass,
                    self._async_report_selection(
                        {
                            "sound_id": sound.id,
                            "category_id": sound.category_id,
                            "season_id": outcome.season_id,
                            "selected_at": selected_at,
                        }
                    ),
                    f"{DOMAIN} report selection",
                    eager_start=False,
                )
            return response

    async def _async_report_selection(self, event: dict[str, Any]) -> None:
        try:
            await self.entry.runtime_data.client.post_selections([event])
        except (StudioConnectionError, StudioAuthError):
            _LOGGER.debug("Unable to report selection to Studio", exc_info=True)

    async def async_reset_history(self, category: str | None = None) -> int:
        """Clear matching bags and last selections without changing the override."""
        async with self._lock:
            category_id = self._category(category).id if category is not None else None
            keys = [
                key
                for key in self._bags
                if category_id is None or key.split("|", 1)[0] == category_id
            ]
            had_last = bool(self._last) if category_id is None else category_id in self._last
            for key in keys:
                del self._bags[key]
            if category_id is None:
                self._last.clear()
            else:
                self._last.pop(category_id, None)
            if keys or had_last:
                self._schedule_save()
                self._notify_listeners()
            return len(keys)

    @callback
    def async_add_listener(self, update: Callable[[], None]) -> Callable[[], None]:
        """Register an in-memory update listener and return its remover."""
        self._listeners.append(update)

        @callback
        def remove() -> None:
            self._listeners.remove(update)

        return remove

    @callback
    def _notify_listeners(self) -> None:
        for update in tuple(self._listeners):
            update()

    @callback
    def _history_data(self) -> dict[str, Any]:
        return {
            "bags": {key: bag.to_dict() for key, bag in self._bags.items()},
            "last": deepcopy(self._last),
            "override": self._override,
        }

    @callback
    def _schedule_save(self) -> None:
        self._store.async_delay_save(self._history_data, 1.0)

    async def async_flush(self) -> None:
        """Flush current history on unload and cancel Store's pending timer."""
        await self._store.async_save(self._history_data())

    def base_url(self) -> str:
        """Use the configured public URL or HA's local URL, if available."""
        configured = self.entry.options.get(CONF_PUBLIC_BASE_URL)
        if configured:
            return str(configured)
        try:
            return get_url(self.hass, allow_external=False, prefer_external=False)
        except NoURLAvailableError:
            return ""
