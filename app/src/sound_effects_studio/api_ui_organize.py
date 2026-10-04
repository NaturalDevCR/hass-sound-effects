"""Ingress UI endpoints for app state, settings and catalog organization."""

from __future__ import annotations

import asyncio
from datetime import date as date_type
from typing import cast

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from starlette.responses import Response

from . import __version__
from .errors import InvalidError, NotFoundError
from .lifecycle import detect_media_base_url, publish_discovery
from .models import (
    Category,
    CategoryCreate,
    CategoryUpdate,
    Profile,
    ProfileCreate,
    ProfileUpdate,
    Season,
    SeasonCreate,
    SeasonUpdate,
    Settings,
    slugify,
)
from .repository import Repository
from .seasons import resolve_calendar_season

router = APIRouter(prefix="/api/ui")


class CategoryOrder(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ids: list[str]


class ProfileApply(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sound_ids: list[str] | None = None
    category_id: str | None = None


def _repo(request: Request) -> Repository:
    return request.app.state.repo


@router.get("/state")
async def get_state(request: Request) -> dict[str, object]:
    state = request.app.state
    www = state.www_status
    return {
        "version": __version__,
        "api_token_masked": state.tokens.masked(),
        "catalog_revision": state.repo.catalog_revision(),
        "discovery": state.discovery_status,
        "www": {
            "exists": www.exists,
            "served": www.served,
            "created_by_app": www.created_by_app,
        },
        "media_base_url_effective": state.media_base_url_effective,
        "hostname": state.hostname,
        "storage": await asyncio.to_thread(state.publisher.storage_usage),
        "settings": state.repo.get_settings(),
    }


@router.get("/token")
async def get_token(request: Request) -> dict[str, str]:
    return {"token": request.app.state.tokens.get()}


@router.post("/token/rotate")
async def rotate_token(request: Request, background_tasks: BackgroundTasks) -> dict[str, str]:
    request.app.state.tokens.rotate()
    if request.app.state.supervisor.available:
        background_tasks.add_task(publish_discovery, request.app)
    return {"api_token_masked": request.app.state.tokens.masked()}


@router.get("/settings", response_model=Settings)
async def get_settings(request: Request) -> Settings:
    return _repo(request).get_settings()


@router.put("/settings", response_model=Settings)
async def put_settings(data: Settings, request: Request) -> Settings:
    seen: set[str] = set()
    for target in data.audition_targets:
        if target.id in seen:
            raise InvalidError(f"Audition target id '{target.id}' is duplicated.")
        seen.add(target.id)
        domain = "media_player" if target.kind == "media_player" else "script"
        entity_domain, separator, object_id = target.entity_id.partition(".")
        if entity_domain != domain or not separator or not object_id.strip():
            raise InvalidError(
                f"Audition target '{target.id}' must use an entity_id in the {domain} domain."
            )
        if target.volume is not None and not 0 <= target.volume <= 1:
            raise InvalidError("Audition target volume must be between 0 and 1.")
    repo = _repo(request)
    saved = repo.update_settings(data)
    supervisor = request.app.state.supervisor
    request.app.state.media_base_url_effective = await detect_media_base_url(
        supervisor, saved.media_base_url
    )
    return saved


@router.get("/categories", response_model=list[Category])
async def list_categories(request: Request) -> list[Category]:
    return _repo(request).list_categories()


@router.post("/categories", response_model=Category)
async def create_category(data: CategoryCreate, request: Request) -> Category:
    repo = _repo(request)
    if data.id is None:
        data = data.model_copy(update={"id": slugify(data.name)})
    return repo.create_category(data)


@router.patch("/categories/{category_id}", response_model=Category)
async def patch_category(category_id: str, data: CategoryUpdate, request: Request) -> Category:
    return _repo(request).update_category(category_id, data)


@router.delete("/categories/{category_id}", status_code=204)
async def delete_category(category_id: str, request: Request) -> Response:
    _repo(request).delete_category(category_id)
    return Response(status_code=204)


@router.put("/categories/order", response_model=list[Category])
async def reorder_categories(data: CategoryOrder, request: Request) -> list[Category]:
    try:
        return _repo(request).reorder_categories(data.ids)
    except NotFoundError as exc:
        raise InvalidError(str(exc)) from exc


@router.get("/seasons", response_model=list[Season])
async def list_seasons(request: Request) -> list[Season]:
    return _repo(request).list_seasons()


@router.post("/seasons", response_model=Season)
async def create_season(data: SeasonCreate, request: Request) -> Season:
    repo = _repo(request)
    if data.id is None:
        data = data.model_copy(update={"id": slugify(data.name)})
    return repo.create_season(data)


@router.patch("/seasons/{season_id}", response_model=Season)
async def patch_season(season_id: str, data: SeasonUpdate, request: Request) -> Season:
    repo = _repo(request)
    return repo.update_season(season_id, data)


@router.delete("/seasons/{season_id}", status_code=204)
async def delete_season(season_id: str, request: Request) -> Response:
    repo = _repo(request)
    if repo.get_season(season_id).builtin:
        raise HTTPException(status_code=400, detail="The regular season cannot be deleted.")
    repo.delete_season(season_id)
    return Response(status_code=204)


@router.get("/seasons/resolve")
async def resolve_season(date: str, request: Request) -> dict[str, str]:
    try:
        parsed = date_type.fromisoformat(date)
    except ValueError:
        raise InvalidError("Date must use YYYY-MM-DD format.") from None
    if parsed.isoformat() != date:
        raise InvalidError("Date must use YYYY-MM-DD format.")
    season_id = resolve_calendar_season(_repo(request).list_seasons(), parsed)
    return {"date": date, "season_id": season_id}


@router.get("/profiles", response_model=list[Profile])
async def list_profiles(request: Request) -> list[Profile]:
    return _repo(request).list_profiles()


@router.post("/profiles", response_model=Profile)
async def create_profile(data: ProfileCreate, request: Request) -> Profile:
    repo = _repo(request)
    if data.id is None:
        data = data.model_copy(update={"id": slugify(data.name)})
    return repo.create_profile(data)


@router.patch("/profiles/{profile_id}")
async def patch_profile(
    profile_id: str, data: ProfileUpdate, request: Request
) -> dict[str, object]:
    profile, affected = _repo(request).update_profile(profile_id, data)
    return {"profile": profile, "affected_sound_ids": affected}


@router.delete("/profiles/{profile_id}", status_code=204)
async def delete_profile(profile_id: str, request: Request) -> Response:
    _repo(request).delete_profile(profile_id)
    return Response(status_code=204)


@router.post("/profiles/{profile_id}/apply")
async def apply_profile(profile_id: str, data: ProfileApply, request: Request) -> dict[str, int]:
    repo = _repo(request)
    profile = repo.get_profile(profile_id)
    if (data.sound_ids is None) == (data.category_id is None):
        raise InvalidError("Provide exactly one of sound_ids or category_id.")
    if data.category_id is not None:
        repo.get_category(data.category_id)
        sound_ids = [
            sound.id for sound in repo.list_sounds() if sound.category_id == data.category_id
        ]
    else:
        sound_ids = cast("list[str]", data.sound_ids)
    sound_ids = list(dict.fromkeys(sound_ids))
    sounds = [repo.get_sound(sound_id) for sound_id in sound_ids]
    for sound in sounds:
        sound_id = sound.id
        recipe = sound.recipe.model_copy(update={"profile_id": profile.id})
        repo.set_recipe(sound_id, recipe)
        request.app.state.jobs.enqueue_publish(sound_id)
    return {"queued": len(sound_ids)}
