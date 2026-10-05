"""Ingress UI sounds, uploads, folder imports, audition, jobs and audio streams."""

from __future__ import annotations

import asyncio
import mimetypes
import re
import shutil
from contextlib import suppress
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict

from . import media
from .config import Paths
from .errors import InvalidError, NotFoundError
from .importer import ImportBrowser
from .jobs import JobQueue
from .media import SUPPORTED_EXTENSIONS
from .models import BulkSet, Job, Recipe, Sound, SoundUpdate
from .publisher import Publisher
from .repository import Repository
from .supervisor import SupervisorClient, SupervisorError
from .uploads import (
    CHUNK_SIZE,
    UnsupportedUploadError,
    UploadStore,
    UploadTooLargeError,
    safe_filename,
)

router = APIRouter(prefix="/api/ui")


class UploadCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: str
    size: int


class Placement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category_id: str
    seasons: list[str]
    all_seasons: bool
    tags: list[str]
    profile_id: str | None = None


class UploadComplete(Placement):
    title: str | None = None


class ImportCreate(Placement):
    paths: list[str]


class SoundIds(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[str]


class BulkUpdate(SoundIds):
    set: BulkSet


class AuditionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_id: str
    use_preview: bool


def _repo(request: Request) -> Repository:
    return request.app.state.repo


def _jobs(request: Request) -> JobQueue:
    return request.app.state.jobs


def _publisher(request: Request) -> Publisher:
    return request.app.state.publisher


def _paths(request: Request) -> Paths:
    return request.app.state.paths


def _uploads(request: Request) -> UploadStore:
    return request.app.state.uploads


def _supervisor(request: Request) -> SupervisorClient:
    return request.app.state.supervisor


def _browser(request: Request) -> ImportBrowser:
    return ImportBrowser(_paths(request).import_roots)


def _validate_profile(repo: Repository, profile_id: str | None) -> None:
    if profile_id is not None:
        try:
            repo.get_profile(profile_id)
        except NotFoundError as exc:
            raise InvalidError(str(exc)) from exc


def _placement_profile(repo: Repository, data: Placement) -> str | None:
    try:
        category = repo.get_category(data.category_id)
    except NotFoundError as exc:
        raise InvalidError(str(exc)) from exc
    profile_id = (
        data.profile_id if "profile_id" in data.model_fields_set else category.default_profile_id
    )
    _validate_profile(repo, profile_id)
    return profile_id


def _create_sound(
    repo: Repository,
    data: Placement,
    filename: str,
    profile_id: str | None,
    title: str | None = None,
) -> Sound:
    key = safe_filename(filename, preserve_extension_case=True)
    if title is None:
        title = (
            re.sub(r"\s+", " ", Path(key).stem.replace("-", " ").replace("_", " ")).strip()
            or Path(key).stem
            or "sound"
        )
    return repo.create_sound(
        category_id=data.category_id,
        title=title,
        key=key,
        tags=data.tags,
        seasons=data.seasons,
        all_seasons=data.all_seasons,
        recipe=Recipe(profile_id=profile_id),
        original=None,
    )


def _validate_recipe(repo: Repository, sound: Sound, recipe: Recipe) -> None:
    if sound.original is None:
        raise InvalidError("sound is still processing")
    recipe.validate_for(sound.original.duration)
    _validate_profile(repo, recipe.profile_id)


def _published_file(request: Request, sound: Sound) -> Path:
    if sound.published is None:
        raise NotFoundError("Published audio is missing.")
    file = _publisher(request).published_path(sound.published.filename)
    if not file.is_file():
        raise NotFoundError("Published audio is missing.")
    return file


@router.get("/sounds")
async def list_sounds(request: Request) -> list[Sound]:
    return _repo(request).list_sounds()


@router.post("/sounds/bulk")
async def bulk_update(data: BulkUpdate, request: Request) -> dict[str, int]:
    repo = _repo(request)
    ids = list(dict.fromkeys(data.ids))
    has_profile = "profile_id" in data.set.model_fields_set
    sounds: list[Sound] = []
    if has_profile:
        # Resolve every id before any metadata or recipe changes.
        sounds = [repo.get_sound(sound_id) for sound_id in ids]
        _validate_profile(repo, data.set.profile_id)
    updated = repo.bulk_update(ids, data.set)
    for sound in sounds:
        recipe = sound.recipe.model_copy(update={"profile_id": data.set.profile_id})
        repo.set_recipe(sound.id, recipe)
        _jobs(request).enqueue_publish(sound.id)
    return {"updated": updated, "queued": len(sounds)}


@router.post("/sounds/bulk-delete")
async def bulk_delete(data: SoundIds, request: Request) -> dict[str, int]:
    repo = _repo(request)
    ids = list(dict.fromkeys(data.ids))
    for sound_id in ids:
        repo.get_sound(sound_id)
    for sound_id in ids:
        _publisher(request).remove_all(sound_id)
        repo.delete_sound(sound_id, _publisher(request).published_filenames(sound_id))
    return {"deleted": len(ids)}


@router.get("/sounds/{sound_id}")
async def get_sound(sound_id: str, request: Request) -> Sound:
    return _repo(request).get_sound(sound_id)


@router.patch("/sounds/{sound_id}")
async def patch_sound(sound_id: str, data: SoundUpdate, request: Request) -> Sound:
    return _repo(request).update_sound(sound_id, data)


@router.put("/sounds/{sound_id}/recipe")
async def put_recipe(sound_id: str, data: Recipe, request: Request) -> dict[str, Sound | Job]:
    repo = _repo(request)
    _validate_recipe(repo, repo.get_sound(sound_id), data)
    sound = repo.set_recipe(sound_id, data)
    return {"sound": sound, "job": _jobs(request).enqueue_publish(sound_id)}


@router.post("/sounds/{sound_id}/preview")
async def post_preview(sound_id: str, data: Recipe, request: Request) -> dict[str, Job]:
    repo = _repo(request)
    _validate_recipe(repo, repo.get_sound(sound_id), data)
    return {"job": _jobs(request).enqueue_preview(sound_id, data)}


@router.delete("/sounds/{sound_id}", status_code=204)
async def delete_sound(sound_id: str, request: Request) -> Response:
    repo = _repo(request)
    repo.get_sound(sound_id)
    _publisher(request).remove_all(sound_id)
    repo.delete_sound(sound_id, _publisher(request).published_filenames(sound_id))
    return Response(status_code=204)


@router.get("/sounds/{sound_id}/original")
async def get_original(sound_id: str, request: Request) -> FileResponse:
    sound = _repo(request).get_sound(sound_id)
    directory = _paths(request).originals_dir / sound.id
    files = [file for file in directory.iterdir() if file.is_file()] if directory.is_dir() else []
    if len(files) != 1:
        raise NotFoundError("Original audio is missing.")
    file = files[0]
    media_type = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
    return FileResponse(file, media_type=media_type, headers={"Cache-Control": "no-store"})


@router.get("/sounds/{sound_id}/preview")
async def get_preview(sound_id: str, request: Request) -> FileResponse:
    sound = _repo(request).get_sound(sound_id)
    file = _paths(request).previews_dir / f"{sound.id}.mp3"
    if not file.is_file():
        raise NotFoundError("Preview audio is missing.")
    return FileResponse(file, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})


