"""Season, override, category and connectivity entities."""

import copy
from dataclasses import dataclass
from datetime import datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sound_effects.const import DOMAIN, STORAGE_VERSION

pytestmark = pytest.mark.integration
BASE = "http://studio:8099/api/v1"


@dataclass
class Clock:
    now: datetime


@pytest.fixture(autouse=True)
def clock():
    """Pin the manager's local date to July so tests do not depend on the real calendar."""
    holder = Clock(datetime(2026, 7, 1, 12, tzinfo=dt_util.UTC))
    shim = SimpleNamespace(now=lambda: holder.now, utcnow=dt_util.utcnow)
    with patch("custom_components.sound_effects.manager.dt_util", shim):
        yield holder


def mock_studio(aioclient_mock, payload, version="1.0"):
    aioclient_mock.clear_requests()
    aioclient_mock.get(
        f"{BASE}/health",
        json={"status": "ok", "version": version, "api_version": 1, "instance_id": "studio-id"},
    )
    aioclient_mock.get(f"{BASE}/catalog", json=payload)
    aioclient_mock.post(f"{BASE}/selections", status=204)


def mock_offline(aioclient_mock):
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{BASE}/health", exc=TimeoutError())
    aioclient_mock.post(f"{BASE}/selections", exc=TimeoutError())


def new_entry(hass, options=None):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"host": "studio", "port": 8099, "token": "secret"},
        unique_id="studio-id",
        options={"scan_interval": 3600, **(options or {})},
    )
    entry.add_to_hass(hass)
    return entry


async def setup(hass, entry):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def refresh(hass, entry):
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()


def lookup(hass, entry, platform, suffix):
    return er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{entry.entry_id}_{suffix}")


def entity_id(hass, entry, platform, suffix):
    found = lookup(hass, entry, platform, suffix)
    assert found is not None, f"{platform} {suffix} is not registered"
    return found


async def select_option(hass, select_entity, option):
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": select_entity, "option": option},
        blocking=True,
    )


async def select_sound(hass, **data: Any):
    return await hass.services.async_call(
        DOMAIN, "select", data, blocking=True, return_response=True
    )


def without_halloween(payload):
    changed = copy.deepcopy(payload)
    changed["revision"] = 8
    changed["seasons"] = [item for item in changed["seasons"] if item["id"] != "halloween"]
    changed["sounds"] = [item for item in changed["sounds"] if item["id"] != "boo"]
    return changed


async def test_entities_and_device(hass, loaded_entry):
    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, loaded_entry.entry_id)
    assert {
        (item.domain, item.unique_id.removeprefix(f"{loaded_entry.entry_id}_")) for item in entities
    } == {
        ("sensor", "active_season"),
        ("select", "season_override"),
        ("binary_sensor", "connected"),
        ("sensor", "category_intro"),
        ("sensor", "category_lion"),
        ("sensor", "category_bath"),
    }
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, loaded_entry.entry_id)})
    assert device is not None
    assert device.name == "Sound Effects Studio"
    assert device.entry_type is DeviceEntryType.SERVICE
    assert device.sw_version == "1.0"
    assert {item.device_id for item in entities} == {device.id}
    # Translated entity names are prefixed with the device name.
    expected = {
        ("sensor", "active_season"): "Sound Effects Studio Active season",
        ("select", "season_override"): "Sound Effects Studio Season override",
        ("binary_sensor", "connected"): "Sound Effects Studio Connected",
        ("sensor", "category_intro"): "Sound Effects Studio Intro entrada",
        ("sensor", "category_lion"): "Sound Effects Studio León",
    }
    for (platform, suffix), name in expected.items():
        state = hass.states.get(entity_id(hass, loaded_entry, platform, suffix))
        assert state is not None
        assert state.name == name


