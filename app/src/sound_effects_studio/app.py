"""FastAPI application factory and lifespan."""

from __future__ import annotations

import asyncio
import importlib
import logging
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable, Coroutine, Sequence
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager, suppress
from functools import partial
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response

from . import __version__, api_v1, lifecycle
from .auth import TokenStore, require_ingress
from .config import Paths
from .db import Database
from .errors import ConflictError, InvalidError, NotFoundError
from .jobs import JobQueue
from .notifier import CatalogNotifier
from .publisher import Publisher
from .repository import Repository
from .supervisor import SupervisorClient
from .uploads import UploadStore

_LOGGER = logging.getLogger(__name__)

# The Ingress UI routers, added by Tasks 6 and 7. Each module exposes a module-level ``router``.
# They are imported by name and skipped while the module does not exist yet; once both exist this
# list is replaced by plain imports.
_UI_ROUTER_MODULES = ("api_ui_organize", "api_ui_sounds")
_NO_SUPERVISOR = "The Supervisor API is not available"
_VALIDATION_LOCATIONS = {"body", "query", "path", "header", "cookie"}

type _ErrorHandler = Callable[[Request, Exception], Awaitable[Response]]


def create_app(
    paths: Paths,
    *,
    supervisor: SupervisorClient | None = None,
    start_background: bool = True,
) -> FastAPI:
    """Build the Studio app.

    Storage, the token and the instance id are prepared here. With ``start_background`` the
    lifespan also runs the render worker, Supervisor integration and periodic cleanup.
    """
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    # The interactive docs would expose the API surface on a LAN-reachable port, so they stay off.
    app = FastAPI(
        title="Sound Effects Studio",
        version=__version__,
        lifespan=_make_lifespan(start_background),
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    db = Database(paths.database_path)
    try:
        publisher = Publisher(paths)
        # Called after each commit, possibly from worker threads; the notifier exists only while
        # the lifespan runs, so look it up per call instead of capturing it.
        repo = Repository(db, on_catalog_change=lambda revision: _catalog_changed(app, revision))
        state = app.state
        state.discovery_lock = asyncio.Lock()
        state.paths = paths
        state.db = db
        state.repo = repo
        state.publisher = publisher
        state.jobs = JobQueue(repo, publisher, paths)
        state.uploads = UploadStore(paths, lambda: repo.get_settings().max_upload_mb * 1024 * 1024)
        state.tokens = TokenStore(paths.data_dir / "api_token")
        state.supervisor = supervisor if supervisor is not None else SupervisorClient(None)
        state.notifier = None
        state.instance_id = _load_instance_id(paths.data_dir / "instance_id")
        state.www_status = publisher.ensure_dirs()
        state.discovery_status = {
            "status": "unavailable",
            "message": None if state.supervisor.available else _NO_SUPERVISOR,
        }
        state.media_base_url_effective = ""
        state.hostname = None
        _install_error_handlers(app)
        app.include_router(api_v1.router)
        _include_optional_routers(app)
        _install_ui_shell(app)
    except BaseException:
        db.close()
        raise
    return app


def _catalog_changed(app: FastAPI, revision: int) -> None:
    notifier: CatalogNotifier | None = app.state.notifier
    if notifier is not None:
        notifier.mark_changed(revision)


def _load_instance_id(path: Path) -> str:
    try:
        existing = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        existing = ""
    if existing:
        return existing
    instance_id = uuid.uuid4().hex
    path.write_text(instance_id, encoding="utf-8")
    return instance_id


# --- lifespan ------------------------------------------------------------------------------


def _make_lifespan(
    start_background: bool,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        # Callbacks run last-in first-out; each is guarded, so one failure cannot skip the rest.
        async with AsyncExitStack() as stack:
            stack.callback(_close_database, app)
            if start_background:
                await _start_background_services(app, stack)
            yield

    return lifespan


async def _start_background_services(app: FastAPI, stack: AsyncExitStack) -> None:
    """Start the render worker, notifier and Supervisor tasks; registers their shutdown.

    Shutdown order: Supervisor tasks, render worker, notifier, Supervisor client, database.
    """
    state = app.state
    supervisor: SupervisorClient = state.supervisor
    _on_exit(stack, "close the Supervisor client", supervisor.aclose)

    notifier = CatalogNotifier(
        lifecycle.catalog_sender(supervisor), delay=lifecycle.CATALOG_NOTIFY_DELAY
    )
    state.notifier = notifier

    async def close_notifier() -> None:
        state.notifier = None
        await notifier.close()

    _on_exit(stack, "close the catalog notifier", close_notifier)

    _on_exit(stack, "stop the render worker", state.jobs.stop)
    await state.jobs.start()

    # The Supervisor steps must neither delay startup nor announce an unbound port, so they run
    # beside the server instead of inside the lifespan.
    _run_task(stack, "supervisor-startup", lifecycle.supervisor_startup(app))
    _run_task(stack, "housekeeping", lifecycle.housekeeping(app, lifecycle.HOUSEKEEPING_INTERVAL))


def _run_task(stack: AsyncExitStack, name: str, work: Coroutine[Any, Any, None]) -> None:
    task = asyncio.create_task(work, name=f"sound-effects-{name}")
    _on_exit(stack, f"stop the {name} task", partial(_cancel, task))


async def _cancel(task: asyncio.Task[None]) -> None:
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


def _on_exit(stack: AsyncExitStack, what: str, callback: Callable[[], Awaitable[None]]) -> None:
    async def guarded() -> None:
        try:
            await callback()
        except Exception:
            _LOGGER.exception("Could not %s", what)

    stack.push_async_callback(guarded)


def _close_database(app: FastAPI) -> None:
    try:
        app.state.db.close()
    except Exception:
        _LOGGER.exception("Could not close the database")


# --- errors --------------------------------------------------------------------------------


def _install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(NotFoundError, _status_handler(404))
    app.add_exception_handler(ConflictError, _status_handler(409))
    app.add_exception_handler(InvalidError, _status_handler(422))
    app.add_exception_handler(RequestValidationError, _validation_handler)


def _status_handler(status_code: int) -> _ErrorHandler:
    async def handler(_request: Request, exc: Exception) -> Response:
        return JSONResponse({"detail": str(exc)}, status_code=status_code)

    return handler


async def _validation_handler(_request: Request, exc: Exception) -> Response:
    """Answer 422 with the contract's ``{"detail": "<string>"}`` instead of FastAPI's list."""
    errors: Sequence[Any] = ()
    if isinstance(exc, RequestValidationError):
        errors = exc.errors()
    parts = [f"{_field(error['loc'])}: {_message(error['msg'])}" for error in errors]
    return JSONResponse({"detail": "; ".join(parts) or "Invalid request"}, status_code=422)


def _field(loc: tuple[int | str, ...]) -> str:
    """``("body", "events", 0, "sound_id")`` becomes ``events.0.sound_id``."""
    parts = list(loc[1:] if loc and loc[0] in _VALIDATION_LOCATIONS else loc)
    if not parts or isinstance(parts[0], int):
        return "body"
    return ".".join(str(part) for part in parts)


def _message(message: str) -> str:
    return message.removeprefix("Value error, ")


# --- routers and UI shell ------------------------------------------------------------------


def _include_optional_routers(app: FastAPI) -> None:
    """Add the Ingress UI routers that exist; each is guarded by ``require_ingress``."""
    package = __package__ or "sound_effects_studio"
    included: list[str] = []
    for name in _UI_ROUTER_MODULES:
        qualified = f"{package}.{name}"
        try:
            module = importlib.import_module(qualified)
        except ModuleNotFoundError as exc:
            if exc.name != qualified:
                raise  # the router exists but one of its own imports is broken
            continue
        app.include_router(module.router, dependencies=[Depends(require_ingress)])
        included.append(name)
    _LOGGER.debug("UI routers included: %s", ", ".join(included) or "none")


def _install_ui_shell(app: FastAPI) -> None:
    @app.get("/", dependencies=[Depends(require_ingress)], include_in_schema=False)
    async def index(request: Request) -> Response:
        page: Path = request.app.state.paths.static_dir / "index.html"
        if not page.is_file():
            return PlainTextResponse("UI not built", status_code=503)
        return FileResponse(page, headers={"Cache-Control": "no-cache"})

    @app.get(
        "/assets/{asset_path:path}",
        dependencies=[Depends(require_ingress)],
        include_in_schema=False,
    )
    async def asset(asset_path: str, request: Request) -> Response:
        root = (request.app.state.paths.static_dir / "assets").resolve()
        try:
            target = (root / asset_path).resolve()
        except (OSError, ValueError):
            raise HTTPException(status_code=404, detail="Not Found") from None
        if not target.is_relative_to(root) or not target.is_file():
            raise HTTPException(status_code=404, detail="Not Found")
        return FileResponse(target)
