"""User configuration, Supervisor discovery, and Sound Effects options."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.hassio import HassioServiceInfo

from .api import StudioAuthError, StudioClient, StudioConnectionError
from .const import (
    CONF_HOST,
    CONF_PORT,
    CONF_PUBLIC_BASE_URL,
    CONF_SCAN_INTERVAL,
    CONF_SEASON_ENTITY,
    CONF_TOKEN,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)


class SoundEffectsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure a single Studio instance."""

    VERSION = 1

    def __init__(self) -> None:
        self._pending: dict[str, Any] = {}
        self._addon_name = "Sound Effects Studio"

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> SoundEffectsOptionsFlow:
        return SoundEffectsOptionsFlow()

    async def _health(self, data: Mapping[str, Any]) -> dict[str, Any]:
        client = StudioClient(
            async_get_clientsession(self.hass),
            data[CONF_HOST],
            data[CONF_PORT],
            data[CONF_TOKEN],
        )
        return await client.health()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Validate the user-provided address and token."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                health = await self._health(user_input)
            except StudioAuthError:
                errors["base"] = "invalid_auth"
            except (StudioConnectionError, ValueError):
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(health["instance_id"])
                if self.source == config_entries.SOURCE_REAUTH:
                    self._abort_if_unique_id_mismatch()
                    return self.async_update_reload_and_abort(
                        self._get_reauth_entry(), data_updates=user_input
                    )
                self._abort_if_unique_id_configured(updates=user_input)
                return self.async_create_entry(title="Sound Effects Studio", data=user_input)
        defaults = user_input or self._pending
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
                    vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=65535)
                    ),
                    vol.Required(CONF_TOKEN): str,
                }
            ),
            errors=errors,
        )

    async def async_step_hassio(self, discovery_info: HassioServiceInfo) -> ConfigFlowResult:
        """Update an existing instance before showing discovery confirmation."""
        config = discovery_info.config
        await self.async_set_unique_id(config["instance_id"])
        data = {key: config[key] for key in (CONF_HOST, CONF_PORT, CONF_TOKEN)}
        self._abort_if_unique_id_configured(updates=data)
        self._pending = data
        self._addon_name = discovery_info.name
        return await self.async_step_hassio_confirm()

    async def async_step_hassio_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Validate Studio after the user confirms Supervisor discovery."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                health = await self._health(self._pending)
            except StudioAuthError:
                errors["base"] = "invalid_auth"
            except (StudioConnectionError, ValueError):
                errors["base"] = "cannot_connect"
            else:
                if health["instance_id"] != self.unique_id:
                    return self.async_abort(reason="cannot_connect")
                self._abort_if_unique_id_configured(updates=self._pending)
                return self.async_create_entry(title="Sound Effects Studio", data=self._pending)
        return self.async_show_form(
            step_id="hassio_confirm",
            data_schema=vol.Schema({}),
            errors=errors,
            description_placeholders={"addon": self._addon_name},
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Allow replacing a rejected token on the existing instance."""
        self._pending = dict(entry_data)
        return await self.async_step_user()


class SoundEffectsOptionsFlow(config_entries.OptionsFlow):
    """Configure public media URLs, an optional season entity, and polling."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        options = self.config_entry.options
        season_option = vol.Optional(CONF_SEASON_ENTITY)
        if options.get(CONF_SEASON_ENTITY):
            season_option = vol.Optional(CONF_SEASON_ENTITY, default=options[CONF_SEASON_ENTITY])
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_PUBLIC_BASE_URL, default=options.get(CONF_PUBLIC_BASE_URL, "")
                    ): str,
                    # HA's selector registry decorator erases the concrete class type.
                    season_option: selector.EntitySelector(  # pyright: ignore[reportUnknownMemberType]
                        selector.EntitySelectorConfig(
                            domain=["sensor", "input_select", "select", "input_text"]
                        )
                    ),
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    ): selector.NumberSelector(  # pyright: ignore[reportUnknownMemberType]
                        selector.NumberSelectorConfig(
                            min=10,
                            max=3600,
                            step=1,
                            mode=selector.NumberSelectorMode.BOX,
                            unit_of_measurement="s",
                        )
                    ),
                }
            ),
        )