@router.get("/sounds/{sound_id}/published")
async def get_published(sound_id: str, request: Request) -> FileResponse:
    sound = _repo(request).get_sound(sound_id)
    return FileResponse(_published_file(request, sound), media_type="audio/mpeg")


@router.post("/sounds/{sound_id}/audition")
async def audition(sound_id: str, data: AuditionRequest, request: Request) -> dict[str, bool | str]:
    repo = _repo(request)
    sound = repo.get_sound(sound_id)
    target = next(
        (item for item in repo.get_settings().audition_targets if item.id == data.target_id), None
    )
    if target is None:
        raise NotFoundError("Unknown audition target.")
    file = _paths(request).previews_dir / f"{sound.id}.mp3"
    if not data.use_preview or not file.is_file():
        file = _published_file(request, sound)
    base_url: str = request.app.state.media_base_url_effective
    if not base_url:
        raise InvalidError("media base URL unknown")
    supervisor = _supervisor(request)
    if not supervisor.available:
        raise HTTPException(status_code=503, detail="The Supervisor API is not available")
    rel = await asyncio.to_thread(_publisher(request).audition_copy, file, sound.id)
    url = base_url.rstrip("/") + rel
    duration = (
        sound.published.duration
        if sound.published
        else (sound.original.duration if sound.original else 0.0)
    )
    try:
        if target.kind == "media_player":
            await supervisor.call_service(
                "media_player",
                "play_media",
                {
                    "entity_id": target.entity_id,
                    "media_content_id": url,
                    "media_content_type": "music",
                    "announce": True,
                },
            )
        else:
            with suppress(media.MediaError):
                duration = (await media.probe(file)).duration
            await supervisor.call_service(
                "script",
                "turn_on",
                {
                    "entity_id": target.entity_id,
                    "variables": {
                        "url": url,
                        "duration": duration,
                        "title": sound.title,
                        "volume": target.volume,
                    },
                },
            )
    except SupervisorError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True, "url": url}


