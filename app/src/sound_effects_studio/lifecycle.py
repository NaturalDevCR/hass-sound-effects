"""Background work behind the app lifespan: discovery, media URL, /local probe, cleanup.

Everything here that the lifespan starts as a task never raises: failures are logged and
reflected in ``app.state`` so a slow or absent Supervisor can neither block nor abort startup.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from pathlib import Path
from typing import cast

import httpx
from fastapi import FastAPI

from .supervisor import SupervisorClient, SupervisorError, describe_error

_LOGGER = logging.getLogger(__name__)

APP_PORT = 8099
CATALOG_EVENT = "sound_effects_catalog_changed"
CATALOG_NOTIFY_DELAY = 1.0
HOUSEKEEPING_INTERVAL = 600.0
SERVER_WAIT_TIMEOUT = 10.0
DEFAULT_CORE_URL = "http://homeassistant:8123"
PROBE_PATH = "/local/sound-effects/.probe"
SERVED_PROBE_TIMEOUT = 3.0


# --- startup ordering ----------------------------------------------------------------------


async def wait_for_server(
    host: str = "127.0.0.1", port: int = APP_PORT, timeout: float | None = None
) -> bool:
    """Wait until something accepts TCP connections on ``host:port``; False on timeout.

    Uvicorn runs the lifespan startup before it binds its socket, so announcing the App to Home
    Assistant from the lifespan itself would point it at a port nobody listens on yet.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + (SERVER_WAIT_TIMEOUT if timeout is None else timeout)
    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            return False
        try:
            _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), remaining)
        except (OSError, TimeoutError):
            if loop.time() >= deadline:
                return False
            await asyncio.sleep(min(0.2, deadline - loop.time()))
        else:
            writer.close()
            with suppress(OSError, TimeoutError):
                await asyncio.wait_for(writer.wait_closed(), 0.2)
            return True


async def supervisor_startup(app: FastAPI) -> None:
    """Announce the App and detect the Home Assistant side once the server accepts connections."""
    if not app.state.supervisor.available:
        return
    try:
        if not await wait_for_server():
            _LOGGER.warning("The HTTP server did not accept connections in time; continuing")
        await publish_discovery(app)
        await refresh_runtime_state(app)
    except Exception:
        _LOGGER.exception("Supervisor startup steps failed")


async def housekeeping(app: FastAPI, interval: float) -> None:
    """Clean up stale files now, then every ``interval``; also re-check Home Assistant then."""
    while True:
        await _clean_up(app)
        await asyncio.sleep(interval)
        await _resync(app)


async def _clean_up(app: FastAPI) -> None:
    """Remove stale audition copies and abandoned uploads."""
    try:
        await asyncio.to_thread(app.state.publisher.cleanup_auditions)
    except Exception:
        _LOGGER.exception("Audition cleanup failed")
    uploads = getattr(app.state, "uploads", None)
    if uploads is None:
        return
    try:
        result = uploads.purge_stale()
        if inspect.isawaitable(result):
            await result
    except Exception:
        _LOGGER.exception("Upload cleanup failed")


async def _resync(app: FastAPI) -> None:
    """Correct what a slow Core or Supervisor boot got wrong at startup."""
    if not app.state.supervisor.available:
        return
    try:
        if app.state.discovery_status["status"] == "failed":
            await publish_discovery(app)
        await refresh_runtime_state(app)
    except Exception:
        _LOGGER.exception("Supervisor refresh failed")


async def refresh_runtime_state(app: FastAPI) -> None:
    """Re-detect the effective media base URL and whether Home Assistant serves ``/local``."""
    state = app.state
    supervisor: SupervisorClient = state.supervisor
    if not supervisor.available:
        return
    try:
        configured = state.repo.get_settings().media_base_url
        state.media_base_url_effective = await detect_media_base_url(supervisor, configured)
    except Exception:
        _LOGGER.exception("Media base URL detection failed")
    try:
        base_url = await core_probe_base(supervisor)
        state.www_status.served = await check_www_served(state.paths.publish_dir, base_url=base_url)
    except Exception:
        _LOGGER.exception("The /local probe failed")


# --- discovery -----------------------------------------------------------------------------


