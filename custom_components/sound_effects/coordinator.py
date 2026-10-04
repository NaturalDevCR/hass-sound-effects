"""Poll Studio and retain the last validated catalog for offline selection."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, cast

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import StudioAuthError, StudioClient, StudioConnectionError
from .catalog import Catalog, parse_catalog
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass
class StudioState:
    catalog: Catalog
    connected: bool
    last_sync: datetime | None
    app_version: str | None


class SoundEffectsCoordinator(DataUpdateCoordinator[StudioState]):
    """Own the catalog cache, ETag, connectivity, and refresh lifecycle."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: StudioClient,
        snapshot: Store[dict[str, Any]],
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        )
        self._client = client
        self._snapshot = snapshot
        self._etag: str | None = None

    async def async_load_snapshot(self) -> bool:
        """Load a validated raw catalog, without claiming a live connection."""
        stored = await self._snapshot.async_load()
        if stored is None:
            return False
        raw: Any = stored.get("catalog")
        etag: Any = stored.get("etag")
        if not isinstance(raw, dict) or (etag is not None and not isinstance(etag, str)):
            return False
        try:
            catalog = parse_catalog(cast(dict[str, Any], raw))
        except ValueError:
            _LOGGER.debug("Ignoring invalid catalog snapshot")
            return False
        self._etag = etag
        self.data = StudioState(catalog, connected=False, last_sync=None, app_version=None)
        return True

    async def _async_update_data(self) -> StudioState:
        # HA annotates data as StudioState even though it is None before the first update.
        previous = cast(StudioState | None, self.data)
        try:
            health = await self._client.health()
            response = await self._client.catalog(self._etag)
            if response.data is None:
                if previous is None:
                    raise StudioConnectionError("Studio returned 304 without a cached catalog")
                catalog = previous.catalog
            else:
                catalog = parse_catalog(response.data)
                await self._snapshot.async_save({"etag": response.etag, "catalog": response.data})
            self._etag = response.etag
            return StudioState(catalog, True, dt_util.utcnow(), health["version"])
        except StudioAuthError as err:
            raise ConfigEntryAuthFailed("Studio rejected the API token") from err
        except (StudioConnectionError, ValueError) as err:
            if previous is not None:
                return StudioState(
                    previous.catalog, False, previous.last_sync, previous.app_version
                )
            raise UpdateFailed("No catalog available from Studio") from err