async def test_active_season_sensor_follows_override_select(hass, loaded_entry):
    sensor = entity_id(hass, loaded_entry, "sensor", "active_season")
    override = entity_id(hass, loaded_entry, "select", "season_override")
    state = hass.states.get(sensor)
    assert state.state == "regular"
    assert state.attributes["name"] == "Regular"
    assert state.attributes["source"] == "default"
    assert state.attributes["color"] == "#64748b"
    assert hass.states.get(override).state == "Auto"
    assert hass.states.get(override).attributes["options"] == ["Auto", "Regular", "Halloween"]

    await select_option(hass, override, "Halloween")
    state = hass.states.get(sensor)
    assert state.state == "halloween"
    assert state.attributes["name"] == "Halloween"
    assert state.attributes["source"] == "override"
    assert state.attributes["color"] == "#f97316"
    assert hass.states.get(override).state == "Halloween"
    assert loaded_entry.runtime_data.manager.override_season == "halloween"

    await select_option(hass, override, "Auto")
    assert hass.states.get(override).state == "Auto"
    assert loaded_entry.runtime_data.manager.override_season is None
    assert hass.states.get(sensor).state == "regular"
    assert hass.states.get(sensor).attributes["source"] == "default"


async def test_active_season_updates_on_coordinator_refresh(
    hass, loaded_entry, aioclient_mock, catalog_payload, clock
):
    sensor = entity_id(hass, loaded_entry, "sensor", "active_season")
    assert hass.states.get(sensor).state == "regular"
    clock.now = datetime(2026, 10, 4, 12, tzinfo=dt_util.UTC)
    assert hass.states.get(sensor).state == "regular"  # nothing re-evaluated it yet
    mock_studio(aioclient_mock, catalog_payload)
    await refresh(hass, loaded_entry)
    state = hass.states.get(sensor)
    assert state.state == "halloween"
    assert state.attributes["source"] == "calendar"


async def test_active_season_refreshes_after_midnight(hass, loaded_entry, clock):
    with patch(
        "custom_components.sound_effects.sensor.async_track_time_change",
        wraps=async_track_time_change,
    ) as track:
        assert await hass.config_entries.async_reload(loaded_entry.entry_id)
        await hass.async_block_till_done()
    track.assert_called_once()
    assert track.call_args.kwargs == {"hour": 0, "minute": 0, "second": 5}
    on_midnight = track.call_args.args[1]
    sensor = entity_id(hass, loaded_entry, "sensor", "active_season")
    assert hass.states.get(sensor).state == "regular"
    clock.now = datetime(2026, 10, 1, 0, 0, 5, tzinfo=dt_util.UTC)
    on_midnight(clock.now)
    assert hass.states.get(sensor).state == "halloween"


async def test_active_season_tracks_season_entity(hass, aioclient_mock, catalog_payload):
    entry = new_entry(hass, {"season_entity": "input_select.season"})
    mock_studio(aioclient_mock, catalog_payload)
    await setup(hass, entry)
    sensor = entity_id(hass, entry, "sensor", "active_season")
    assert hass.states.get(sensor).attributes["source"] == "default"

    hass.states.async_set("input_select.season", "Halloween")
    await hass.async_block_till_done()
    state = hass.states.get(sensor)
    assert state.state == "halloween"
    assert state.attributes["source"] == "entity"

    hass.states.async_set("input_select.season", "unavailable")
    await hass.async_block_till_done()
    assert hass.states.get(sensor).state == "regular"
    assert hass.states.get(sensor).attributes["source"] == "default"

    assert await hass.config_entries.async_unload(entry.entry_id)
    hass.states.async_set("input_select.season", "Halloween")
    await hass.async_block_till_done()


async def test_override_select_options_follow_catalog(
    hass, loaded_entry, aioclient_mock, catalog_payload
):
    override = entity_id(hass, loaded_entry, "select", "season_override")
    sensor = entity_id(hass, loaded_entry, "sensor", "active_season")
    await select_option(hass, override, "Halloween")

    renamed = copy.deepcopy(catalog_payload)
    renamed["revision"] = 8
    renamed["seasons"][1]["name"] = "Spooky"
    mock_studio(aioclient_mock, renamed)
    await refresh(hass, loaded_entry)
    state = hass.states.get(override)
    assert state.state == "Spooky"  # the override is stored by id, shown by name
    assert state.attributes["options"] == ["Auto", "Regular", "Spooky"]
    assert hass.states.get(sensor).attributes["name"] == "Spooky"
    await select_option(hass, override, "Auto")
    await select_option(hass, override, "Spooky")

    mock_studio(aioclient_mock, without_halloween(catalog_payload))
    await refresh(hass, loaded_entry)
    state = hass.states.get(override)
    assert state.state == "Auto"  # the override points at a deleted season
    assert state.attributes["options"] == ["Auto", "Regular"]
    assert hass.states.get(sensor).state == "regular"


