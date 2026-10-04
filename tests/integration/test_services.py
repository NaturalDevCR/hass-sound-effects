"""Public selection/reset/refresh actions and offline cached operation."""

from unittest.mock import patch

import pytest
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sound_effects.const import DOMAIN, STORAGE_VERSION
from custom_components.sound_effects.services import async_register_services

pytestmark = pytest.mark.integration


async def call(hass, action="select", data=None, response=True):
    return await hass.services.async_call(
        DOMAIN, action, data or {}, blocking=True, return_response=response
    )


async def test_shuffle_across_service_calls(hass, loaded_entry):
    results = [
        await call(hass, data={"category": "Intro entrada", "season": "regular"}) for _ in range(3)
    ]
    assert {result["sound_id"] for result in results} == {"fox", "universal", "pirates"}
    assert set(results[0]) == {
        "sound_id",
        "key",
        "title",
        "category",
        "tags",
        "season",
        "requested_season",
        "season_fallback",
        "url",
        "path",
        "duration",
        "revision",
        "mime_type",
    }
    assert results[0]["url"].startswith("https://ha.example/local/sound-effects/")


@pytest.mark.parametrize("tags", [["es"], " es, es "])
async def test_tags_and_fallback(hass, loaded_entry, tags):
    result = await call(hass, data={"category": "bath", "tags": tags, "season": "Halloween"})
    assert result["sound_id"] == "bath_es"
    assert result["requested_season"] == "halloween"
    assert result["season"] == "regular"
    assert result["season_fallback"]


async def test_override_and_named_season(hass, loaded_entry):
    await loaded_entry.runtime_data.manager.async_set_override("halloween")
    assert (await call(hass, data={"category": "intro"}))["sound_id"] == "boo"
    assert (await call(hass, data={"category": "intro", "season": "Halloween"}))[
        "sound_id"
    ] == "boo"


@pytest.mark.parametrize(
    "data, key",
    [
        ({"category": "missing"}, "unknown_category"),
        ({"category": "intro", "season": "missing"}, "unknown_season"),
        ({"category": "intro", "tags": ["missing"]}, "no_eligible_sound"),
    ],
)
async def test_validation_errors(hass, loaded_entry, data, key):
    with pytest.raises(ServiceValidationError) as err:
        await call(hass, data=data)
    assert err.value.translation_domain == DOMAIN
    assert err.value.translation_key == key
    if key == "no_eligible_sound":
        assert err.value.translation_placeholders == {"category": "Intro entrada"}


async def test_no_response(hass, loaded_entry):
    assert await call(hass, data={"category": "lion"}, response=False) is None
    assert loaded_entry.runtime_data.manager.last_selection("lion")["sound_id"] == "roar"
    assert await call(hass, "reset_history", response=False) is None


async def test_reset_category_and_all(hass, loaded_entry):
    await call(hass, data={"category": "intro", "season": "regular"})
    await call(hass, data={"category": "intro", "season": "halloween"})
    await call(hass, data={"category": "lion"})
    assert await call(hass, "reset_history", {"category": "Intro entrada"}) == {"cleared": 2}
    assert loaded_entry.runtime_data.manager.last_selection("intro") is None
    assert loaded_entry.runtime_data.manager.last_selection("lion") is not None
    assert await call(hass, "reset_history") == {"cleared": 1}
    assert await call(hass, "reset_history") == {"cleared": 0}
    with pytest.raises(ServiceValidationError) as err:
        await call(hass, "reset_history", {"category": "missing"})
    assert err.value.translation_key == "unknown_category"


async def test_refresh_and_registration_once(hass, loaded_entry):
    handler = hass.services._services[DOMAIN]["select"]
    await async_register_services(hass)
    assert hass.services._services[DOMAIN]["select"] is handler
    with patch.object(loaded_entry.runtime_data.coordinator, "async_refresh") as refresh:
        await call(hass, "refresh", response=False)
        refresh.assert_awaited_once_with()


@pytest.mark.parametrize("action", ["select", "reset_history", "refresh"])
async def test_no_loaded_entry(hass, action):
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    await async_register_services(hass)
    with pytest.raises(ServiceValidationError) as err:
        await call(hass, action, {"category": "lion"} if action == "select" else {}, response=False)
    assert err.value.translation_key == "not_loaded"
    assert err.value.translation_domain == DOMAIN


async def test_offline_snapshot_selection(hass, aioclient_mock, hass_storage, catalog_payload):
    entry = MockConfigEntry(domain=DOMAIN, data={"host": "studio", "port": 8099, "token": "secret"})
    entry.add_to_hass(hass)
    key = f"{DOMAIN}.{entry.entry_id}.catalog"
    hass_storage[key] = {
        "version": STORAGE_VERSION,
        "minor_version": 1,
        "key": key,
        "data": {"catalog": catalog_payload, "etag": None},
    }
    aioclient_mock.get("http://studio:8099/api/v1/health", exc=TimeoutError())
    aioclient_mock.post("http://studio:8099/api/v1/selections", exc=TimeoutError())
    assert await hass.config_entries.async_setup(entry.entry_id)
    assert not entry.runtime_data.coordinator.data.connected
    assert (await call(hass, data={"category": "lion"}))["sound_id"] == "roar"
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_service_dry_run_preserves_existing_history(hass, loaded_entry, aioclient_mock):
    from custom_components.sound_effects.const import EVENT_SELECTED

    manager = loaded_entry.runtime_data.manager
    await call(hass, data={"category": "intro", "season": "regular"})
    await hass.async_block_till_done()
    before = manager._history_data()
    count = aioclient_mock.call_count
    events = []
    unsub = hass.bus.async_listen(EVENT_SELECTED, events.append)
    result = await call(hass, data={"category": "intro", "season": "regular", "dry_run": True})
    await hass.async_block_till_done()
    assert manager._history_data() == before
    assert aioclient_mock.call_count == count
    assert events == []
    assert await call(hass, data={"category": "intro", "season": "regular"}) == result
    unsub()


async def test_actions_after_unload(hass, loaded_entry):
    assert await hass.config_entries.async_unload(loaded_entry.entry_id)
    with pytest.raises(ServiceValidationError) as err:
        await call(hass, data={"category": "lion"})
    assert err.value.translation_key == "not_loaded"


async def test_action_metadata(hass, loaded_entry):
    from homeassistant.helpers.service import async_get_all_descriptions

    descriptions = (await async_get_all_descriptions(hass))[DOMAIN]
    assert set(descriptions) == {"select", "reset_history", "refresh"}
    select = descriptions["select"]
    assert select["response"] == {"optional": True}
    assert select["fields"]["category"]["required"]
    assert select["fields"]["tags"]["selector"]["text"]["multiple"] is True
    assert "boolean" in select["fields"]["dry_run"]["selector"]
    assert descriptions["reset_history"]["response"] == {"optional": True}
    assert "response" not in descriptions["refresh"]
