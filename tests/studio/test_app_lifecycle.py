"""Background services started by the app lifespan: discovery, media URL, events, cleanup."""

import asyncio
import json
import logging
import os
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import sound_effects_studio.lifecycle as lifecycle
from sound_effects_studio.app import create_app
from sound_effects_studio.config import Paths
from sound_effects_studio.models import CategoryCreate, Settings
from sound_effects_studio.supervisor import SupervisorClient

pytestmark = pytest.mark.studio

HOSTNAME = "local-sound-effects-studio"
REAL_CHECK_WWW_SERVED = lifecycle.check_www_served
REAL_WAIT_FOR_SERVER = lifecycle.wait_for_server

Routes = dict[tuple[str, str], httpx.Response | Exception]


@dataclass
class FakeSupervisor:
    """A Supervisor stand-in that records requests and answers from a mutable route table."""

    routes: Routes = field(default_factory=dict)
    requests: list[httpx.Request] = field(default_factory=list)

    def __post_init__(self) -> None:
        defaults: Routes = {
            ("GET", "/addons/self/info"): httpx.Response(
                200, json={"data": {"hostname": HOSTNAME}}
            ),
            ("POST", "/discovery"): httpx.Response(200, json={"data": {"uuid": "uuid-new"}}),
            ("GET", "/core/api/config"): httpx.Response(
                200, json={"internal_url": "http://ha.local:8123"}
            ),
            ("POST", "/core/api/events/sound_effects_catalog_changed"): httpx.Response(
                200, json={"message": "fired"}
            ),
        }
        self.routes = {**defaults, **self.routes}

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        result = self.routes.get((request.method, request.url.path))
        if result is None:
            return httpx.Response(404, json={"result": "error", "message": "not routed"})
        if isinstance(result, Exception):
            raise result
        return result

    def client(self) -> SupervisorClient:
        http = httpx.AsyncClient(transport=httpx.MockTransport(self.handle))
        return SupervisorClient("sup-token", client=http)

    def calls(self) -> list[tuple[str, str]]:
        return [(r.method, r.url.path) for r in self.requests]

    def body(self, method: str, path: str) -> object:
        request = next(r for r in self.requests if (r.method, r.url.path) == (method, path))
        return json.loads(request.content)


@dataclass
class Probe:
    """Stands in for the Home Assistant /local probe and records what it was asked."""

    served: bool = True
    calls: list[tuple[Path, str]] = field(default_factory=list)


@pytest.fixture(autouse=True)
def probe(monkeypatch: pytest.MonkeyPatch) -> Probe:
    """No real network: the /local probe is faked and the server-listening wait is instant."""
    fake = Probe()

    async def served(
        publish_dir: Path,
        client: httpx.AsyncClient | None = None,
        *,
        base_url: str = lifecycle.DEFAULT_CORE_URL,
    ) -> bool:
        fake.calls.append((publish_dir, base_url))
        return fake.served

    async def listening(*args: object, **kwargs: object) -> bool:
        return True

    monkeypatch.setattr(lifecycle, "check_www_served", served)
    monkeypatch.setattr(lifecycle, "wait_for_server", listening)
    return fake


@pytest.fixture
def made(paths: Paths) -> Iterator[list[FastAPI]]:
    apps: list[FastAPI] = []
    yield apps
    for app in apps:
        app.state.db.close()


def build(
    made: list[FastAPI],
    paths: Paths,
    supervisor: SupervisorClient | None = None,
    *,
    start_background: bool = True,
) -> FastAPI:
    app = create_app(paths, supervisor=supervisor, start_background=start_background)
    made.append(app)
    return app


