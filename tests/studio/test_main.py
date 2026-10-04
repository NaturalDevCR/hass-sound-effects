"""Container entry point."""

import asyncio
import logging
from pathlib import Path
from typing import Any

import httpx
import pytest
import sound_effects_studio.main as entry
import uvicorn
from fastapi import FastAPI
from sound_effects_studio.app import create_app
from sound_effects_studio.auth import INGRESS_PEER
from sound_effects_studio.config import Paths
from sound_effects_studio.supervisor import SupervisorClient

pytestmark = pytest.mark.studio


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        ({}, "info"),
        ({"log_level": "debug"}, "debug"),
        ({"log_level": "DEBUG"}, "debug"),
        ({"log_level": "trace"}, "debug"),
        ({"log_level": "notice"}, "info"),
        ({"log_level": "warning"}, "warning"),
        ({"log_level": "fatal"}, "critical"),
        ({"log_level": "loud"}, "info"),
        ({"log_level": 7}, "info"),
    ],
)
def test_log_level_follows_the_addon_option(options: dict[str, object], expected: str):
    assert entry.resolve_log_level(options) == expected


def test_main_serves_the_app_on_the_ingress_port(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "root"
    options = tmp_path / "options.json"
    options.write_text('{"log_level": "warning"}', encoding="utf-8")
    monkeypatch.setattr(entry, "OPTIONS_PATH", options)
    monkeypatch.setenv("SOUND_EFFECTS_DATA", str(root / "data"))
    monkeypatch.setenv("SOUND_EFFECTS_WWW", str(root / "www"))
    monkeypatch.setenv("SUPERVISOR_TOKEN", "sup-token")
    monkeypatch.setattr(logging, "basicConfig", lambda **_: None)
    served: dict[str, Any] = {}
    monkeypatch.setattr(
        entry.uvicorn, "run", lambda app, **kwargs: served.update(app=app, **kwargs)
    )

    entry.main()

    app = served["app"]
    try:
        assert isinstance(app, FastAPI)
        assert (served["host"], served["port"], served["log_level"]) == ("0.0.0.0", 8099, "warning")
        assert served["proxy_headers"] is False
        assert served["forwarded_allow_ips"] == ""
        supervisor: SupervisorClient = app.state.supervisor
        assert supervisor.available
    finally:
        app.state.db.close()


@pytest.mark.usefixtures("socket_enabled")
@pytest.mark.parametrize(("trust_proxy", "expected"), [(False, 403), (True, 503)])
async def test_the_server_ignores_forwarded_headers(paths: Paths, trust_proxy: bool, expected: int):
    """A spoofed X-Forwarded-For must not turn a LAN client into the Ingress peer."""
    app = create_app(paths, start_background=False)
    options = {**entry.uvicorn_options("warning"), "host": "127.0.0.1", "port": 0}
    if trust_proxy:
        # Control case: uvicorn's defaults trust loopback proxies, so the spoof would succeed.
        options.update(proxy_headers=True, forwarded_allow_ips="127.0.0.1")
    server = uvicorn.Server(uvicorn.Config(app, **options))
    serving = asyncio.create_task(server.serve())
    try:
        async with asyncio.timeout(10):
            while not server.started:
                await asyncio.sleep(0.01)
        port = server.servers[0].sockets[0].getsockname()[1]
        async with httpx.AsyncClient() as http:
            response = await http.get(
                f"http://127.0.0.1:{port}/", headers={"X-Forwarded-For": INGRESS_PEER}
            )
    finally:
        server.should_exit = True
        await serving
    assert response.status_code == expected
