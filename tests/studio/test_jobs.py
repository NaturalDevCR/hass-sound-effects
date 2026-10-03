"""Real media pipeline, queue lifecycle and catalog notification contracts."""

import asyncio
import re
import shutil
from collections.abc import AsyncIterator, Iterator

import pytest
import sound_effects_studio.media as media
from sound_effects_studio.config import Paths
from sound_effects_studio.db import Database
from sound_effects_studio.jobs import JobQueue
from sound_effects_studio.models import Recipe, Settings
from sound_effects_studio.notifier import CatalogNotifier
from sound_effects_studio.publisher import Publisher
from sound_effects_studio.repository import Repository

pytestmark = pytest.mark.studio


@pytest.fixture
def repo(paths: Paths) -> Iterator[Repository]:
    db = Database(paths.database_path)
    yield Repository(db)
    db.close()


@pytest.fixture
def publisher(paths: Paths) -> Publisher:
    publisher = Publisher(paths)
    publisher.ensure_dirs()
    return publisher


@pytest.fixture
async def queue(repo: Repository, publisher: Publisher, paths: Paths) -> AsyncIterator[JobQueue]:
    queue = JobQueue(repo, publisher, paths)
    await queue.start()
    try:
        yield queue
    finally:
        await queue.stop()


def add_sound(repo, paths, src, recipe=None):
    sound = repo.create_sound(
        category_id="general",
        title=src.stem,
        key=src.name,
        tags=[],
        seasons=["regular"],
        all_seasons=False,
        recipe=recipe or Recipe(),
        original=None,
    )
    directory = paths.originals_dir / sound.id
    directory.mkdir()
    shutil.copyfile(src, directory / src.name)
    return sound


async def imported(queue, repo, paths, make_tone, name="tone.mp3", recipe=None):
    sound = add_sound(repo, paths, make_tone(name=name, seconds=2), recipe)
    queue.enqueue_import(sound.id)
    await queue.wait_idle()
    assert repo.get_sound(sound.id).status == "ready"
    return repo.get_sound(sound.id)


async def test_import_mp3_identity(queue, repo, paths, make_tone):
    src = make_tone(name="identity.mp3", seconds=2)
    sound = add_sound(repo, paths, src)
    revision = repo.catalog_revision()
    job = queue.enqueue_import(sound.id)
    await queue.wait_idle()
    stored = repo.get_sound(sound.id)
    assert job.status == "done" and job.progress == 1 and job.error is None
    assert re.fullmatch(r"[a-f0-9]{12}", job.id)
    assert job.started_at and job.finished_at and job.created_at.endswith("Z")
    assert stored.status == "ready" and stored.original.filename == src.name
    assert stored.published.revision == 1 and stored.published.mime_type == "audio/mpeg"
    assert (paths.publish_dir / stored.published.filename).read_bytes() == src.read_bytes()
    assert repo.catalog_revision() > revision
    assert not list(paths.publish_dir.glob(".tmp-*"))


async def test_import_wav_with_profile(queue, repo, paths, make_tone):
    sound = await imported(queue, repo, paths, make_tone, "tone.wav", Recipe(profile_id="standard"))
    info = await media.probe(paths.publish_dir / sound.published.filename)
    assert info.codec == "mp3" and info.sample_rate == 44100
    assert sound.published.loudness_lufs == pytest.approx(-16, abs=1)
    assert sound.published.true_peak_db is not None
    assert sound.published.size == (paths.publish_dir / sound.published.filename).stat().st_size


async def test_publish_trim_keeps_previous_revision(queue, repo, paths, make_tone):
    sound = await imported(queue, repo, paths, make_tone)
    old = paths.publish_dir / sound.published.filename
    previous = old.read_bytes()
    repo.set_recipe(sound.id, Recipe(trim_start=0.5, trim_end=1.5))
    job = queue.enqueue_publish(sound.id)
    await queue.wait_idle()
    stored = repo.get_sound(sound.id)
    assert job.status == "done" and stored.published.revision == 2
    assert old.read_bytes() == previous
    assert stored.published.duration == pytest.approx(1, abs=0.06)
    assert not list(paths.publish_dir.glob(".tmp-*"))


async def test_publish_failure_preserves_revision_and_worker(queue, repo, paths, make_tone):
    sound = await imported(queue, repo, paths, make_tone)
    old = paths.publish_dir / sound.published.filename
    previous = old.read_bytes()
    (paths.originals_dir / sound.id / sound.original.filename).write_bytes(b"garbage")
    job = queue.enqueue_publish(sound.id)
    next_sound = add_sound(repo, paths, make_tone(name="next.wav", seconds=1))
    next_job = queue.enqueue_import(next_sound.id)
    await queue.wait_idle()
    stored = repo.get_sound(sound.id)
    assert job.status == "failed" and job.error and len(job.error) <= 400
    assert stored.status == "failed" and stored.published == sound.published
    assert old.read_bytes() == previous
    assert next_job.status == "done"
    assert not list(paths.publish_dir.glob(".tmp-*"))


