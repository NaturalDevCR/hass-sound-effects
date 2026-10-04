"""Background work behind the app lifespan: discovery, media URL, /local probe, cleanup."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import cast

import httpx
from fastapi import FastAPI

from .supervisor import SupervisorClient, SupervisorError

_LOGGER = logging.getLogger(__name__)

APP_PORT = 8099
CATALOG_EVENT = "sound_effects_catalog_changed"
CATALOG_NOTIFY_DELAY = 1.0
HOUSEKEEPING_INTERVAL = 600.0
SERVED_PROBE_URL = "http://homeassistant:8123/local/sound-effects/.probe"
SERVED_PROBE_TIMEOUT = 3.0


async def publish_discovery(app: FastAPI) -> None:
    """Announce the App and its token to Home Assistant, replacing the previous announcement.

    The outcome lands in ``app.state.discovery_status``; this never raises.
    """
    state = app.state
    supervisor: SupervisorClient = state.supervisor
    uuid_file: Path = state.paths.data_dir / "discovery_uuid"
    try:
        hostname = (await supervisor.self_info()).get("hostname")
        if not isinstance(hostname, str) or not hostname:
            raise SupervisorError("The Supervisor did not report the App hostname")
        await _delete_previous_discovery(supervisor, uuid_file)
        uuid = await supervisor.publish_discovery(
            {
                "host": hostname,
                "port": APP_PORT,
                "token": state.tokens.get(),
                "instance_id": state.instance_id,
            }
        )
        uuid_file.write_text(uuid, encoding="utf-8")
    except Exception as exc:
        _LOGGER.warning("Could not publish discovery: %s", exc)
        state.discovery_status = {"status": "failed", "message": str(exc)}
    else:
        state.discovery_status = {"status": "ok", "message": None}


async def _delete_previous_discovery(supervisor: SupervisorClient, uuid_file: Path) -> None:
    try:
        previous = uuid_file.read_text(encoding="utf-8").strip()
    except OSError:
        return
    if not previous:
        return
    try:
        await supervisor.delete_discovery(previous)
    except SupervisorError as exc:
        _LOGGER.debug("Previous discovery %s was not removed: %s", previous, exc)
        return
    uuid_file.unlink(missing_ok=True)


async def detect_media_base_url(supervisor: SupervisorClient, configured: str) -> str:
    """The Home Assistant base URL for audio links; ``""`` when it cannot be determined.

    Order: the ``media_base_url`` setting, Core's ``internal_url``, then the primary network
    interface's IPv4 address with Core's port.
    """
    if configured.strip():
        return configured.strip().rstrip("/")
    if not supervisor.available:
        return ""
    try:
        internal = (await supervisor.core_config()).get("internal_url")
        if isinstance(internal, str) and internal.strip():
            return internal.strip().rstrip("/")
    except SupervisorError as exc:
        _LOGGER.debug("Core internal_url unavailable: %s", exc)
    try:
        address = _primary_ipv4(await supervisor.network_info())
        port = (await supervisor.core_info()).get("port")
    except SupervisorError as exc:
        _LOGGER.debug("Network detection failed: %s", exc)
        return ""
    if address is None or not isinstance(port, int) or isinstance(port, bool):
        return ""
    return f"http://{address}:{port}"


def _primary_ipv4(network_info: dict[str, object]) -> str | None:
    interfaces = network_info.get("interfaces")
    if not isinstance(interfaces, list):
        return None
    for item in cast("list[object]", interfaces):
        if not isinstance(item, dict):
            continue
        interface = cast("dict[str, object]", item)
        ipv4 = interface.get("ipv4")
        if not interface.get("primary") or not isinstance(ipv4, dict):
            continue
        addresses = cast("dict[str, object]", ipv4).get("address")
        if isinstance(addresses, list):
            for address in cast("list[object]", addresses):
                if isinstance(address, str) and address:
                    return address.partition("/")[0]
    return None


async def check_www_served(publish_dir: Path, client: httpx.AsyncClient | None = None) -> bool:
    """Whether Home Assistant serves the publish directory under ``/local/sound-effects/``.

    Writes a probe file and requests it back; anything but a plain ``200`` counts as not served.
    """
    try:
        (publish_dir / ".probe").write_text("sound-effects", encoding="utf-8")
    except OSError as exc:
        _LOGGER.warning("Could not write the www probe file: %s", exc)
        return False
    http = client if client is not None else httpx.AsyncClient()
    try:
        response = await http.get(SERVED_PROBE_URL, timeout=SERVED_PROBE_TIMEOUT)
    except httpx.HTTPError as exc:
        _LOGGER.info("Home Assistant did not answer the www probe: %s", exc)
        return False
    finally:
        if client is None:
            await http.aclose()
    return response.status_code == 200


def catalog_sender(supervisor: SupervisorClient) -> Callable[[int], Awaitable[None]]:
    """The notifier callback that tells Home Assistant the catalog moved to a new revision."""

    async def send(revision: int) -> None:
        if not supervisor.available:
            return
        try:
            await supervisor.fire_event(CATALOG_EVENT, {"revision": revision})
        except SupervisorError as exc:
            _LOGGER.warning("Could not announce catalog revision %s: %s", revision, exc)

    return send


async def housekeeping(app: FastAPI, interval: float) -> None:
    """Remove stale audition copies and abandoned uploads, then repeat every ``interval``."""
    while True:
        try:
            await asyncio.to_thread(app.state.publisher.cleanup_auditions)
        except Exception:
            _LOGGER.exception("Audition cleanup failed")
        uploads = getattr(app.state, "uploads", None)
        if uploads is not None:
            try:
                result = uploads.purge_stale()
                if inspect.isawaitable(result):
                    await result
            except Exception:
                _LOGGER.exception("Upload cleanup failed")
        await asyncio.sleep(interval)
