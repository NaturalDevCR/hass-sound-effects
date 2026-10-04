"""Container entry point."""

import logging
from pathlib import Path
from typing import Any

import pytest
import sound_effects_studio.main as entry
from fastapi import FastAPI
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
        supervisor: SupervisorClient = app.state.supervisor
        assert supervisor.available
    finally:
        app.state.db.close()