async def test_preview_preserves_sound_and_catalog(queue, repo, paths, make_tone):
    sound = await imported(queue, repo, paths, make_tone)
    revision = repo.catalog_revision()
    job = queue.enqueue_preview(sound.id, Recipe(trim_end=1))
    await queue.wait_idle()
    stored = repo.get_sound(sound.id)
    assert job.status == "done" and stored.has_preview and stored.status == "ready"
    assert stored.recipe == sound.recipe and stored.published == sound.published
    assert repo.catalog_revision() == revision
    assert (await media.probe(paths.previews_dir / f"{sound.id}.mp3")).duration == pytest.approx(
        1, abs=0.06
    )
    preview = (paths.previews_dir / f"{sound.id}.mp3").read_bytes()
    job = queue.enqueue_preview(sound.id, Recipe(trim_start=10))
    await queue.wait_idle()
    assert job.status == "failed"
    assert (paths.previews_dir / f"{sound.id}.mp3").read_bytes() == preview
    assert repo.get_sound(sound.id).status == "ready" and repo.catalog_revision() == revision


async def test_coalescing_and_fifo(repo, publisher, paths, make_tone):
    sound = add_sound(repo, paths, make_tone(name="one.mp3", seconds=1))
    queue = JobQueue(repo, publisher, paths)
    first = queue.enqueue_publish(sound.id)
    preview = queue.enqueue_preview(sound.id, Recipe())
    replacement = queue.enqueue_publish(sound.id)
    assert [job.id for job in queue.list_jobs()] == [replacement.id, preview.id]
    assert first.id != replacement.id
    await queue.start()
    try:
        await queue.wait_idle()
        assert [job.id for job in queue.list_jobs()] == [preview.id, replacement.id]
    finally:
        await queue.stop()


async def test_import_rejects_long_audio(queue, repo, paths, make_tone):
    repo.update_settings(Settings(max_duration_s=1))
    sound = add_sound(repo, paths, make_tone(seconds=2))
    job = queue.enqueue_import(sound.id)
    await queue.wait_idle()
    stored = repo.get_sound(sound.id)
    assert job.status == "failed" and "longer than 1 s" in job.error
    assert stored.status == "failed" and stored.published is None and stored.original is not None


async def test_loudness_failure_does_not_fail_publish(queue, repo, paths, make_tone, monkeypatch):
    async def fail(_path):
        raise media.MediaError("measurement failed")

    monkeypatch.setattr(media, "measure_loudness", fail)
    sound = await imported(queue, repo, paths, make_tone)
    assert sound.published.loudness_lufs is None and sound.published.true_peak_db is None


@pytest.mark.parametrize(
    "kind,existing", [("import", False), ("publish", False), ("publish", True)]
)
async def test_stop_cancels_real_render(queue, repo, paths, make_tone, monkeypatch, kind, existing):
    if existing:
        sound = await imported(queue, repo, paths, make_tone)
    else:
        sound = add_sound(repo, paths, make_tone(name="cancel.wav", seconds=3))
    repo.set_recipe(sound.id, Recipe(gain_db=1))
    executable = shutil.which("ffmpeg")
    wrapper = paths.data_dir / "ffmpeg-realtime"
    wrapper.write_text(
        "#!/usr/bin/env python3\nimport os, sys\n"
        f"ffmpeg = {executable!r}\nargs = sys.argv[1:]\nindex = args.index('-i')\n"
        "os.execv(ffmpeg, [ffmpeg, *args[:index], '-re', *args[index:]])\n"
    )
    wrapper.chmod(0o755)
    monkeypatch.setattr(media, "FFMPEG", str(wrapper))
    started = asyncio.Event()
    processes = []
    create = asyncio.create_subprocess_exec

    async def observe(*args, **kwargs):
        process = await create(*args, **kwargs)
        if args[0] == str(wrapper):
            processes.append(process)
            started.set()
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", observe)
    job = queue.enqueue_import(sound.id) if kind == "import" else queue.enqueue_publish(sound.id)
    await asyncio.wait_for(started.wait(), 5)
    await queue.stop()
    await queue.wait_idle()
    assert job.status == "failed" and job.error == "cancelled"
    stored = repo.get_sound(sound.id)
    assert stored.status == ("ready" if existing else "failed")
    assert stored.published == sound.published
    if existing:
        assert (paths.publish_dir / sound.published.filename).exists()
    assert all(process.returncode is not None for process in processes)
    assert not list(paths.publish_dir.glob(".tmp-*"))


async def test_notifier_debounce_and_thread_safety():
    seen = []

    async def send(revision):
        seen.append(revision)

    notifier = CatalogNotifier(send, delay=0.01)
    try:
        notifier.mark_changed(1)
        notifier.mark_changed(2)
        await asyncio.to_thread(notifier.mark_changed, 3)
        await notifier.flush()
        assert seen == [3]
    finally:
        await notifier.close()


async def test_notifier_send_failure_and_close(caplog):
    seen = []

    async def send(revision):
        seen.append(revision)
        if revision == 1:
            raise RuntimeError("offline")

    notifier = CatalogNotifier(send, delay=0.01)
    notifier.mark_changed(1)
    await notifier.flush()
    assert "offline" in caplog.text
    notifier.mark_changed(2)
    await notifier.flush()
    assert seen == [1, 2]
    notifier.mark_changed(3)
    await notifier.close()
    notifier.mark_changed(4)
    await notifier.flush()
    assert seen == [1, 2]


