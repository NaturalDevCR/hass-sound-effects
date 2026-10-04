"""Background services started by the app lifespan: discovery, media URL, events, cleanup."""

import asyncio
import json
import os
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import pytest
import sound_effects_studio.lifecycle as lifecycle
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sound_effects_studio.app import create_app
from sound_effects_studio.config import Paths
from sound_effects_studio.models import CategoryCreate, Settings
from sound_effects_studio.supervisor import SupervisorClient

pytestmark = pytest.mark.studio

HOSTNAME = "local-sound-effects-studio"
REAL_CHECK_WWW_SERVED = lifecycle.check_www_served


@dataclass
class FakeSupervisor:
    """A Supervisor stand-in that records requests and answers from a route table."""

    routes: dict[tuple[str, str], httpx.Response | Exception] = field(default_factory=dict)
    requests: list[httpx.Request] = field(default_factory=list)

    def __post_init__(self) -> None:
        defaults: dict[tuple[str, str], httpx.Response | Exception] = {
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


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Replace the Home Assistant /local probe; records the directories it was asked to check."""
    probed: list[Path] = []

    async def served(publish_dir: Path, client: httpx.AsyncClient | None = None) -> bool:
        probed.append(publish_dir)
        return True

    monkeypatch.setattr(lifecycle, "check_www_served", served)
    return probed


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


# --- discovery -----------------------------------------------------------------------------


def test_lifespan_publishes_discovery_and_replaces_the_previous_one(
    paths: Paths, made: list[FastAPI]
):
    (paths.data_dir / "discovery_uuid").write_text("uuid-old", encoding="utf-8")
    fake = FakeSupervisor(routes={("DELETE", "/discovery/uuid-old"): httpx.Response(200, json={})})
    app = build(made, paths, fake.client())
    with TestClient(app):
        assert app.state.discovery_status == {"status": "ok", "message": None}
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
    assert (paths.data_dir / "discovery_uuid").read_text(encoding="utf-8").strip() == "uuid-new"


def test_first_start_publishes_without_deleting(paths: Paths, made: list[FastAPI]):
    fake = FakeSupervisor()
    with TestClient(build(made, paths, fake.client())):
        pass
    assert all(method != "DELETE" for method, _ in fake.calls())
    assert (paths.data_dir / "discovery_uuid").read_text(encoding="utf-8").strip() == "uuid-new"


def test_a_failed_delete_of_the_previous_discovery_is_ignored(paths: Paths, made: list[FastAPI]):
    (paths.data_dir / "discovery_uuid").write_text("uuid-old", encoding="utf-8")
    fake = FakeSupervisor(
        routes={("DELETE", "/discovery/uuid-old"): httpx.Response(404, json={"message": "gone"})}
    )
    app = build(made, paths, fake.client())
    with TestClient(app):
        assert app.state.discovery_status["status"] == "ok"
    assert (paths.data_dir / "discovery_uuid").read_text(encoding="utf-8").strip() == "uuid-new"


def test_discovery_failure_is_reported_and_the_app_keeps_running(paths: Paths, made: list[FastAPI]):
    fake = FakeSupervisor(
        routes={("POST", "/discovery"): httpx.Response(400, json={"message": "service refused"})}
    )
    app = build(made, paths, fake.client())
    with TestClient(app) as client:
        assert app.state.discovery_status["status"] == "failed"
        assert "service refused" in str(app.state.discovery_status["message"])
        health = client.get(
            "/api/v1/health", headers={"Authorization": f"Bearer {app.state.tokens.get()}"}
        )
        assert health.status_code == 200
    assert not (paths.data_dir / "discovery_uuid").exists()


def test_unreachable_supervisor_does_not_stop_startup(paths: Paths, made: list[FastAPI]):
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    http = httpx.AsyncClient(transport=httpx.MockTransport(refuse))
    app = build(made, paths, SupervisorClient("tok", client=http))
    with TestClient(app):
        assert app.state.discovery_status["status"] == "failed"
        assert app.state.media_base_url_effective == ""


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
        if r.url.path == "/discovery" and r.method == "POST"
    ]
    assert posted[1]["config"]["token"] == app.state.tokens.get()
    assert posted[0]["config"]["token"] != posted[1]["config"]["token"]


def test_without_a_supervisor_nothing_is_published(
    paths: Paths, made: list[FastAPI], no_real_network: list[Path]
):
    app = build(made, paths)
    with TestClient(app):
        assert app.state.discovery_status["status"] == "unavailable"
        assert app.state.media_base_url_effective == ""
        assert app.state.www_status.served is None
    assert no_real_network == []


# --- media base URL ------------------------------------------------------------------------


def network_routes(core_port: object = 8123) -> dict[tuple[str, str], httpx.Response]:
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
    fake = FakeSupervisor(routes=dict(network_routes(8123)))
    assert await lifecycle.detect_media_base_url(fake.client(), "") == "http://192.168.1.50:8123"


async def test_media_base_url_falls_back_when_core_config_fails():
    routes: dict[tuple[str, str], httpx.Response | Exception] = dict(network_routes(8124))
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
    broken = FakeSupervisor(routes=dict(network_routes(core_port="x")))
    assert await lifecycle.detect_media_base_url(broken.client(), "") == ""
    assert await lifecycle.detect_media_base_url(SupervisorClient(None), "") == ""


def test_lifespan_stores_the_effective_media_base_url(paths: Paths, made: list[FastAPI]):
    app = build(made, paths, FakeSupervisor().client())
    with TestClient(app):
        assert app.state.media_base_url_effective == "http://ha.local:8123"


def test_lifespan_prefers_the_media_base_url_setting(paths: Paths, made: list[FastAPI]):
    app = build(made, paths, FakeSupervisor().client())
    app.state.repo.update_settings(Settings(media_base_url="http://custom:9000"))
    with TestClient(app):
        assert app.state.media_base_url_effective == "http://custom:9000"


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


def test_lifespan_records_whether_home_assistant_serves_the_files(
    paths: Paths,
    made: list[FastAPI],
    monkeypatch: pytest.MonkeyPatch,
    no_real_network: list[Path],
):
    app = build(made, paths, FakeSupervisor().client())
    with TestClient(app):
        assert app.state.www_status.served is True
    assert no_real_network == [paths.publish_dir]

    async def unserved(publish_dir: Path, client: httpx.AsyncClient | None = None) -> bool:
        return False

    monkeypatch.setattr(lifecycle, "check_www_served", unserved)
    other = build(made, paths, FakeSupervisor().client())
    with TestClient(other):
        assert other.state.www_status.served is False


# --- catalog change events -----------------------------------------------------------------


def wait_for(condition, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


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


def test_changes_without_a_supervisor_are_harmless(
    paths: Paths, made: list[FastAPI], fast_notifier: None
):
    app = build(made, paths)
    with TestClient(app):
        app.state.repo.create_category(CategoryCreate(name="Doors"))
        time.sleep(0.2)
        assert app.state.notifier is not None


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
        assert app.state.notifier is None
        assert app.state.discovery_status["status"] == "unavailable"
    assert started == []
    assert fake.requests == []
    assert app.state.www_status.exists


# --- periodic cleanup ----------------------------------------------------------------------


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


async def test_housekeeping_loop_stops_when_cancelled(paths: Paths, made: list[FastAPI]):
    app = build(made, paths, start_background=False)
    task = asyncio.create_task(lifecycle.housekeeping(app, 0.01))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
