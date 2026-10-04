"""Cached selection, delayed history, and entry lifecycle guarantees."""

import asyncio
import random
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.network import NoURLAvailableError
from homeassistant.util import dt as dt_util

from custom_components.sound_effects.api import StudioAuthError, StudioConnectionError
from custom_components.sound_effects.const import DOMAIN, EVENT_SELECTED
from custom_components.sound_effects.manager import SoundEffectsManager

pytestmark = pytest.mark.integration


async def test_full_response_and_no_io(hass, loaded_entry, aioclient_mock, hass_storage):
    manager = loaded_entry.runtime_data.manager
    assert isinstance(manager, SoundEffectsManager)
    count = aioclient_mock.call_count
    with patch.object(manager._store, "async_save", side_effect=AssertionError("inline I/O")):
        response = await manager.async_select(category="León", season="regular")
        assert aioclient_mock.call_count == count
        assert f"{DOMAIN}.{loaded_entry.entry_id}.history" not in hass_storage
    assert response == {
        "sound_id": "roar",
        "key": "roar.mp3",
        "title": "Roar",
        "category": "lion",
        "tags": [],
        "season": "regular",
        "requested_season": "regular",
        "season_fallback": False,
        "path": "/local/sound-effects/roar-r1.mp3",
        "url": "https://ha.example/local/sound-effects/roar-r1.mp3",
        "duration": 2.5,
        "revision": 1,
        "mime_type": "audio/mpeg",
    }
    assert manager.last_selection("lion") == {
        **response,
        "selected_at": manager.last_selection("lion")["selected_at"],
    }
    assert manager.last_selection("lion")["selected_at"].endswith("Z")
    await hass.async_block_till_done(wait_background_tasks=True)
    post = aioclient_mock.mock_calls[-1]
    assert post[0] == "POST"
    assert post[2] == {
        "events": [
            {
                "sound_id": "roar",
                "category_id": "lion",
                "season_id": "regular",
                "selected_at": manager.last_selection("lion")["selected_at"],
            }
        ]
    }


async def test_selection_returns_while_network_and_storage_blocked(hass, loaded_entry):
    manager = loaded_entry.runtime_data.manager
    gate = asyncio.Event()
    post_started = asyncio.Event()

    async def blocked_post(events):
        post_started.set()
        await gate.wait()

    with (
        patch.object(loaded_entry.runtime_data.client, "post_selections", blocked_post),
        patch.object(manager._store, "async_save", new=AsyncMock(side_effect=AssertionError)),
        patch.object(manager._store, "async_delay_save") as delayed,
    ):
        response = await asyncio.wait_for(manager.async_select(category="lion"), timeout=0.2)
        assert response["sound_id"] == "roar"
        await asyncio.wait_for(post_started.wait(), timeout=0.2)
        delayed.assert_called_once_with(manager._history_data, 1.0)
    # Unloading must cancel the blocked entry-owned task.
    assert await hass.config_entries.async_unload(loaded_entry.entry_id)
    assert not loaded_entry._background_tasks


async def test_dry_run_has_no_side_effects(hass, loaded_entry, aioclient_mock, hass_storage):
    manager = loaded_entry.runtime_data.manager
    events = []
    unsub = hass.bus.async_listen(EVENT_SELECTED, events.append)
    listener = Mock()
    remove = manager.async_add_listener(listener)
    count = aioclient_mock.call_count
    rng_state = manager._rng.getstate()
    with patch.object(manager._store, "async_delay_save") as delayed:
        response = await manager.async_select(category="intro", season="regular", dry_run=True)
        assert manager.last_selection("intro") is None
        assert await manager.async_reset_history() == 0
        delayed.assert_not_called()
    assert manager._rng.getstate() == rng_state
    await hass.async_block_till_done()
    assert response["sound_id"] in {"fox", "universal", "pirates"}
    assert events == []
    listener.assert_not_called()
    assert aioclient_mock.call_count == count
    assert f"{DOMAIN}.{loaded_entry.entry_id}.history" not in hass_storage
    remove()
    unsub()


async def test_event_and_listeners(hass, loaded_entry):
    manager = loaded_entry.runtime_data.manager
    events = []
    unsub = hass.bus.async_listen(EVENT_SELECTED, events.append)
    listener = Mock()
    remove = manager.async_add_listener(listener)
    response = await manager.async_select(category="lion")
    await hass.async_block_till_done()
    assert [event.data for event in events] == [response]
    listener.assert_called_once_with()
    remove()
    await manager.async_select(category="lion")
    assert listener.call_count == 1
    unsub()


async def test_history_survives_reload(hass, loaded_entry, hass_storage):
    manager = loaded_entry.runtime_data.manager
    first = await manager.async_select(category="intro", season="regular")
    await manager.async_set_override("halloween")
    assert await hass.config_entries.async_reload(loaded_entry.entry_id)
    manager = loaded_entry.runtime_data.manager
    assert manager.override_season == "halloween"
    assert manager.last_selection("intro")["sound_id"] == first["sound_id"]
    history = hass_storage[f"{DOMAIN}.{loaded_entry.entry_id}.history"]["data"]
    assert history["bags"]["intro|regular|"]["played"] == [first["sound_id"]]
    rest = [await manager.async_select(category="intro", season="regular") for _ in range(2)]
    assert {first["sound_id"], *(item["sound_id"] for item in rest)} == {
        "fox",
        "universal",
        "pirates",
    }