def wait_for(condition: Callable[[], bool], timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


def discovery_status(app: FastAPI) -> str:
    return app.state.discovery_status["status"]


def remembered_uuids(paths: Paths) -> list[str]:
    path = paths.data_dir / "discovery_uuid"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


# --- discovery -----------------------------------------------------------------------------


def test_lifespan_publishes_discovery_and_replaces_the_previous_one(
    paths: Paths, made: list[FastAPI]
):
    (paths.data_dir / "discovery_uuid").write_text("uuid-old", encoding="utf-8")
    fake = FakeSupervisor(routes={("DELETE", "/discovery/uuid-old"): httpx.Response(200, json={})})
    app = build(made, paths, fake.client())
    with TestClient(app):
        assert wait_for(lambda: discovery_status(app) == "ok")
        assert app.state.discovery_status == {"status": "ok", "message": None}
        assert app.state.hostname == HOSTNAME
    calls = fake.calls()
    assert calls.index(("DELETE", "/discovery/uuid-old")) < calls.index(("POST", "/discovery"))
    assert fake.body("POST", "/discovery") == {
        "service": "sound_effects",
        "config": {
            "host": HOSTNAME,
            "port": 8099,
            "token": app.state.tokens.get(),
            "instance_id": app.state.instance_id,
        },
    }
    assert remembered_uuids(paths) == ["uuid-new"]


def test_first_start_publishes_without_deleting(paths: Paths, made: list[FastAPI]):
    fake = FakeSupervisor()
    app = build(made, paths, fake.client())
    with TestClient(app):
        assert wait_for(lambda: discovery_status(app) == "ok")
    assert all(method != "DELETE" for method, _ in fake.calls())
    assert remembered_uuids(paths) == ["uuid-new"]


def test_a_discovery_that_cannot_be_deleted_is_retried_on_the_next_start(
    paths: Paths, made: list[FastAPI]
):
    (paths.data_dir / "discovery_uuid").write_text("uuid-old", encoding="utf-8")
    refused = httpx.Response(500, json={"message": "supervisor busy"})
    first = FakeSupervisor(routes={("DELETE", "/discovery/uuid-old"): refused})
    app = build(made, paths, first.client())
    with TestClient(app):
        assert wait_for(lambda: discovery_status(app) == "ok")
    assert remembered_uuids(paths) == ["uuid-old", "uuid-new"]

    second = FakeSupervisor(
        routes={
            ("DELETE", "/discovery/uuid-old"): httpx.Response(200, json={}),
            ("DELETE", "/discovery/uuid-new"): httpx.Response(200, json={}),
            ("POST", "/discovery"): httpx.Response(200, json={"data": {"uuid": "uuid-3"}}),
        }
    )
    again = build(made, paths, second.client())
    with TestClient(again):
        assert wait_for(lambda: discovery_status(again) == "ok")
    assert ("DELETE", "/discovery/uuid-old") in second.calls()
    assert ("DELETE", "/discovery/uuid-new") in second.calls()
    assert remembered_uuids(paths) == ["uuid-3"]


def test_a_discovery_the_supervisor_no_longer_knows_is_forgotten(paths: Paths, made: list[FastAPI]):
    (paths.data_dir / "discovery_uuid").write_text("uuid-old", encoding="utf-8")
    gone = httpx.Response(404, json={"result": "error", "message": "Gone"})
    fake = FakeSupervisor(routes={("DELETE", "/discovery/uuid-old"): gone})
    app = build(made, paths, fake.client())
    with TestClient(app):
        assert wait_for(lambda: discovery_status(app) == "ok")
    assert remembered_uuids(paths) == ["uuid-new"]


def test_a_not_found_message_with_another_status_remains_pending(paths: Paths, made: list[FastAPI]):
    (paths.data_dir / "discovery_uuid").write_text("uuid-old", encoding="utf-8")
    refused = httpx.Response(400, json={"message": "Discovery not found"})
    fake = FakeSupervisor(routes={("DELETE", "/discovery/uuid-old"): refused})
    app = build(made, paths, fake.client())
    with TestClient(app):
        assert wait_for(lambda: discovery_status(app) == "ok")
    assert remembered_uuids(paths) == ["uuid-old", "uuid-new"]


async def test_failed_deletes_remain_pending_when_publishing_also_fails(
    paths: Paths, made: list[FastAPI]
):
    pending = ["uuid-deleted", "uuid-pending"]
    (paths.data_dir / "discovery_uuid").write_text(json.dumps(pending), encoding="utf-8")
    fake = FakeSupervisor(
        routes={
            ("DELETE", "/discovery/uuid-deleted"): httpx.Response(200, json={}),
            ("DELETE", "/discovery/uuid-pending"): httpx.Response(503, text="busy"),
            ("POST", "/discovery"): httpx.Response(503, text="busy"),
        }
    )
    app = build(made, paths, fake.client(), start_background=False)
    await lifecycle.publish_discovery(app)
    assert discovery_status(app) == "failed"
    assert remembered_uuids(paths) == ["uuid-pending"]
    fake.routes[("DELETE", "/discovery/uuid-pending")] = httpx.Response(200, json={})
    fake.routes[("POST", "/discovery")] = httpx.Response(200, json={"data": {"uuid": "next"}})
    await lifecycle.publish_discovery(app)
    assert fake.calls().count(("DELETE", "/discovery/uuid-pending")) == 2
    assert discovery_status(app) == "ok"
    assert remembered_uuids(paths) == ["next"]


def test_all_undeletable_discoveries_are_kept_for_retry(paths: Paths, made: list[FastAPI]):
    old = [f"uuid-{n}" for n in range(8)]
    (paths.data_dir / "discovery_uuid").write_text(json.dumps(old), encoding="utf-8")
    refused = httpx.Response(500, text="no")
    fake = FakeSupervisor(routes={("DELETE", f"/discovery/{u}"): refused for u in old})
    app = build(made, paths, fake.client())
    with TestClient(app):
        assert wait_for(lambda: discovery_status(app) == "ok")
    assert remembered_uuids(paths) == [*old, "uuid-new"]


def test_discovery_failure_is_reported_and_the_app_keeps_running(paths: Paths, made: list[FastAPI]):
    fake = FakeSupervisor(
        routes={("POST", "/discovery"): httpx.Response(400, json={"message": "service refused"})}
    )
    app = build(made, paths, fake.client())
    with TestClient(app) as client:
        assert wait_for(lambda: discovery_status(app) == "failed")
        assert "service refused" in str(app.state.discovery_status["message"])
        health = client.get(
            "/api/v1/health", headers={"Authorization": f"Bearer {app.state.tokens.get()}"}
        )
        assert health.status_code == 200
    assert remembered_uuids(paths) == []


def test_unreachable_supervisor_does_not_stop_startup(paths: Paths, made: list[FastAPI]):
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    http = httpx.AsyncClient(transport=httpx.MockTransport(refuse))
    app = build(made, paths, SupervisorClient("tok", client=http))
    with TestClient(app):
        assert wait_for(lambda: discovery_status(app) == "failed")
        assert app.state.media_base_url_effective == ""


def test_a_discovery_message_without_text_names_the_error_type(paths: Paths, made: list[FastAPI]):
    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("", request=request)

    http = httpx.AsyncClient(transport=httpx.MockTransport(slow))
    app = build(made, paths, SupervisorClient("tok", client=http))
    with TestClient(app):
        assert wait_for(lambda: discovery_status(app) == "failed")
        assert "ReadTimeout" in str(app.state.discovery_status["message"])


def test_a_bookkeeping_failure_does_not_fail_discovery(
    paths: Paths, made: list[FastAPI], caplog: pytest.LogCaptureFixture
):
    (paths.data_dir / "discovery_uuid").mkdir()  # cannot be read or written as a file
    app = build(made, paths, FakeSupervisor().client())
    with caplog.at_level(logging.WARNING, logger="sound_effects_studio.lifecycle"), TestClient(app):
        assert wait_for(lambda: discovery_status(app) == "ok")
        assert wait_for(lambda: "Could not record the discovery uuid" in caplog.text)
    assert app.state.discovery_status == {"status": "ok", "message": None}


async def test_publish_discovery_can_be_repeated_after_a_token_rotation(
    paths: Paths, made: list[FastAPI]
):
    fake = FakeSupervisor(routes={("DELETE", "/discovery/uuid-new"): httpx.Response(200, json={})})
    app = build(made, paths, fake.client(), start_background=False)
    await lifecycle.publish_discovery(app)
    app.state.tokens.rotate()
    await lifecycle.publish_discovery(app)
    assert fake.calls().count(("POST", "/discovery")) == 2
    assert ("DELETE", "/discovery/uuid-new") in fake.calls()
    posted = [
        json.loads(r.content)
        for r in fake.requests
        if (r.method, r.url.path) == ("POST", "/discovery")
    ]
    assert posted[1]["config"]["token"] == app.state.tokens.get()
    assert posted[0]["config"]["token"] != posted[1]["config"]["token"]


def test_without_a_supervisor_nothing_is_published(paths: Paths, made: list[FastAPI], probe: Probe):
    app = build(made, paths)
    with TestClient(app):
        time.sleep(0.1)
        assert app.state.discovery_status == {
            "status": "unavailable",
            "message": "The Supervisor API is not available",
        }
        assert app.state.media_base_url_effective == ""
        assert app.state.www_status.served is None
    assert probe.calls == []


# --- startup ordering ----------------------------------------------------------------------


def test_the_supervisor_steps_wait_for_the_server_and_never_block_startup(
    paths: Paths, made: list[FastAPI], monkeypatch: pytest.MonkeyPatch
):
    gate = threading.Event()

    async def listening(*args: object, **kwargs: object) -> bool:
        while not gate.is_set():
            await asyncio.sleep(0.01)
        return True

    monkeypatch.setattr(lifecycle, "wait_for_server", listening)
    fake = FakeSupervisor()
    app = build(made, paths, fake.client())
    with TestClient(app):
        # Startup returned while the server is not accepting connections yet: nothing announced.
        time.sleep(0.15)
        assert fake.requests == []
        assert discovery_status(app) == "unavailable"
        gate.set()
        assert wait_for(lambda: discovery_status(app) == "ok")
    assert ("POST", "/discovery") in fake.calls()


def test_shutdown_cancels_steps_that_are_still_waiting(
    paths: Paths, made: list[FastAPI], monkeypatch: pytest.MonkeyPatch
):
    async def never(*args: object, **kwargs: object) -> bool:
        await asyncio.sleep(3600)
        return True

    monkeypatch.setattr(lifecycle, "wait_for_server", never)
    fake = FakeSupervisor()
    app = build(made, paths, fake.client())
    started = time.monotonic()
    with TestClient(app):
        pass
    assert time.monotonic() - started < 5
    assert fake.requests == []


def test_a_server_that_never_answers_does_not_prevent_discovery(
    paths: Paths, made: list[FastAPI], monkeypatch: pytest.MonkeyPatch
):
    async def timed_out(*args: object, **kwargs: object) -> bool:
        return False

    monkeypatch.setattr(lifecycle, "wait_for_server", timed_out)
    app = build(made, paths, FakeSupervisor().client())
    with TestClient(app):
        assert wait_for(lambda: discovery_status(app) == "ok")


@pytest.mark.usefixtures("socket_enabled")
async def test_wait_for_server_returns_once_something_listens():
    server = await asyncio.start_server(lambda r, w: w.close(), "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        assert await REAL_WAIT_FOR_SERVER("127.0.0.1", port, timeout=2) is True
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.usefixtures("socket_enabled")
async def test_wait_for_server_times_out_when_nothing_listens():
    probe_socket = await asyncio.start_server(lambda r, w: w.close(), "127.0.0.1", 0)
    port = probe_socket.sockets[0].getsockname()[1]
    probe_socket.close()
    await probe_socket.wait_closed()
    started = time.monotonic()
    assert await REAL_WAIT_FOR_SERVER("127.0.0.1", port, timeout=0.4) is False
    assert time.monotonic() - started < 3


async def test_wait_for_server_bounds_a_stalled_connect(monkeypatch: pytest.MonkeyPatch):
    cancelled = asyncio.Event()

    async def stalled(host: str, port: int) -> None:
        try:
            await asyncio.sleep(3600)
        finally:
            cancelled.set()

    monkeypatch.setattr(lifecycle.asyncio, "open_connection", stalled)
    async with asyncio.timeout(1):
        assert await REAL_WAIT_FOR_SERVER(timeout=0.05) is False
    assert cancelled.is_set()


@pytest.mark.usefixtures("socket_enabled")
async def test_wait_for_server_retries_until_the_port_is_bound():
    reserve = await asyncio.start_server(lambda r, w: w.close(), "127.0.0.1", 0)
    port = reserve.sockets[0].getsockname()[1]
    reserve.close()
    await reserve.wait_closed()
    waiting = asyncio.create_task(REAL_WAIT_FOR_SERVER("127.0.0.1", port, timeout=5))
    await asyncio.sleep(0.5)
    assert not waiting.done()
    server = await asyncio.start_server(lambda r, w: w.close(), "127.0.0.1", port)
    try:
        assert await waiting is True
    finally:
        server.close()
        await server.wait_closed()


# --- media base URL ------------------------------------------------------------------------


def network_routes(core_port: object = 8123) -> Routes:
    return {
        ("GET", "/core/api/config"): httpx.Response(200, json={"internal_url": None}),
        ("GET", "/network/info"): httpx.Response(
            200,
            json={
                "data": {
                    "interfaces": [
                        {
                            "interface": "eth0",
                            "primary": False,
                            "ipv4": {"address": ["10.0.0.5/24"]},
                        },
                        {
                            "interface": "wlan0",
                            "primary": True,
                            "ipv4": {"address": ["192.168.1.50/24", "192.168.1.51/24"]},
                        },
                    ]
                }
            },
        ),
        ("GET", "/core/info"): httpx.Response(200, json={"data": {"port": core_port}}),
    }


async def test_configured_media_base_url_wins_without_asking_the_supervisor():
    fake = FakeSupervisor()
    url = await lifecycle.detect_media_base_url(fake.client(), "http://custom.example:8123/")
    assert url == "http://custom.example:8123"
    assert fake.requests == []


async def test_media_base_url_uses_the_internal_url():
    fake = FakeSupervisor()
    assert await lifecycle.detect_media_base_url(fake.client(), "") == "http://ha.local:8123"
    assert fake.calls() == [("GET", "/core/api/config")]


async def test_media_base_url_falls_back_to_the_primary_interface():
    fake = FakeSupervisor(routes=network_routes(8123))
    assert await lifecycle.detect_media_base_url(fake.client(), "") == "http://192.168.1.50:8123"


async def test_media_base_url_falls_back_when_core_config_fails():
    routes = network_routes(8124)
    routes[("GET", "/core/api/config")] = httpx.Response(503, text="starting")
    fake = FakeSupervisor(routes=routes)
    assert await lifecycle.detect_media_base_url(fake.client(), "") == "http://192.168.1.50:8124"


async def test_media_base_url_is_empty_when_nothing_works():
    fake = FakeSupervisor(
        routes={
            ("GET", "/core/api/config"): httpx.Response(200, json={}),
            ("GET", "/network/info"): httpx.Response(500, text="boom"),
        }
    )
    assert await lifecycle.detect_media_base_url(fake.client(), "") == ""
    broken = FakeSupervisor(routes=network_routes(core_port="x"))
    assert await lifecycle.detect_media_base_url(broken.client(), "") == ""
    assert await lifecycle.detect_media_base_url(SupervisorClient(None), "") == ""


def test_lifespan_stores_the_effective_media_base_url(paths: Paths, made: list[FastAPI]):
    app = build(made, paths, FakeSupervisor().client())
    with TestClient(app):
        assert wait_for(lambda: app.state.media_base_url_effective == "http://ha.local:8123")


def test_lifespan_prefers_the_media_base_url_setting(paths: Paths, made: list[FastAPI]):
    app = build(made, paths, FakeSupervisor().client())
    app.state.repo.update_settings(Settings(media_base_url="http://custom:9000"))
    with TestClient(app):
        assert wait_for(lambda: app.state.media_base_url_effective == "http://custom:9000")


# --- /local probe --------------------------------------------------------------------------


def http_client(status: int | Exception, seen: list[httpx.Request]) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if isinstance(status, Exception):
            raise status
        return httpx.Response(status, text="ok")

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_probe_writes_the_file_and_reads_it_back_through_home_assistant(paths: Paths):
    paths.publish_dir.mkdir(parents=True)
    seen: list[httpx.Request] = []
    assert await REAL_CHECK_WWW_SERVED(paths.publish_dir, http_client(200, seen)) is True
    assert (paths.publish_dir / ".probe").is_file()
    assert str(seen[0].url) == "http://homeassistant:8123/local/sound-effects/.probe"


async def test_probe_follows_the_core_port_and_scheme(paths: Paths):
    paths.publish_dir.mkdir(parents=True)
    seen: list[httpx.Request] = []
    served = await REAL_CHECK_WWW_SERVED(
        paths.publish_dir, http_client(200, seen), base_url="https://homeassistant:8443"
    )
    assert served is True
    assert str(seen[0].url) == "https://homeassistant:8443/local/sound-effects/.probe"


@pytest.mark.parametrize(
    "outcome",
    [404, 302, 500, httpx.ConnectError("refused"), httpx.ReadTimeout("slow")],
)
async def test_probe_reports_false_unless_home_assistant_serves_the_file(
    paths: Paths, outcome: int | Exception
):
    paths.publish_dir.mkdir(parents=True)
    assert await REAL_CHECK_WWW_SERVED(paths.publish_dir, http_client(outcome, [])) is False


async def test_probe_is_false_when_the_probe_file_cannot_be_written(paths: Paths):
    seen: list[httpx.Request] = []
    assert await REAL_CHECK_WWW_SERVED(paths.publish_dir, http_client(200, seen)) is False
    assert seen == []


@pytest.mark.parametrize(
    ("core_info", "expected"),
    [
        ({"data": {"port": 8123, "ssl": False}}, "http://homeassistant:8123"),
        ({"data": {"port": 8443, "ssl": True}}, "https://homeassistant:8443"),
        ({"data": {"port": 9000}}, "http://homeassistant:9000"),
        ({"data": {"ssl": True}}, "http://homeassistant:8123"),
        ({"data": {"port": "8123", "ssl": True}}, "http://homeassistant:8123"),
    ],
)
async def test_probe_base_comes_from_core_info(core_info: dict[str, object], expected: str):
    fake = FakeSupervisor(routes={("GET", "/core/info"): httpx.Response(200, json=core_info)})
    assert await lifecycle.core_probe_base(fake.client()) == expected


async def test_probe_base_defaults_when_core_info_fails():
    fake = FakeSupervisor(routes={("GET", "/core/info"): httpx.Response(503, text="starting")})
    assert await lifecycle.core_probe_base(fake.client()) == "http://homeassistant:8123"


def test_lifespan_records_whether_home_assistant_serves_the_files(
    paths: Paths, made: list[FastAPI], probe: Probe
):
    fake = FakeSupervisor(
        routes={
            ("GET", "/core/info"): httpx.Response(200, json={"data": {"port": 8443, "ssl": True}})
        }
    )
    app = build(made, paths, fake.client())
    with TestClient(app):
        assert wait_for(lambda: app.state.www_status.served is True)
    assert probe.calls[0] == (paths.publish_dir, "https://homeassistant:8443")

    probe.served = False
    other = build(made, paths, FakeSupervisor().client())
    with TestClient(other):
        assert wait_for(lambda: other.state.www_status.served is False)
    assert probe.calls[-1] == (paths.publish_dir, "http://homeassistant:8123")


def test_detection_and_probe_errors_leave_the_server_running(
    paths: Paths,
    made: list[FastAPI],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    async def broken_detection(supervisor: SupervisorClient, configured: str) -> str:
        raise RuntimeError("detection failed")

    async def broken_probe(*args: object, **kwargs: object) -> bool:
        raise RuntimeError("probe failed")

    monkeypatch.setattr(lifecycle, "detect_media_base_url", broken_detection)
    monkeypatch.setattr(lifecycle, "check_www_served", broken_probe)
    app = build(made, paths, FakeSupervisor().client())
    with caplog.at_level(logging.ERROR), TestClient(app) as client:
        assert wait_for(lambda: "The /local probe failed" in caplog.text)
        assert "Media base URL detection failed" in caplog.text
        assert app.state.media_base_url_effective == ""
        assert app.state.www_status.served is None
        assert (
            client.get(
                "/api/v1/health", headers={"Authorization": f"Bearer {app.state.tokens.get()}"}
            ).status_code
            == 200
        )
    assert app.state.tokens.get() not in caplog.text
    assert "sup-token" not in caplog.text


# --- catalog change events -----------------------------------------------------------------


@pytest.fixture
def fast_notifier(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lifecycle, "CATALOG_NOTIFY_DELAY", 0.05)


def test_catalog_changes_fire_a_debounced_home_assistant_event(
    paths: Paths, made: list[FastAPI], fast_notifier: None
):
    fake = FakeSupervisor()
    app = build(made, paths, fake.client())
    event = ("POST", "/core/api/events/sound_effects_catalog_changed")
    with TestClient(app):
        assert app.state.notifier is not None
        app.state.repo.create_category(CategoryCreate(name="Doors"))
        revision = app.state.repo.catalog_revision()
        assert wait_for(lambda: event in fake.calls())
        assert fake.body(*event) == {"revision": revision}
    assert app.state.notifier is None


def test_event_failures_are_swallowed(paths: Paths, made: list[FastAPI], fast_notifier: None):
    event = ("POST", "/core/api/events/sound_effects_catalog_changed")
    fake = FakeSupervisor(routes={event: httpx.Response(500, json={"message": "core is down"})})
    app = build(made, paths, fake.client())
    with TestClient(app) as client:
        app.state.repo.create_category(CategoryCreate(name="Doors"))
        assert wait_for(lambda: event in fake.calls())
        app.state.repo.create_category(CategoryCreate(name="Windows"))
        assert wait_for(lambda: fake.calls().count(event) == 2)
        token = app.state.tokens.get()
        assert client.get("/api/v1/health", headers={"Authorization": f"Bearer {token}"}).is_success


def test_changes_without_a_supervisor_are_announced_to_nobody(
    paths: Paths,
    made: list[FastAPI],
    fast_notifier: None,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    sent: list[int] = []
    real_sender = lifecycle.catalog_sender

    def spying_sender(supervisor: SupervisorClient):
        send = real_sender(supervisor)

        async def spy(revision: int) -> None:
            sent.append(revision)
            await send(revision)

        return spy

    monkeypatch.setattr(lifecycle, "catalog_sender", spying_sender)
    app = build(made, paths)
    fired: list[str] = []

    async def fire_event(event_type: str, data: dict[str, object]) -> None:
        fired.append(event_type)

    monkeypatch.setattr(app.state.supervisor, "fire_event", fire_event)
    with caplog.at_level(logging.DEBUG), TestClient(app):
        app.state.repo.create_category(CategoryCreate(name="Doors"))
        revision = app.state.repo.catalog_revision()
        # The notifier did run the sender for this revision, and the sender did nothing.
        assert wait_for(lambda: sent == [revision])
        time.sleep(0.1)
    assert fired == []
    problems = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert problems == []


async def test_the_catalog_sender_is_a_no_op_for_an_unavailable_supervisor():
    fake = FakeSupervisor()
    http = httpx.AsyncClient(transport=httpx.MockTransport(fake.handle))
    await lifecycle.catalog_sender(SupervisorClient(None, client=http))(5)
    assert fake.requests == []


# --- lifecycle -----------------------------------------------------------------------------


def test_lifespan_starts_and_stops_the_job_queue(
    paths: Paths, made: list[FastAPI], monkeypatch: pytest.MonkeyPatch
):
    app = build(made, paths)
    events: list[str] = []

    async def start() -> None:
        events.append("start")

    async def stop() -> None:
        events.append("stop")

    monkeypatch.setattr(app.state.jobs, "start", start)
    monkeypatch.setattr(app.state.jobs, "stop", stop)
    with TestClient(app):
        assert events == ["start"]
    assert events == ["start", "stop"]


def test_shutdown_closes_the_supervisor_notifier_and_database(paths: Paths, made: list[FastAPI]):
    http = httpx.AsyncClient(transport=httpx.MockTransport(FakeSupervisor().handle))
    app = build(made, paths, SupervisorClient("tok", client=http))
    with TestClient(app):
        assert not http.is_closed
    assert http.is_closed
    assert app.state.notifier is None
    with pytest.raises(Exception, match="closed"):
        app.state.db.connection.execute("SELECT 1")


def test_a_failing_shutdown_step_does_not_skip_the_others(
    paths: Paths,
    made: list[FastAPI],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    http = httpx.AsyncClient(transport=httpx.MockTransport(FakeSupervisor().handle))
    app = build(made, paths, SupervisorClient("tok", client=http))

    async def broken_stop() -> None:
        raise RuntimeError("worker is stuck")

    monkeypatch.setattr(app.state.jobs, "stop", broken_stop)
    with caplog.at_level(logging.ERROR, logger="sound_effects_studio.app"), TestClient(app):
        pass
    assert "Could not stop the render worker" in caplog.text
    assert http.is_closed
    assert app.state.notifier is None
    with pytest.raises(Exception, match="closed"):
        app.state.db.connection.execute("SELECT 1")


def test_a_failed_startup_still_releases_everything(
    paths: Paths, made: list[FastAPI], monkeypatch: pytest.MonkeyPatch
):
    http = httpx.AsyncClient(transport=httpx.MockTransport(FakeSupervisor().handle))
    app = build(made, paths, SupervisorClient("tok", client=http))
    started_worker: list[asyncio.Task[None]] = []
    start = app.state.jobs.start

    async def broken_start() -> None:
        await start()
        started_worker.append(app.state.jobs._worker)
        raise RuntimeError("cannot start the worker")

    monkeypatch.setattr(app.state.jobs, "start", broken_start)
    with pytest.raises(RuntimeError, match="cannot start the worker"), TestClient(app):
        pass
    assert http.is_closed
    assert app.state.notifier is None
    assert len(started_worker) == 1
    assert started_worker[0].done()
    with pytest.raises(Exception, match="closed"):
        app.state.db.connection.execute("SELECT 1")


def test_without_background_work_the_lifespan_starts_nothing(
    paths: Paths, made: list[FastAPI], monkeypatch: pytest.MonkeyPatch
):
    fake = FakeSupervisor()
    app = build(made, paths, fake.client(), start_background=False)
    started: list[str] = []

    async def start() -> None:
        started.append("start")

    monkeypatch.setattr(app.state.jobs, "start", start)
    with TestClient(app):
        time.sleep(0.1)
        assert app.state.notifier is None
        assert app.state.discovery_status["status"] == "unavailable"
    assert started == []
    assert fake.requests == []
    assert app.state.www_status.exists


@pytest.mark.parametrize("discovery_fails", [False, True])
def test_secrets_never_reach_the_logs(
    paths: Paths,
    made: list[FastAPI],
    caplog: pytest.LogCaptureFixture,
    fast_notifier: None,
    discovery_fails: bool,
):
    event = ("POST", "/core/api/events/sound_effects_catalog_changed")
    discovery = (
        httpx.Response(400, json={"message": "refused"})
        if discovery_fails
        else httpx.Response(200, json={"data": {"uuid": "uuid-new"}})
    )
    fake = FakeSupervisor(
        routes={
            ("POST", "/discovery"): discovery,
            event: httpx.Response(500, json={"message": "core is down"}),
        }
    )
    app = build(made, paths, fake.client())
    caplog.set_level(logging.DEBUG)
    with TestClient(app):
        expected = "failed" if discovery_fails else "ok"
        assert wait_for(lambda: discovery_status(app) == expected)
        app.state.repo.create_category(CategoryCreate(name="Doors"))
        assert wait_for(lambda: event in fake.calls())
    assert "core is down" in caplog.text
    if discovery_fails:
        assert "refused" in caplog.text
    assert app.state.tokens.get() not in caplog.text
    assert "sup-token" not in caplog.text


# --- periodic work -------------------------------------------------------------------------


def test_stale_auditions_are_cleaned_periodically(
    paths: Paths, made: list[FastAPI], monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(lifecycle, "HOUSEKEEPING_INTERVAL", 0.05)
    app = build(made, paths)
    stale = paths.publish_dir / "_audition" / "old-12345678.mp3"
    fresh = paths.publish_dir / "_audition" / "new-12345678.mp3"
    with TestClient(app):
        for path in (stale, fresh):
            path.write_bytes(b"x")
        old = time.time() - 3600
        os.utime(stale, (old, old))
        assert wait_for(lambda: not stale.exists())
        assert fresh.exists()


def test_housekeeping_also_purges_stale_uploads_and_survives_errors(
    paths: Paths, made: list[FastAPI], monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(lifecycle, "HOUSEKEEPING_INTERVAL", 0.02)
    app = build(made, paths)
    calls: list[int] = []

    class Uploads:
        def purge_stale(self) -> None:
            calls.append(len(calls))
            if len(calls) == 1:
                raise RuntimeError("disk hiccup")

    app.state.uploads = Uploads()
    with TestClient(app):
        assert wait_for(lambda: len(calls) >= 3)


def test_housekeeping_awaits_an_asynchronous_purge(
    paths: Paths, made: list[FastAPI], monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(lifecycle, "HOUSEKEEPING_INTERVAL", 0.02)
    app = build(made, paths)
    finished: list[int] = []

    class Uploads:
        async def purge_stale(self) -> None:
            await asyncio.sleep(0)
            finished.append(len(finished))

    app.state.uploads = Uploads()
    with TestClient(app):
        assert wait_for(lambda: len(finished) >= 2)


def test_a_slow_core_boot_is_corrected_by_the_periodic_refresh(
    paths: Paths, made: list[FastAPI], monkeypatch: pytest.MonkeyPatch, probe: Probe
):
    monkeypatch.setattr(lifecycle, "HOUSEKEEPING_INTERVAL", 0.05)
    probe.served = False
    fake = FakeSupervisor(
        routes={
            ("GET", "/core/api/config"): httpx.Response(503, text="core is starting"),
            ("GET", "/network/info"): httpx.Response(503, text="core is starting"),
        }
    )
    app = build(made, paths, fake.client())
    with TestClient(app):
        assert wait_for(lambda: discovery_status(app) == "ok")
        assert wait_for(lambda: len(probe.calls) >= 1)
        assert app.state.media_base_url_effective == ""
        assert app.state.www_status.served is False
        # Core finishes booting.
        fake.routes[("GET", "/core/api/config")] = httpx.Response(
            200, json={"internal_url": "http://ha.local:8123"}
        )
        probe.served = True
        assert wait_for(lambda: app.state.media_base_url_effective == "http://ha.local:8123")
        assert wait_for(lambda: app.state.www_status.served is True)


def test_a_failed_discovery_is_retried_by_the_periodic_refresh(
    paths: Paths, made: list[FastAPI], monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(lifecycle, "HOUSEKEEPING_INTERVAL", 0.05)
    fake = FakeSupervisor(
        routes={("POST", "/discovery"): httpx.Response(503, json={"message": "starting"})}
    )
    app = build(made, paths, fake.client())
    with TestClient(app):
        assert wait_for(lambda: discovery_status(app) == "failed")
        fake.routes[("POST", "/discovery")] = httpx.Response(200, json={"data": {"uuid": "late"}})
        assert wait_for(lambda: discovery_status(app) == "ok")
    assert remembered_uuids(paths) == ["late"]


def test_a_healthy_discovery_is_not_republished_by_the_refresh(
    paths: Paths, made: list[FastAPI], monkeypatch: pytest.MonkeyPatch, probe: Probe
):
    monkeypatch.setattr(lifecycle, "HOUSEKEEPING_INTERVAL", 0.05)
    fake = FakeSupervisor()
    app = build(made, paths, fake.client())
    with TestClient(app):
        assert wait_for(lambda: discovery_status(app) == "ok")
        assert wait_for(lambda: len(probe.calls) >= 3)
    assert fake.calls().count(("POST", "/discovery")) == 1


async def test_housekeeping_loop_stops_when_cancelled(paths: Paths, made: list[FastAPI]):
    app = build(made, paths, start_background=False)
    task = asyncio.create_task(lifecycle.housekeeping(app, 0.01))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def test_upload_purge_runs_in_a_worker_thread(paths: Paths, made: list[FastAPI]):
    app = build(made, paths)
    completed: list[bool] = []

    class Uploads:
        def purge_stale(self) -> None:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                completed.append(True)
            else:
                completed.append(False)

    app.state.uploads = Uploads()
    with TestClient(app):
        assert wait_for(lambda: bool(completed))
    assert completed[0]
