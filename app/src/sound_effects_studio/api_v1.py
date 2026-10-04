"""Integration API v1, used by the sound_effects Home Assistant integration."""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from . import __version__
from .auth import require_bearer
from .models import SelectionBatch
from .repository import Repository

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_bearer)])


@router.get("/health")
async def health(request: Request) -> dict[str, str | int]:
    return {
        "status": "ok",
        "version": __version__,
        "api_version": 1,
        "instance_id": request.app.state.instance_id,
    }


@router.get("/catalog")
async def catalog(request: Request) -> Response:
    repo: Repository = request.app.state.repo
    current = _etag(repo.catalog_revision())
    if _etag_matches(request.headers.get("If-None-Match", ""), current):
        return Response(status_code=304, headers={"ETag": current})
    document = repo.catalog_document()
    # Tag the body with the revision it was built from, not the one that is current by now.
    return JSONResponse(document, headers={"ETag": _etag(cast("int", document["revision"]))})


@router.post("/selections", status_code=204)
async def selections(batch: SelectionBatch, request: Request) -> Response:
    repo: Repository = request.app.state.repo
    repo.record_selections(batch.events)
    return Response(status_code=204)


def _etag(revision: int) -> str:
    return f'"rev-{revision}"'


def _etag_matches(header: str, etag: str) -> bool:
    """Whether an ``If-None-Match`` header lists ``etag`` (weak validators compare equal)."""
    for candidate in header.split(","):
        value = candidate.strip().removeprefix("W/")
        if value in ("*", etag):
            return True
    return False