async def publish_discovery(app: FastAPI) -> None:
    """Announce the App and its token to Home Assistant, replacing the previous announcement.

    The outcome lands in ``app.state.discovery_status``; this never raises.
    """
    state = app.state
    async with state.discovery_lock:
        supervisor: SupervisorClient = state.supervisor
        uuid_file: Path = state.paths.data_dir / "discovery_uuid"
        try:
            hostname = (await supervisor.self_info()).get("hostname")
            if not isinstance(hostname, str) or not hostname:
                raise SupervisorError("The Supervisor did not report the App hostname")
            stale = await _delete_previous_discoveries(supervisor, uuid_file)
            uuid = await supervisor.publish_discovery(
                {
                    "host": hostname,
                    "port": APP_PORT,
                    "token": state.tokens.get(),
                    "instance_id": state.instance_id,
                }
            )
        except Exception as exc:
            message = describe_error(exc)
            _LOGGER.warning("Could not publish discovery: %s", message)
            state.discovery_status = {"status": "failed", "message": message}
            return
        state.discovery_status = {"status": "ok", "message": None}
        _remember_discoveries(uuid_file, [*stale, uuid])


async def _delete_previous_discoveries(supervisor: SupervisorClient, uuid_file: Path) -> list[str]:
    """Delete the remembered discoveries; returns the ones that could not be deleted."""
    stale: list[str] = []
    for uuid in _read_discoveries(uuid_file):
        try:
            await supervisor.delete_discovery(uuid)
        except SupervisorError as exc:
            if exc.status == 404:
                continue
            _LOGGER.debug("Previous discovery %s was not removed: %s", uuid, exc)
            stale.append(uuid)
    _remember_discoveries(uuid_file, stale)
    return stale


def _read_discoveries(uuid_file: Path) -> list[str]:
    try:
        saved = uuid_file.read_text(encoding="utf-8")
    except OSError:
        return []
    try:
        uuids: object = json.loads(saved)
    except json.JSONDecodeError:
        # Upgrade the original single-uuid file (and interim newline records) on the next write.
        return [line.strip() for line in saved.splitlines() if line.strip()]
    if not isinstance(uuids, list):
        return []
    return [uuid for uuid in cast("list[object]", uuids) if isinstance(uuid, str) and uuid]


def _remember_discoveries(uuid_file: Path, uuids: list[str]) -> None:
    """Persist the discovery uuids to delete next time; bookkeeping errors only warn."""
    try:
        if uuids:
            uuid_file.write_text(json.dumps(list(dict.fromkeys(uuids))) + "\n", encoding="utf-8")
        else:
            uuid_file.unlink(missing_ok=True)
    except OSError as exc:
        _LOGGER.warning("Could not record the discovery uuid: %s", describe_error(exc))


# --- Home Assistant detection --------------------------------------------------------------


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


async def core_probe_base(supervisor: SupervisorClient) -> str:
    """Where to reach Core from inside the App network: its port and ``ssl`` flag when known."""
    try:
        info = await supervisor.core_info()
    except SupervisorError as exc:
        _LOGGER.debug("Core info unavailable for the /local probe: %s", exc)
        return DEFAULT_CORE_URL
    port = info.get("port")
    if not isinstance(port, int) or isinstance(port, bool):
        return DEFAULT_CORE_URL
    scheme = "https" if info.get("ssl") is True else "http"
    return f"{scheme}://homeassistant:{port}"


async def check_www_served(
    publish_dir: Path,
    client: httpx.AsyncClient | None = None,
    *,
    base_url: str = DEFAULT_CORE_URL,
) -> bool:
    """Whether Home Assistant serves the publish directory under ``/local/sound-effects/``.

    Writes a probe file and requests it back; anything but a plain ``200`` counts as not served.
    The probe carries no credentials, so TLS verification is off: Core's certificate is issued
    for its public name, not for ``homeassistant``.
    """
    try:
        (publish_dir / ".probe").write_text("sound-effects", encoding="utf-8")
    except OSError as exc:
        _LOGGER.warning("Could not write the www probe file: %s", describe_error(exc))
        return False
    http = client if client is not None else httpx.AsyncClient(verify=False)
    try:
        response = await http.get(f"{base_url}{PROBE_PATH}", timeout=SERVED_PROBE_TIMEOUT)
    except httpx.HTTPError as exc:
        _LOGGER.info("Home Assistant did not answer the www probe: %s", describe_error(exc))
        return False
    finally:
        if client is None:
            await http.aclose()
    return response.status_code == 200


# --- catalog events ------------------------------------------------------------------------


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