@router.post("/uploads")
async def create_upload(data: UploadCreate, request: Request) -> dict[str, str | int]:
    try:
        upload_id = await asyncio.to_thread(_uploads(request).create, data.filename, data.size)
    except UnsupportedUploadError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except UploadTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    return {"upload_id": upload_id, "chunk_size": CHUNK_SIZE}


@router.put("/uploads/{upload_id}/chunks/{index}")
async def put_chunk(upload_id: str, index: int, request: Request) -> dict[str, int]:
    uploads = _uploads(request)
    try:
        limit = await asyncio.to_thread(uploads.chunk_limit, upload_id, index)
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                declared_length = int(content_length)
            except ValueError as exc:
                raise InvalidError("Invalid Content-Length.") from exc
            if declared_length > limit:
                raise UploadTooLargeError("Chunk exceeds the maximum or declared upload size.")
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > limit:
                raise UploadTooLargeError("Chunk exceeds the maximum or declared upload size.")
            data.extend(chunk)
        received = await asyncio.to_thread(uploads.write_chunk, upload_id, index, bytes(data))
    except UploadTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    return {"received": received}


@router.post("/uploads/{upload_id}/complete")
async def complete_upload(upload_id: str, data: UploadComplete, request: Request) -> Sound:
    uploads = _uploads(request)
    filename = await asyncio.to_thread(uploads.ready_filename, upload_id)
    repo = _repo(request)
    profile_id = _placement_profile(repo, data)
    sound = _create_sound(repo, data, filename, profile_id, title=data.title)
    try:
        finish = asyncio.create_task(
            asyncio.to_thread(uploads.finish, upload_id, _paths(request).originals_dir / sound.id)
        )
        try:
            await asyncio.shield(finish)
        except asyncio.CancelledError:
            with suppress(Exception):
                await finish
            raise
    except BaseException:
        _publisher(request).remove_all(sound.id)
        repo.delete_sound(sound.id, _publisher(request).published_filenames(sound.id))
        raise
    _jobs(request).enqueue_import(sound.id)
    return sound


@router.get("/import/browse")
async def browse_import(request: Request, path: str = "") -> dict[str, object]:
    return await asyncio.to_thread(_browser(request).browse, path)


@router.post("/import")
async def import_files(data: ImportCreate, request: Request) -> dict[str, list[Sound]]:
    repo = _repo(request)
    profile_id = _placement_profile(repo, data)
    browser = _browser(request)

    def validate_sources() -> list[tuple[str, Path]]:
        sources: list[tuple[str, Path]] = []
        for virtual_path in data.paths:
            source = browser.resolve(virtual_path)
            if not source.exists():
                raise NotFoundError("Import file does not exist.")
            filename = Path(virtual_path).name
            if Path(filename).suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            if not source.is_file():
                raise NotFoundError("Import file does not exist.")
            sources.append((filename, source))
        return sources

    sources = await asyncio.to_thread(validate_sources)
    sounds: list[Sound] = []
    for filename, source in sources:
        sound = _create_sound(repo, data, filename, profile_id)
        directory = _paths(request).originals_dir / sound.id
        try:

            def copy_source(
                source: Path = source, directory: Path = directory, filename: str = filename
            ) -> None:
                directory.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, directory / safe_filename(filename))

            copy = asyncio.create_task(asyncio.to_thread(copy_source))
            try:
                await asyncio.shield(copy)
            except asyncio.CancelledError:
                # A running thread cannot be cancelled; settle it before removing its output.
                with suppress(Exception):
                    await copy
                raise
        except BaseException:
            _publisher(request).remove_all(sound.id)
            repo.delete_sound(sound.id, _publisher(request).published_filenames(sound.id))
            raise
        _jobs(request).enqueue_import(sound.id)
        sounds.append(sound)
    return {"sounds": sounds}


@router.get("/jobs")
async def list_jobs(request: Request) -> list[Job]:
    return _jobs(request).list_jobs()