async def test_category_sensor_before_any_selection(hass, loaded_entry):
    state = hass.states.get(entity_id(hass, loaded_entry, "sensor", "category_intro"))
    assert state.state == STATE_UNKNOWN
    assert state.attributes["icon"] == "mdi:door-open"
    assert state.attributes["category_id"] == "intro"
    assert state.attributes["available"] == 3
    for key in ("sound_id", "key", "url", "duration", "season", "selected_at"):
        assert state.attributes[key] is None
    lion = hass.states.get(entity_id(hass, loaded_entry, "sensor", "category_lion"))
    assert lion.attributes["icon"] == "mdi:paw"
    assert lion.attributes["available"] == 1


async def test_category_sensor_updates_after_select(hass, loaded_entry):
    sensor = entity_id(hass, loaded_entry, "sensor", "category_intro")
    result = await select_sound(hass, category="intro")
    state = hass.states.get(sensor)
    assert state.state == result["title"]
    manager = loaded_entry.runtime_data.manager
    assert {
        key: state.attributes[key]
        for key in (
            "category_id",
            "sound_id",
            "key",
            "url",
            "duration",
            "season",
            "selected_at",
            "available",
        )
    } == {
        "category_id": "intro",
        "sound_id": result["sound_id"],
        "key": result["key"],
        "url": result["url"],
        "duration": 2.5,
        "season": "regular",
        "selected_at": manager.last_selection("intro")["selected_at"],
        "available": 3,
    }
    assert state.attributes["selected_at"].endswith("Z")
    # Other categories are untouched.
    assert hass.states.get(entity_id(hass, loaded_entry, "sensor", "category_lion")).state == (
        STATE_UNKNOWN
    )


async def test_category_available_follows_override(hass, loaded_entry):
    intro = entity_id(hass, loaded_entry, "sensor", "category_intro")
    bath = entity_id(hass, loaded_entry, "sensor", "category_bath")
    assert hass.states.get(intro).attributes["available"] == 3
    await select_option(
        hass, entity_id(hass, loaded_entry, "select", "season_override"), "Halloween"
    )
    assert hass.states.get(intro).attributes["available"] == 1  # boo
    assert hass.states.get(bath).attributes["available"] == 2  # falls back to regular


async def test_category_entities_added_and_removed(
    hass, loaded_entry, aioclient_mock, catalog_payload
):
    registry = er.async_get(hass)
    bath = entity_id(hass, loaded_entry, "sensor", "category_bath")
    assert lookup(hass, loaded_entry, "sensor", "category_kids") is None

    changed = copy.deepcopy(catalog_payload)
    changed["revision"] = 8
    changed["categories"] = [item for item in changed["categories"] if item["id"] != "bath"]
    changed["categories"].append(
        {
            "id": "kids",
            "name": "Kids",
            "icon": "mdi:teddy-bear",
            "color": "#ec4899",
            "description": "",
            "sort_order": 3,
        }
    )
    changed["sounds"] = [item for item in changed["sounds"] if item["category_id"] != "bath"]
    changed["sounds"].append(
        {
            **changed["sounds"][0],
            "id": "bear",
            "category_id": "kids",
            "title": "Bear",
            "key": "bear.mp3",
        }
    )
    mock_studio(aioclient_mock, changed)
    await refresh(hass, loaded_entry)

    kids = entity_id(hass, loaded_entry, "sensor", "category_kids")
    state = hass.states.get(kids)
    assert state.state == STATE_UNKNOWN
    assert state.name == "Sound Effects Studio Kids"
    assert state.attributes["icon"] == "mdi:teddy-bear"
    assert state.attributes["available"] == 1
    assert registry.async_get(kids).device_id is not None
    assert lookup(hass, loaded_entry, "sensor", "category_bath") is None
    assert registry.async_get(bath) is None
    assert hass.states.get(bath) is None
    # Existing categories survive the catalog change.
    assert lookup(hass, loaded_entry, "sensor", "category_intro") is not None