async def test_override_count_and_action_precedence(loaded_entry):
    manager = loaded_entry.runtime_data.manager
    listener = Mock()
    remove = manager.async_add_listener(listener)
    await manager.async_set_override("Halloween")
    assert manager.override_season == "halloween"
    assert manager.active_season() == ("halloween", "override")
    assert manager.available_count("intro") == 1
    assert manager.available_count("bath") == 2
    assert manager.available_count("missing") == 0
    assert (await manager.async_select(category="intro"))["sound_id"] == "boo"
    assert (await manager.async_select(category="intro", season="regular"))["season"] == "regular"
    await manager.async_set_override(None)
    assert manager.override_season is None
    with pytest.raises(ServiceValidationError) as err:
        await manager.async_set_override("missing")
    assert err.value.translation_key == "unknown_season"
    assert listener.call_count == 4
    remove()


@pytest.mark.parametrize("state", [None, "unknown", "unavailable", "Regular", "Halloween"])
async def test_season_entity(hass, loaded_entry, state):
    # Updating options schedules a runtime reload after these immediate assertions.
    hass.config_entries.async_update_entry(
        loaded_entry, options={**loaded_entry.options, "season_entity": "input_select.season"}
    )
    if state is not None:
        hass.states.async_set("input_select.season", state)
    with patch(
        "custom_components.sound_effects.manager.dt_util.now", return_value=datetime(2026, 7, 1)
    ):
        expected = (
            ("halloween", "entity")
            if state == "Halloween"
            else (("regular", "entity") if state == "Regular" else ("regular", "default"))
        )
        assert loaded_entry.runtime_data.manager.active_season() == expected
    await hass.async_block_till_done()


@pytest.mark.parametrize(
    "url, expected", [("http://ha.local:8123/", "http://ha.local:8123/"), (None, "")]
)
async def test_base_url_options_absent(hass, loaded_entry, url, expected):
    # Updating options schedules a runtime reload after these immediate assertions.
    hass.config_entries.async_update_entry(loaded_entry, options={"scan_interval": 3600})
    manager = loaded_entry.runtime_data.manager
    with patch("custom_components.sound_effects.manager.get_url") as get_url:
        if url is None:
            get_url.side_effect = NoURLAvailableError
        else:
            get_url.return_value = url
        assert manager.base_url() == expected
        response = await manager.async_select(category="lion", dry_run=True)
        assert response["url"] == f"{expected.rstrip('/')}{response['path']}"
        get_url.assert_called_with(hass, allow_external=False, prefer_external=False)
    await hass.async_block_till_done()


@pytest.mark.parametrize("error", [StudioConnectionError, StudioAuthError])
async def test_reporting_failure_is_swallowed(hass, loaded_entry, error, caplog):
    with patch.object(
        loaded_entry.runtime_data.client, "post_selections", side_effect=error
    ) as post:
        assert (await loaded_entry.runtime_data.manager.async_select(category="lion"))[
            "sound_id"
        ] == "roar"
        task = next(iter(loaded_entry._background_tasks))
        await hass.async_block_till_done(wait_background_tasks=True)
        post.assert_awaited_once()
        assert task.done()
        assert not task.cancelled()
        assert task.exception() is None
    assert "Error doing job" not in caplog.text


async def test_concurrent_draws(loaded_entry):
    manager = loaded_entry.runtime_data.manager
    manager._rng = random.Random(42)
    results = await asyncio.gather(
        *(manager.async_select(category="intro", season="regular") for _ in range(3))
    )
    assert {result["sound_id"] for result in results} == {"fox", "universal", "pirates"}


async def test_delayed_history_save(hass, loaded_entry, hass_storage):
    from datetime import timedelta

    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    manager = loaded_entry.runtime_data.manager
    await manager.async_select(category="lion")
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=2), fire_all=True)
    await hass.async_block_till_done()
    assert (
        hass_storage[f"{DOMAIN}.{loaded_entry.entry_id}.history"]["data"]["last"]["lion"][
            "sound_id"
        ]
        == "roar"
    )


async def test_remove_history(hass, loaded_entry, hass_storage):
    await loaded_entry.runtime_data.manager.async_select(category="lion")
    await hass.config_entries.async_remove(loaded_entry.entry_id)
    await hass.async_block_till_done()
    assert f"{DOMAIN}.{loaded_entry.entry_id}.history" not in hass_storage
    assert f"{DOMAIN}.{loaded_entry.entry_id}.catalog" not in hass_storage


async def test_raising_listener_does_not_interrupt_selection(hass, loaded_entry, caplog):
    manager = loaded_entry.runtime_data.manager
    tasks_seen = []

    def broken():
        tasks_seen.extend(loaded_entry._background_tasks)
        raise RuntimeError("broken listener")

    good = Mock()
    remove_broken = manager.async_add_listener(broken)
    remove_good = manager.async_add_listener(good)
    with patch.object(loaded_entry.runtime_data.client, "post_selections") as post:
        response = await manager.async_select(category="lion")
        await hass.async_block_till_done(wait_background_tasks=True)
        post.assert_awaited_once()
    assert response["sound_id"] == "roar"
    assert tasks_seen  # Reporting is scheduled before any listener runs.
    assert all(task.done() and task.exception() is None for task in tasks_seen)
    good.assert_called_once_with()
    assert "broken listener" in caplog.text
    remove_broken()
    remove_good()


async def test_invalid_override_includes_value(loaded_entry):
    with pytest.raises(ServiceValidationError) as err:
        await loaded_entry.runtime_data.manager.async_set_override("missing override")
    assert err.value.translation_placeholders == {"season": "missing override"}
