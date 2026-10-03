"""One FIFO render worker with bounded, in-memory job history."""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
import shutil
from collections import deque
from contextlib import suppress
from dataclasses import dataclass

from . import media
from .config import Paths
from .models import Job, JobKind, OriginalInfo, Published, Recipe, utcnow_iso
from .publisher import Publisher
from .repository import Repository

_LOGGER = logging.getLogger(__name__)


@dataclass
class _Entry:
    job: Job
    recipe: Recipe | None = None


class JobQueue:
    def __init__(self, repo: Repository, publisher: Publisher, paths: Paths) -> None:
        self._repo = repo
        self._publisher = publisher
        self._paths = paths
        self._queued: deque[_Entry] = deque()
        self._finished: deque[Job] = deque(maxlen=50)
        self._running: Job | None = None
        self._worker: asyncio.Task[None] | None = None
        self._available = asyncio.Event()
        self._idle = asyncio.Event()
        self._idle.set()

    async def start(self) -> None:
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._work(), name="sound-effects-render-worker")

    async def stop(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            with suppress(asyncio.CancelledError):
                await self._worker
            self._worker = None
        # Shutdown also settles jobs that never started, so wait_idle remains usable.
        while self._queued:
            job = self._queued.popleft().job
            self._fail(job, "cancelled", cancelled=True)
            self._finish(job)
        self._available.clear()
        self._idle.set()

    def enqueue_import(self, sound_id: str) -> Job:
        return self._enqueue("import", sound_id)

    def enqueue_publish(self, sound_id: str) -> Job:
        return self._enqueue("publish", sound_id)

    def enqueue_preview(self, sound_id: str, recipe: Recipe) -> Job:
        return self._enqueue("preview", sound_id, recipe.model_copy(deep=True))

    def _enqueue(self, kind: JobKind, sound_id: str, recipe: Recipe | None = None) -> Job:
        sound = self._repo.get_sound(sound_id)
        job = Job(
            id=secrets.token_hex(6),
            kind=kind,
            sound_id=sound_id,
            sound_title=sound.title,
            created_at=utcnow_iso(),
        )
        entry = _Entry(job, recipe)
        for index, queued in enumerate(self._queued):
            if kind == "publish" and queued.job.kind == kind and queued.job.sound_id == sound_id:
                self._queued[index] = entry
                break
        else:
            self._queued.append(entry)
        self._idle.clear()
        self._available.set()
        return job

    def list_jobs(self) -> list[Job]:
        return (
            ([self._running] if self._running is not None else [])
            + [entry.job for entry in self._queued]
            + list(self._finished)
        )

    async def wait_idle(self, timeout: float = 60) -> None:
        await asyncio.wait_for(self._idle.wait(), timeout=timeout)

    def _finish(self, job: Job) -> None:
        job.finished_at = utcnow_iso()
        self._finished.appendleft(job)

    def _fail(self, job: Job, error: str, *, cancelled: bool = False) -> None:
        job.status = "failed"
        job.error = error[-400:]
        if job.kind == "preview":
            return
        try:
            sound = self._repo.get_sound(job.sound_id)
            if cancelled:
                if sound.status == "rendering":
                    status = "ready" if sound.published is not None else "failed"
                    self._repo.set_status(
                        job.sound_id, status, None if status == "ready" else job.error
                    )
                elif sound.status == "processing":
                    self._repo.set_status(job.sound_id, "failed", job.error)
            else:
                self._repo.set_status(job.sound_id, "failed", job.error)
        except Exception:
            _LOGGER.exception("Could not reset sound status for job %s", job.id)

    async def _work(self) -> None:
        while True:
            await self._available.wait()
            while self._queued:
                entry = self._queued.popleft()
                job = self._running = entry.job
                job.status = "running"
                job.started_at = utcnow_iso()
                try:
                    await self._execute(entry)
                except asyncio.CancelledError:
                    self._fail(job, "cancelled", cancelled=True)
                    raise
                except Exception as exc:
                    self._fail(job, str(exc))
                else:
                    job.status = "done"
                    job.progress = 1.0
                finally:
                    self._finish(job)
                    self._running = None
                    if not self._queued:
                        self._idle.set()
            self._available.clear()

    async def _execute(self, entry: _Entry) -> None:
        job = entry.job
        sound = self._repo.get_sound(job.sound_id)
        recipe = entry.recipe if entry.recipe is not None else sound.recipe
        if job.kind != "preview":
            self._repo.set_status(sound.id, "processing" if job.kind == "import" else "rendering")
        originals = [p for p in (self._paths.originals_dir / sound.id).iterdir() if p.is_file()]
        if len(originals) != 1:
            raise media.MediaError("Expected exactly one original audio file")
        src = originals[0]
        info = await media.probe(src)
        if job.kind == "import":
            self._repo.set_original(
                sound.id,
                OriginalInfo(
                    filename=src.name,
                    size=src.stat().st_size,
                    format=info.format,
                    codec=info.codec,
                    duration=info.duration,
                    sample_rate=info.sample_rate,
                    channels=info.channels,
                ),
            )
            maximum = self._repo.get_settings().max_duration_s
            if info.duration > maximum:
                raise media.MediaError(f"Audio is longer than {maximum} s")
        recipe.validate_for(info.duration)
        profile = self._repo.get_profile(recipe.profile_id) if recipe.profile_id else None
        tmp = self._publisher.temp_path(sound.id)
        final = None
        recorded = False
        try:
            if job.kind != "preview" and media.can_copy_verbatim(info, recipe):
                shutil.copyfile(src, tmp)
            else:

                def progress(value: float) -> None:
                    job.progress = min(1.0, max(0.0, value))

                await media.render(
                    src,
                    tmp,
                    recipe=recipe,
                    duration=info.duration,
                    channels=info.channels,
                    profile=profile,
                    on_progress=progress,
                )
            output = await media.probe(tmp)
            if job.kind == "preview":
                # /data and /homeassistant/www can be different mounts. Stage the complete
                # render beside the preview so the final replace is always same-filesystem.
                preview = self._paths.previews_dir / f"{sound.id}.mp3"
                preview_tmp = preview.with_name(f".tmp-{sound.id}-{secrets.token_hex(4)}.mp3")
                try:
                    shutil.copyfile(tmp, preview_tmp)
                    os.replace(preview_tmp, preview)
                finally:
                    preview_tmp.unlink(missing_ok=True)
                self._repo.set_has_preview(sound.id, True)
                return
            current = self._repo.get_sound(sound.id)
            revision = (current.published.revision if current.published else 0) + 1
            filename = self._publisher.commit(tmp, sound.id, revision)
            final = self._publisher.published_path(filename)
            loudness_lufs = true_peak_db = None
            try:
                measured = await media.measure_loudness(final)
                loudness_lufs, true_peak_db = measured.input_i, measured.input_tp
            except media.MediaError:
                _LOGGER.debug(
                    "Could not measure published loudness for %s", sound.id, exc_info=True
                )
            self._repo.set_published(
                sound.id,
                Published(
                    revision=revision,
                    filename=filename,
                    duration=output.duration,
                    loudness_lufs=loudness_lufs,
                    true_peak_db=true_peak_db,
                    size=final.stat().st_size,
                    published_at=utcnow_iso(),
                ),
            )
            recorded = True
            try:
                self._publisher.cleanup(sound.id, keep={revision, revision - 1})
            except OSError:
                _LOGGER.exception("Could not clean up old revisions for %s", sound.id)
        finally:
            tmp.unlink(missing_ok=True)
            if final is not None and not recorded:
                final.unlink(missing_ok=True)