async def test_category_rename_updates_friendly_name(
    hass, loaded_entry, aioclient_mock, catalog_payload
):
    sensor = entity_id(hass, loaded_entry, "sensor", "category_lion")
    renamed = copy.deepcopy(catalog_payload)
    renamed["revision"] = 8
    renamed["categories"][1].update({"name": "Leones", "icon": "mdi:cat"})
    mock_studio(aioclient_mock, renamed)
    await refresh(hass, loaded_entry)
    state = hass.states.get(sensor)
    assert state.name == "Sound Effects Studio Leones"
    assert state.attributes["icon"] == "mdi:cat"


async def test_stale_category_entities_removed_at_setup(hass, aioclient_mock, catalog_payload):
    entry = new_entry(hass)
    registry = er.async_get(hass)
    stale = registry.async_get_or_create(
        "sensor", DOMAIN, f"{entry.entry_id}_category_gone", config_entry=entry
    )
    mock_studio(aioclient_mock, catalog_payload)
    await setup(hass, entry)
    assert registry.async_get(stale.entity_id) is None
    assert lookup(hass, entry, "sensor", "category_intro") is not None
    assert lookup(hass, entry, "sensor", "active_season") is not None
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_connectivity_sensor(hass, loaded_entry, aioclient_mock, catalog_payload):
    connected = entity_id(hass, loaded_entry, "binary_sensor", "connected")
    registry_entry = er.async_get(hass).async_get(connected)
    assert registry_entry.entity_category is EntityCategory.DIAGNOSTIC
    state = hass.states.get(connected)
    assert state.state == STATE_ON
    assert state.attributes["device_class"] == "connectivity"
    last_sync = loaded_entry.runtime_data.coordinator.data.last_sync.isoformat().replace(
        "+00:00", "Z"
    )
    assert state.attributes["catalog_revision"] == 7
    assert state.attributes["app_version"] == "1.0"
    assert state.attributes["last_sync"] == last_sync

    mock_offline(aioclient_mock)
    await refresh(hass, loaded_entry)
    state = hass.states.get(connected)
    assert state.state == STATE_OFF
    assert state.attributes["catalog_revision"] == 7
    assert state.attributes["last_sync"] == last_sync
    assert state.attributes["app_version"] == "1.0"
    # The cached catalog keeps selection entities usable while Studio is offline.
    intro = hass.states.get(entity_id(hass, loaded_entry, "sensor", "category_intro"))
    assert intro.state != STATE_UNAVAILABLE
    assert (await select_sound(hass, category="lion"))["sound_id"] == "roar"
    await hass.async_block_till_done(wait_background_tasks=True)

    mock_studio(aioclient_mock, catalog_payload)
    await refresh(hass, loaded_entry)
    assert hass.states.get(connected).state == STATE_ON


async def test_device_version_updates_after_reconnect(
    hass, aioclient_mock, hass_storage, catalog_payload
):
    entry = new_entry(hass)
    hass_storage[f"{DOMAIN}.{entry.entry_id}.catalog"] = {
        "version": STORAGE_VERSION,
        "minor_version": 1,
        "key": f"{DOMAIN}.{entry.entry_id}.catalog",
        "data": {"etag": None, "catalog": catalog_payload},
    }
    mock_offline(aioclient_mock)
    await setup(hass, entry)
    assert hass.states.get(entity_id(hass, entry, "binary_sensor", "connected")).state == STATE_OFF
    devices = dr.async_get(hass)
    device = devices.async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    assert device is not None
    assert device.sw_version is None

    mock_studio(aioclient_mock, catalog_payload, version="2.0.1")
    await refresh(hass, entry)
    device = devices.async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    assert device.sw_version == "2.0.1"
    assert hass.states.get(entity_id(hass, entry, "binary_sensor", "connected")).state == STATE_ON
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_unload_detaches_listeners(hass, loaded_entry):
    manager = loaded_entry.runtime_data.manager
    assert manager._listeners
    assert await hass.config_entries.async_unload(loaded_entry.entry_id)
    assert manager._listeners == []
    entities = er.async_entries_for_config_entry(er.async_get(hass), loaded_entry.entry_id)
    assert len(entities) == 6
    assert {hass.states.get(item.entity_id).state for item in entities} == {STATE_UNAVAILABLE}


