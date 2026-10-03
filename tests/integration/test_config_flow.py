"""User, Supervisor discovery, and options flows."""

from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import AbortFlow, FlowResultType
from homeassistant.helpers.service_info.hassio import HassioServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sound_effects.config_flow import SoundEffectsConfigFlow
from custom_components.sound_effects.const import DOMAIN

pytestmark = pytest.mark.integration
DATA = {"host": "studio", "port": 8099, "token": "secret"}
HEALTH = {"status": "ok", "version": "1.0.0", "api_version": 1, "instance_id": "studio-id"}
URL = "http://studio:8099/api/v1/health"


@pytest.fixture(autouse=True)
def mock_entry_setup():
    with patch("custom_components.sound_effects.async_setup_entry", return_value=True):
        yield


async def test_user_success(hass, aioclient_mock):
    aioclient_mock.get(URL, json=HEALTH)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], DATA)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Sound Effects Studio"
    assert result["data"] == DATA
    assert result["result"].unique_id == "studio-id"
    await hass.async_block_till_done()


@pytest.mark.parametrize("status, error", [(503, "cannot_connect"), (401, "invalid_auth")])
async def test_user_errors(hass, aioclient_mock, status, error):
    aioclient_mock.get(URL, status=status)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}, data=DATA
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}


def discovery(token="secret"):
    return HassioServiceInfo(
        config={**DATA, "token": token, "instance_id": "studio-id"},
        name="Sound Effects Studio",
        slug="sound_effects_studio",
        uuid="1234",
    )


async def test_hassio_success(hass, aioclient_mock):
    aioclient_mock.get(URL, json=HEALTH)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_HASSIO}, data=discovery()
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "hassio_confirm"
    assert result["description_placeholders"] == {"addon": "Sound Effects Studio"}
    assert aioclient_mock.call_count == 0
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == DATA
    assert result["result"].unique_id == "studio-id"
    await hass.async_block_till_done()


async def test_hassio_rediscovery(hass, aioclient_mock):
    entry = MockConfigEntry(domain=DOMAIN, data=DATA, unique_id="studio-id")
    entry.add_to_hass(hass)
    # HA 2026.2 rejects rediscovery before invoking this handler for single-entry
    # integrations. Exercise the required handler behavior directly, without
    # changing the manifest or patching HA's single-entry guard.
    flow = SoundEffectsConfigFlow()
    flow.hass = hass
    flow.handler = DOMAIN
    flow.context = {"source": config_entries.SOURCE_HASSIO}
    with pytest.raises(AbortFlow) as abort:
        await flow.async_step_hassio(discovery("rotated"))
    assert abort.value.reason == "already_configured"
    assert entry.data == {**DATA, "token": "rotated"}
    assert aioclient_mock.call_count == 0


async def test_hassio_rediscovery_blocked_by_ha_single_entry_guard(hass, aioclient_mock):
    """Document the platform limitation without hiding it behind a mock."""
    entry = MockConfigEntry(domain=DOMAIN, data=DATA, unique_id="studio-id")
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_HASSIO}, data=discovery("rotated")
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"
    assert entry.data == DATA
    assert aioclient_mock.call_count == 0


@pytest.mark.parametrize("status, error", [(503, "cannot_connect"), (403, "invalid_auth")])
async def test_hassio_errors(hass, aioclient_mock, status, error):
    aioclient_mock.get(URL, status=status)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_HASSIO}, data=discovery()
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["step_id"] == "hassio_confirm"
    assert result["errors"] == {"base": error}


async def test_hassio_identity_mismatch(hass, aioclient_mock):
    aioclient_mock.get(URL, json={**HEALTH, "instance_id": "another-studio"})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_HASSIO}, data=discovery()
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def test_single_instance(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=DATA, unique_id="studio-id")
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_options(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=DATA, unique_id="studio-id")
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    options = {
        "public_base_url": "https://ha.example",
        "season_entity": "input_select.season",
        "scan_interval": 60,
    }
    result = await hass.config_entries.options.async_configure(result["flow_id"], options)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == options


@pytest.mark.parametrize(
    "instance_id, reason",
    [
        ("studio-id", "reauth_successful"),
        ("another-studio", "unique_id_mismatch"),
    ],
)
async def test_reauth(hass, aioclient_mock, instance_id, reason):
    entry = MockConfigEntry(domain=DOMAIN, data=DATA, unique_id="studio-id")
    entry.add_to_hass(hass)
    aioclient_mock.get(URL, json={**HEALTH, "instance_id": instance_id})
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=DATA,
    )
    assert result["step_id"] == "user"
    with patch.object(hass.config_entries, "async_reload", return_value=True) as reload:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**DATA, "token": "rotated"}
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == reason
    assert entry.data["token"] == ("rotated" if instance_id == "studio-id" else "secret")
    assert reload.await_count == (1 if instance_id == "studio-id" else 0)


async def test_options_defaults_and_optional_season(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=DATA)
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["data_schema"]({}) == {"public_base_url": "", "scan_interval": 30}
    result = await hass.config_entries.options.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {"public_base_url": "", "scan_interval": 30}


async def test_options_current_values(hass):
    options = {
        "public_base_url": "https://ha.example",
        "season_entity": "sensor.season",
        "scan_interval": 90,
    }
    entry = MockConfigEntry(domain=DOMAIN, data=DATA, options=options)
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["data_schema"]({}) == options
