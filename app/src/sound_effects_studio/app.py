"""FastAPI application factory and lifespan."""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager, suppress
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

_UI_ROUTER_MODULES = ("api_ui_organize", "api_ui_sounds")
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
        state.paths = paths
        state.db = db
        state.repo = repo
        state.publisher = publisher
        state.jobs = JobQueue(repo, publisher, paths)
        state.tokens = TokenStore(paths.data_dir / "api_token")
        state.supervisor = supervisor if supervisor is not None else SupervisorClient(None)
        state.notifier = None
        state.instance_id = _load_instance_id(paths.data_dir / "instance_id")
        state.www_status = publisher.ensure_dirs()
        state.discovery_status = {"status": "unavailable", "message": None}
        state.media_base_url_effective = ""
    except BaseException:
        db.close()
        raise

    _install_error_handlers(app)
    app.include_router(api_v1.router)
    _include_optional_routers(app)
    _install_ui_shell(app)
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
        try:
            if start_background:
                async with _background_services(app):
                    yield
            else:
                yield
        finally:
            app.state.db.close()

    return lifespan


@asynccontextmanager
async def _background_services(app: FastAPI) -> AsyncGenerator[None]:
    state = app.state
    supervisor: SupervisorClient = state.supervisor
    await state.jobs.start()
    notifier = CatalogNotifier(
        lifecycle.catalog_sender(supervisor), delay=lifecycle.CATALOG_NOTIFY_DELAY
    )
    state.notifier = notifier
    cleanup = asyncio.create_task(
        lifecycle.housekeeping(app, lifecycle.HOUSEKEEPING_INTERVAL), name="sound-effects-cleanup"
    )
    try:
        if supervisor.available:
            await lifecycle.publish_discovery(app)
            state.media_base_url_effective = await lifecycle.detect_media_base_url(
                supervisor, state.repo.get_settings().media_base_url
            )
            state.www_status.served = await lifecycle.check_www_served(state.paths.publish_dir)
        else:
            state.discovery_status = {
                "status": "unavailable",
                "message": "The Supervisor API is not available",
            }
        yield
    finally:
        cleanup.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup
        await state.jobs.stop()
        await notifier.close()
        state.notifier = None
        await supervisor.aclose()


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
    for name in _UI_ROUTER_MODULES:
        qualified = f"{package}.{name}"
        if importlib.util.find_spec(qualified) is None:
            continue
        module = importlib.import_module(qualified)
        app.include_router(module.router, dependencies=[Depends(require_ingress)])


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