async def test_running_publish_is_not_coalesced_and_jobs_stay_fifo(
    queue,
    repo,
    paths,
    make_tone,
    monkeypatch,
):
    sound = await imported(queue, repo, paths, make_tone)
    repo.set_recipe(sound.id, Recipe(gain_db=1))
    entered, release = asyncio.Event(), asyncio.Event()
    render = media.render

    async def paused_render(*args, **kwargs):
        entered.set()
        await release.wait()
        await render(*args, **kwargs)

    monkeypatch.setattr(media, "render", paused_render)
    running = queue.enqueue_publish(sound.id)
    await asyncio.wait_for(entered.wait(), 5)
    replaced = queue.enqueue_publish(sound.id)
    recipe = Recipe(trim_end=1)
    preview = queue.enqueue_preview(sound.id, recipe)
    recipe.trim_end = 1.5
    latest = queue.enqueue_publish(sound.id)
    assert [job.id for job in queue.list_jobs()[:3]] == [running.id, latest.id, preview.id]
    assert running.status == "running" and latest.status == "queued"
    assert replaced.id not in {job.id for job in queue.list_jobs()}
    release.set()
    await queue.wait_idle()
    assert repo.get_sound(sound.id).published.revision == 3
    assert [job.id for job in queue.list_jobs()[:3]] == [preview.id, latest.id, running.id]
    info = await media.probe(paths.previews_dir / f"{sound.id}.mp3")
    assert info.duration == pytest.approx(1, abs=0.06)


async def test_finished_history_is_bounded(queue, repo, paths, make_tone):
    sound = await imported(queue, repo, paths, make_tone)
    jobs = [queue.enqueue_preview(sound.id, Recipe(trim_start=10)) for _ in range(55)]
    assert len(queue.list_jobs()) == 56
    await queue.wait_idle()
    assert [job.id for job in queue.list_jobs()] == [job.id for job in reversed(jobs[-50:])]
    assert all(job.status == "failed" for job in queue.list_jobs())


async def test_stop_settles_queued_jobs(repo, publisher, paths, make_tone):
    sound = add_sound(repo, paths, make_tone(seconds=1))
    queue = JobQueue(repo, publisher, paths)
    job = queue.enqueue_import(sound.id)
    await queue.stop()
    await queue.wait_idle()
    assert job.status == "failed" and job.error == "cancelled"
    assert repo.get_sound(sound.id).status == "failed"
    await queue.start()
    try:
        retry = queue.enqueue_import(sound.id)
        await queue.wait_idle()
        assert retry.status == "done"
    finally:
        await queue.stop()


async def test_cancel_after_commit_removes_unrecorded_revision(
    queue,
    repo,
    paths,
    make_tone,
    monkeypatch,
):
    sound = await imported(queue, repo, paths, make_tone)
    old = paths.publish_dir / sound.published.filename
    previous = old.read_bytes()
    entered = asyncio.Event()

    async def paused_measure(_path):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(media, "measure_loudness", paused_measure)
    job = queue.enqueue_publish(sound.id)
    await asyncio.wait_for(entered.wait(), 5)
    assert (paths.publish_dir / f"{sound.id}-r2.mp3").exists()
    await queue.stop()
    assert job.status == "failed" and job.error == "cancelled"
    assert repo.get_sound(sound.id).published == sound.published
    assert repo.get_sound(sound.id).status == "ready" and old.read_bytes() == previous
    assert not (paths.publish_dir / f"{sound.id}-r2.mp3").exists()


async def test_unexpected_exception_is_truncated_and_worker_survives(
    queue,
    repo,
    paths,
    make_tone,
    monkeypatch,
):
    sound = add_sound(repo, paths, make_tone(seconds=1))
    probe = media.probe
    count = 0

    async def fail_once(path, **kwargs):
        nonlocal count
        count += 1
        if count == 1:
            raise RuntimeError("x" * 1000 + "tail")
        return await probe(path, **kwargs)

    monkeypatch.setattr(media, "probe", fail_once)
    first = queue.enqueue_import(sound.id)
    retry = queue.enqueue_import(sound.id)
    await queue.wait_idle()
    assert first.status == "failed" and first.error == "x" * 396 + "tail"
    assert retry.status == "done" and repo.get_sound(sound.id).error is None


async def test_notifier_marks_during_send_and_ignores_older_revisions():
    seen = []
    entered, release = asyncio.Event(), asyncio.Event()

    async def send(revision):
        seen.append(revision)
        if revision == 1:
            entered.set()
            await release.wait()

    notifier = CatalogNotifier(send, delay=0.001)
    try:
        notifier.mark_changed(1)
        await asyncio.wait_for(entered.wait(), 5)
        await asyncio.to_thread(notifier.mark_changed, 3)
        notifier.mark_changed(2)
        release.set()
        await notifier.flush()
        assert seen == [1, 3]
    finally:
        await notifier.close()