async def test_season_input_change_updates_category_counts(hass, aioclient_mock, catalog_payload):
    entry = new_entry(hass, {"season_entity": "input_select.season"})
    mock_studio(aioclient_mock, catalog_payload)
    await setup(hass, entry)
    intro = entity_id(hass, entry, "sensor", "category_intro")
    assert hass.states.get(intro).attributes["available"] == 3
    hass.states.async_set("input_select.season", "Halloween")
    await hass.async_block_till_done()
    assert hass.states.get(intro).attributes["available"] == 1
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_midnight_timer_and_cleanup(hass, aioclient_mock, catalog_payload, clock, freezer):
    from unittest.mock import Mock

    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    # Use a non-UTC zone to verify that this timer follows HA's local midnight.
    await hass.config.async_set_time_zone("America/Costa_Rica")
    freezer.move_to("2026-10-01T05:59:50Z")
    clock.now = dt_util.as_local(dt_util.utcnow())
    entry = new_entry(hass)
    mock_studio(aioclient_mock, catalog_payload)
    removers = []

    def track(*args, **kwargs):
        remove = Mock(wraps=async_track_time_change(*args, **kwargs))
        removers.append(remove)
        return remove

    with patch("custom_components.sound_effects.sensor.async_track_time_change", side_effect=track):
        await setup(hass, entry)
    active = entity_id(hass, entry, "sensor", "active_season")
    intro = entity_id(hass, entry, "sensor", "category_intro")
    assert hass.states.get(active).state == "regular"
    assert hass.states.get(intro).attributes["available"] == 3
    clock.now = dt_util.as_local(dt_util.parse_datetime("2026-10-01T06:00:05Z"))
    async_fire_time_changed(hass, clock.now)
    await hass.async_block_till_done()
    assert hass.states.get(active).state == "halloween"
    assert hass.states.get(intro).attributes["available"] == 1
    coordinator = entry.runtime_data.coordinator
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert len(removers) == 1
    removers[0].assert_called_once_with()
    assert coordinator._listeners == {}
    assert coordinator._unsub_refresh is None
    assert not entry._background_tasks


async def test_options_reload_replaces_season_subscription(hass, loaded_entry):
    # Option changes reload the entry, replacing the old season entity subscription.
    hass.config_entries.async_update_entry(
        loaded_entry, options={**loaded_entry.options, "season_entity": "input_select.old_season"}
    )
    await hass.async_block_till_done()
    old_manager = loaded_entry.runtime_data.manager
    hass.config_entries.async_update_entry(
        loaded_entry, options={**loaded_entry.options, "season_entity": "input_select.new_season"}
    )
    await hass.async_block_till_done()
    assert old_manager._listeners == []
    sensor = entity_id(hass, loaded_entry, "sensor", "active_season")
    hass.states.async_set("input_select.old_season", "Halloween")
    await hass.async_block_till_done()
    assert hass.states.get(sensor).state == "regular"
    hass.states.async_set("input_select.new_season", "Halloween")
    await hass.async_block_till_done()
    assert hass.states.get(sensor).state == "halloween"


async def test_disabled_season_sensor_does_not_break_category_updates(
    hass, aioclient_mock, catalog_payload
):
    entry = new_entry(hass, {"season_entity": "input_select.season"})
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_active_season",
        config_entry=entry,
        disabled_by=er.RegistryEntryDisabler.USER,
    )
    mock_studio(aioclient_mock, catalog_payload)
    await setup(hass, entry)
    intro = entity_id(hass, entry, "sensor", "category_intro")
    hass.states.async_set("input_select.season", "Halloween")
    await hass.async_block_till_done()
    assert hass.states.get(intro).attributes["available"] == 1
    assert await hass.config_entries.async_unload(entry.entry_id)
