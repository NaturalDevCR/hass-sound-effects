"""Ingress sounds workflow with real ffmpeg and recorded Supervisor services."""

from __future__ import annotations

import asyncio
import shutil
import threading

import httpx
import pytest
from fastapi.testclient import TestClient

from sound_effects_studio import media
from sound_effects_studio.app import create_app
from sound_effects_studio.auth import INGRESS_PEER
from sound_effects_studio.models import AuditionTarget, CategoryUpdate, Recipe, Settings
from sound_effects_studio.supervisor import SupervisorClient, SupervisorError

pytestmark = pytest.mark.studio
CHUNK_SIZE = 4194304
PLACEMENT = {"category_id": "general", "seasons": ["regular"], "all_seasons": False, "tags": []}


@pytest.fixture
async def ui(paths):
    app = create_app(paths, start_background=False)
    await app.state.jobs.start()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=(INGRESS_PEER, 50000)),
        base_url="http://studio",
    ) as client:
        yield app, client
    await app.state.jobs.stop()
    app.state.db.close()


async def upload(client, source, placement=None):
    data = source.read_bytes()
    response = await client.post(
        "/api/ui/uploads", json={"filename": source.name, "size": len(data)}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["chunk_size"] == CHUNK_SIZE
    for index in reversed(range((len(data) + CHUNK_SIZE - 1) // CHUNK_SIZE)):
        response = await client.put(
            f"/api/ui/uploads/{body['upload_id']}/chunks/{index}",
            content=data[index * CHUNK_SIZE : (index + 1) * CHUNK_SIZE],
        )
        assert response.status_code == 200
    return await client.post(
        f"/api/ui/uploads/{body['upload_id']}/complete", json=placement or PLACEMENT
    )


async def ready(ui, make_tone):
    app, client = ui
    response = await upload(client, make_tone(seconds=2))
    assert response.status_code == 200
    sound = response.json()
    assert sound["status"] == "processing"
    await app.state.jobs.wait_idle()
    return (await client.get(f"/api/ui/sounds/{sound['id']}")).json()


async def test_three_chunk_upload_lifecycle(ui, make_tone, paths):
    app, client = ui
    source = make_tone(name="door-bell_tone.wav", seconds=50)
    assert 2 * CHUNK_SIZE < source.stat().st_size < 3 * CHUNK_SIZE
    response = await upload(client, source)
    sound = response.json()
    assert sound["status"] == "processing" and sound["title"] == "door bell tone"
    assert sound["key"] == source.name
    assert (paths.originals_dir / sound["id"] / source.name).read_bytes() == source.read_bytes()
    await app.state.jobs.wait_idle()
    stored = (await client.get(f"/api/ui/sounds/{sound['id']}")).json()
    assert stored["status"] == "ready" and stored["original"]["duration"] == pytest.approx(50)
    assert (await client.get("/api/ui/sounds")).json() == [stored]
    assert (await client.get("/api/ui/jobs")).json()[0]["status"] == "done"


async def test_upload_errors_and_dynamic_limit(ui):
    app, client = ui
    for payload, status in [
        ({"filename": "bad.exe", "size": 1}, 415),
        ({"filename": "tone.wav", "size": 101 * 1024 * 1024}, 413),
        ({"filename": "tone.wav", "size": 0}, 422),
    ]:
        response = await client.post("/api/ui/uploads", json=payload)
        assert response.status_code == status and isinstance(response.json()["detail"], str)
    app.state.repo.update_settings(Settings(max_upload_mb=1))
    assert (
        await client.post(
            "/api/ui/uploads",
            json={
                "filename": "tone.wav",
                "size": 2 * 1024 * 1024,
            },
        )
    ).status_code == 413
    body = (await client.post("/api/ui/uploads", json={"filename": "tone.wav", "size": 3})).json()
    endpoint = f"/api/ui/uploads/{body['upload_id']}"
    assert (
        await client.put(endpoint + "/chunks/0", content=b"x" * (CHUNK_SIZE + 1))
    ).status_code == 413
    assert (await client.put(endpoint + "/chunks/0", content=b"1234")).status_code == 413
    assert (await client.put(endpoint + "/chunks/-1", content=b"x")).status_code == 422
    assert (await client.post(endpoint + "/complete", json=PLACEMENT)).status_code == 422
    assert app.state.repo.list_sounds() == []
    assert (await client.put("/api/ui/uploads/unknown/chunks/0", content=b"x")).status_code == 404
    assert (
        await client.post("/api/ui/uploads/unknown/complete", json=PLACEMENT)
    ).status_code == 404


@pytest.mark.parametrize("profile,expected", [("absent", "soft"), (None, None), ("loud", "loud")])
@pytest.mark.parametrize("method", ["upload", "import"])
async def test_profile_presence_defaults(ui, make_tone, paths, profile, expected, method):
    app, client = ui
    app.state.repo.update_category("general", CategoryUpdate(default_profile_id="soft"))
    placement = dict(PLACEMENT)
    if profile != "absent":
        placement["profile_id"] = profile
    source = make_tone(seconds=0.5)
    if method == "upload":
        response = await upload(client, source, placement)
        sound = response.json()
    else:
        shutil.copyfile(source, paths.import_roots["media"] / source.name)
        response = await client.post(
            "/api/ui/import", json={**placement, "paths": ["media/tone.wav"]}
        )
        sound = response.json()["sounds"][0]
    assert response.status_code == 200 and sound["recipe"]["profile_id"] == expected
    await app.state.jobs.wait_idle()
    assert app.state.repo.get_sound(sound["id"]).status == "ready"


async def test_invalid_placement_can_retry_upload(ui, make_tone):
    app, client = ui
    source = make_tone(seconds=0.5)
    assert (await upload(client, source, {**PLACEMENT, "profile_id": "unknown"})).status_code == 422
    assert app.state.repo.list_sounds() == []
    upload_id = next(app.state.paths.uploads_dir.iterdir()).stem
    assert (
        await client.post(f"/api/ui/uploads/{upload_id}/complete", json=PLACEMENT)
    ).status_code == 200
    await app.state.jobs.wait_idle()


async def test_import_copy_order_skips_and_boundaries(ui, make_tone, paths, tmp_path):
    app, client = ui
    for name in ("one.wav", "two.mp3"):
        shutil.copyfile(make_tone(name=name, seconds=0.5), paths.import_roots["media"] / name)
    (paths.import_roots["media"] / "notes.txt").write_text("notes")
    assert (await client.get("/api/ui/import/browse")).json()["roots"] == [
        "config/www",
        "media",
        "share",
    ]
    for path in ("media/../../etc", "unknown"):
        assert (await client.get("/api/ui/import/browse", params={"path": path})).status_code == 422
        assert (
            await client.post("/api/ui/import", json={**PLACEMENT, "paths": [path]})
        ).status_code == 422
    (paths.import_roots["media"] / "escape").symlink_to(tmp_path, target_is_directory=True)
    assert (
        await client.get("/api/ui/import/browse", params={"path": "media/escape"})
    ).status_code == 422
    sources = ["media/two.mp3", "media/notes.txt", "media/one.wav"]
    before = [(paths.import_roots["media"] / name).read_bytes() for name in ("two.mp3", "one.wav")]
    assert (
        await client.post(
            "/api/ui/import",
            json={
                **PLACEMENT,
                "paths": sources,
                "profile_id": "missing",
            },
        )
    ).status_code == 422
    assert app.state.repo.list_sounds() == []
    response = await client.post("/api/ui/import", json={**PLACEMENT, "paths": sources})
    sounds = response.json()["sounds"]
    assert [sound["key"] for sound in sounds] == ["two.mp3", "one.wav"]
    await app.state.jobs.wait_idle()
    for sound, data in zip(sounds, before, strict=True):
        assert app.state.repo.get_sound(sound["id"]).status == "ready"
        assert (paths.import_roots["media"] / sound["key"]).read_bytes() == data
        assert (paths.originals_dir / sound["id"] / sound["key"]).read_bytes() == data


async def test_metadata_recipes_preview_streams_and_jobs(ui, make_tone, paths):
    app, client = ui
    sound = await ready(ui, make_tone)
    url = f"/api/ui/sounds/{sound['id']}"
    response = await client.patch(
        url,
        json={
            "title": "New title",
            "key": "new",
            "tags": ["Bell"],
            "enabled": False,
            "notes": "note",
            "all_seasons": True,
        },
    )
    assert response.status_code == 200 and response.json()["title"] == "New title"
    assert response.json()["tags"] == ["bell"]
    old = app.state.repo.get_sound(sound["id"])
    for recipe in ({"trim_start": 20}, {"fade_in": 3}, {"profile_id": "missing"}, {"gain_db": 30}):
        assert (await client.put(url + "/recipe", json=recipe)).status_code == 422
        assert (await client.post(url + "/preview", json=recipe)).status_code == 422
    assert app.state.repo.get_sound(sound["id"]).recipe == old.recipe
    result = (await client.put(url + "/recipe", json={"trim_end": 1})).json()
    assert result["sound"]["recipe"]["trim_end"] == 1 and result["job"]["kind"] == "publish"
    await app.state.jobs.wait_idle()
    current = app.state.repo.get_sound(sound["id"])
    assert current.published.revision == 2
    result = (await client.post(url + "/preview", json={"gain_db": 2})).json()
    assert result["job"]["kind"] == "preview"
    await app.state.jobs.wait_idle()
    assert app.state.repo.get_sound(sound["id"]).has_preview
    assert app.state.repo.get_sound(sound["id"]).recipe.trim_end == 1
    for kind, file in [
        ("published", paths.publish_dir / current.published.filename),
        ("preview", paths.previews_dir / f"{sound['id']}.mp3"),
        ("original", paths.originals_dir / sound["id"] / "tone.wav"),
    ]:
        response = await client.get(url + "/" + kind)
        assert response.content == file.read_bytes()
        if kind != "published":
            assert response.headers["cache-control"] == "no-store"
        ranged = await client.get(url + "/" + kind, headers={"Range": "bytes=0-99"})
        assert ranged.status_code == 206 and ranged.content == file.read_bytes()[:100]
    jobs = (await client.get("/api/ui/jobs")).json()
    assert [job["kind"] for job in jobs] == ["preview", "publish", "import"]


async def test_bulk_atomic_profiles_tags_and_delete(ui, make_tone, paths):
    app, client = ui
    first = await ready(ui, make_tone)
    second = await ready(ui, make_tone)
    ids = [first["id"], second["id"], first["id"]]
    endpoint = "/api/ui/sounds/bulk"
    assert (
        await client.post(endpoint, json={"ids": ids, "set": {"add_tags": ["a", "b"]}})
    ).json() == {
        "updated": 2,
        "queued": 0,
    }
    assert (
        await client.post(endpoint, json={"ids": ids, "set": {"remove_tags": ["a"]}})
    ).status_code == 200
    for sound_id in ids:
        assert app.state.repo.get_sound(sound_id).tags == ["b"]
    snapshot = app.state.repo.list_sounds()
    assert (
        await client.post(
            endpoint,
            json={
                "ids": [first["id"], "missing"],
                "set": {"profile_id": "soft", "enabled": False},
            },
        )
    ).status_code == 404
    assert (
        await client.post(
            endpoint,
            json={
                "ids": ids,
                "set": {"profile_id": "missing", "enabled": False},
            },
        )
    ).status_code == 422
    assert app.state.repo.list_sounds() == snapshot
    for profile in ("soft", None):
        assert (
            await client.post(endpoint, json={"ids": ids, "set": {"profile_id": profile}})
        ).json() == {
            "updated": 2,
            "queued": 2,
        }
        await app.state.jobs.wait_idle()
        assert all(app.state.repo.get_sound(i).recipe.profile_id == profile for i in ids)
    assert (
        await client.post("/api/ui/sounds/bulk-delete", json={"ids": [first["id"], "missing"]})
    ).status_code == 404
    assert len(app.state.repo.list_sounds()) == 2
    publications = {p.name for p in paths.publish_dir.glob("*.mp3")}
    assert (await client.post("/api/ui/sounds/bulk-delete", json={"ids": ids})).json() == {
        "deleted": 2
    }
    assert app.state.repo.list_sounds() == []
    assert not list(paths.originals_dir.iterdir())
    assert {p.name for p in paths.publish_dir.glob("*.mp3")} == publications
    assert app.state.db.connection.execute("SELECT COUNT(*) FROM retired_files").fetchone()[
        0
    ] == len(publications)


class FakeSupervisor(SupervisorClient):
    def __init__(self):
        super().__init__("fake")
        self.calls = []
        self.error = None

    async def call_service(self, domain, service, data):
        if self.error:
            raise SupervisorError(self.error)
        self.calls.append((domain, service, data))


async def test_audition_payloads_preview_fallback_and_errors(ui, make_tone, paths):
    app, client = ui
    sound = await ready(ui, make_tone)
    url = f"/api/ui/sounds/{sound['id']}/audition"
    fake = FakeSupervisor()
    app.state.supervisor = fake
    app.state.repo.update_settings(
        Settings(
            audition_targets=[
                AuditionTarget(
                    id="speaker",
                    label="Speaker",
                    kind="media_player",
                    entity_id="media_player.room",
                ),
                AuditionTarget(
                    id="script", label="Script", kind="script", entity_id="script.play", volume=0.4
                ),
            ]
        )
    )
    assert (
        await client.post(url, json={"target_id": "unknown", "use_preview": False})
    ).status_code == 404
    response = await client.post(url, json={"target_id": "speaker", "use_preview": False})
    assert response.status_code == 422 and response.json()["detail"] == "media base URL unknown"
    app.state.media_base_url_effective = "http://ha:8123/"
    payload = {"target_id": "speaker", "use_preview": True}
    response = (await client.post(url, json=payload)).json()
    assert response["ok"] is True and response["url"].startswith("http://ha:8123/local/")
    assert fake.calls[-1] == (
        "media_player",
        "play_media",
        {
            "entity_id": "media_player.room",
            "media_content_id": response["url"],
            "media_content_type": "music",
            "announce": True,
        },
    )
    published = paths.publish_dir / sound["published"]["filename"]
    audition = paths.www_dir / response["url"].split("/local/")[1]
    assert audition.read_bytes() == published.read_bytes()
    preview = paths.previews_dir / f"{sound['id']}.mp3"
    shutil.copyfile(make_tone(name="preview.mp3", seconds=0.5), preview)
    preview_duration = (await media.probe(preview)).duration
    assert preview_duration != pytest.approx(sound["published"]["duration"])
    response = (await client.post(url, json={"target_id": "script", "use_preview": True})).json()
    assert fake.calls[-1] == (
        "script",
        "turn_on",
        {
            "entity_id": "script.play",
            "variables": {
                "url": response["url"],
                "duration": preview_duration,
                "title": sound["title"],
                "volume": 0.4,
            },
        },
    )
    assert (
        paths.www_dir / response["url"].split("/local/")[1]
    ).read_bytes() == preview.read_bytes()
    stored = app.state.repo.get_sound(sound["id"])
    assert stored.selection_count == 0 and stored.last_selected_at is None
    fake.error = "speaker offline"
    response = await client.post(url, json=payload)
    assert response.status_code == 502 and response.json()["detail"] == "speaker offline"
    app.state.supervisor = SupervisorClient(None)
    assert (await client.post(url, json=payload)).status_code == 503
    assert (await client.delete(f"/api/ui/sounds/{sound['id']}")).status_code == 204
    assert not list((paths.publish_dir / "_audition").iterdir()) and not preview.exists()


async def test_processing_and_missing_resources(ui):
    app, client = ui
    sound = app.state.repo.create_sound(
        title="Pending", key="pending.wav", recipe=Recipe(), original=None, **PLACEMENT
    )
    url = f"/api/ui/sounds/{sound.id}"
    for method, suffix in [("put", "/recipe"), ("post", "/preview")]:
        response = await getattr(client, method)(url + suffix, json={})
        assert (
            response.status_code == 422 and response.json()["detail"] == "sound is still processing"
        )
    for kind in ("original", "preview", "published"):
        assert (await client.get(url + "/" + kind)).status_code == 404
        assert (await client.get("/api/ui/sounds/missing/" + kind)).status_code == 404
    assert (await client.get("/api/ui/sounds/missing")).status_code == 404
    assert (await client.patch("/api/ui/sounds/missing", json={"title": "x"})).status_code == 404
    assert (await client.delete("/api/ui/sounds/missing")).status_code == 404
    assert (
        await client.post("/api/ui/sounds/bulk", json={"ids": [sound.id], "set": {"bad": True}})
    ).status_code == 422


def test_ingress_and_lifespan(paths, make_tone):
    app = create_app(paths)
    with TestClient(app, client=(INGRESS_PEER, 50000)) as client:
        source = make_tone(seconds=0.5)
        body = client.post(
            "/api/ui/uploads", json={"filename": source.name, "size": source.stat().st_size}
        ).json()
        client.put(f"/api/ui/uploads/{body['upload_id']}/chunks/0", content=source.read_bytes())
        sound = client.post(f"/api/ui/uploads/{body['upload_id']}/complete", json=PLACEMENT).json()
        client.portal.call(app.state.jobs.wait_idle)
        assert client.get(f"/api/ui/sounds/{sound['id']}").json()["status"] == "ready"
        denied = TestClient(app, client=("192.168.1.2", 50000))
        assert denied.get("/api/ui/sounds").status_code == 403


async def test_upload_missing_middle_chunk_and_custom_title(ui, make_tone):
    app, client = ui
    data = make_tone(name="bell.MP3", seconds=0.5).read_bytes()
    body = (
        await client.post(
            "/api/ui/uploads",
            json={
                "filename": "bell.MP3",
                "size": 2 * CHUNK_SIZE + len(data),
            },
        )
    ).json()
    url = f"/api/ui/uploads/{body['upload_id']}"
    await client.put(url + "/chunks/0", content=b"x" * CHUNK_SIZE)
    await client.put(url + "/chunks/2", content=data)
    assert (await client.post(url + "/complete", json=PLACEMENT)).status_code == 422
    assert app.state.repo.list_sounds() == []
    # A separate small upload exercises custom titles and lowercase stored extension.
    response = await upload(
        client,
        make_tone(name="bell.MP3", seconds=0.5),
        {
            **PLACEMENT,
            "title": "Custom bell",
        },
    )
    assert response.json()["title"] == "Custom bell"
    await app.state.jobs.wait_idle()
    sound = app.state.repo.get_sound(response.json()["id"])
    assert sound.original.filename == "bell.mp3" and sound.key == "bell.MP3"


async def test_bulk_validation_and_recipe_preservation(ui, make_tone):
    app, client = ui
    sound = await ready(ui, make_tone)
    app.state.repo.set_recipe(sound["id"], Recipe(trim_end=1, gain_db=2))
    before = app.state.repo.get_sound(sound["id"])
    response = await client.post(
        "/api/ui/sounds/bulk",
        json={
            "ids": [sound["id"]],
            "set": {"profile_id": "soft", "seasons": ["missing"]},
        },
    )
    assert response.status_code == 422 and app.state.repo.get_sound(sound["id"]) == before
    response = await client.post(
        "/api/ui/sounds/bulk",
        json={
            "ids": [sound["id"]],
            "set": {"profile_id": None},
        },
    )
    assert response.json() == {"updated": 1, "queued": 1}
    assert app.state.repo.get_sound(sound["id"]).recipe == before.recipe
    await app.state.jobs.wait_idle()
    assert (
        await client.post(
            "/api/ui/sounds/bulk",
            json={
                "ids": ["missing", sound["id"]],
                "set": {"enabled": False},
            },
        )
    ).json() == {"updated": 1, "queued": 0}


async def test_jobs_running_and_queued_first(ui, make_tone, monkeypatch):
    import asyncio

    from sound_effects_studio import media

    app, client = ui
    sound = await ready(ui, make_tone)
    entered, release = asyncio.Event(), asyncio.Event()
    render = media.render

    async def paused(*args, **kwargs):
        entered.set()
        await release.wait()
        await render(*args, **kwargs)

    monkeypatch.setattr(media, "render", paused)
    url = f"/api/ui/sounds/{sound['id']}"
    running = (await client.post(url + "/preview", json={"gain_db": 1})).json()["job"]
    await asyncio.wait_for(entered.wait(), 5)
    queued = (await client.put(url + "/recipe", json={"gain_db": 2})).json()["job"]
    try:
        jobs = (await client.get("/api/ui/jobs")).json()
        assert [job["id"] for job in jobs[:2]] == [running["id"], queued["id"]]
        assert [job["status"] for job in jobs] == ["running", "queued", "done"]
    finally:
        release.set()
    await app.state.jobs.wait_idle()
    assert (await client.get("/api/ui/jobs")).json()[0]["id"] == queued["id"]


async def test_audition_without_audio_and_missing_current_revision(ui, make_tone, paths):
    app, client = ui
    sound = await ready(ui, make_tone)
    app.state.repo.update_settings(
        Settings(
            audition_targets=[
                AuditionTarget(
                    id="speaker",
                    label="Speaker",
                    kind="media_player",
                    entity_id="media_player.room",
                )
            ]
        )
    )
    app.state.supervisor = FakeSupervisor()
    app.state.media_base_url_effective = "http://ha:8123"
    url = f"/api/ui/sounds/{sound['id']}"
    (paths.publish_dir / sound["published"]["filename"]).unlink()
    assert (await client.get(url + "/published")).status_code == 404
    assert (
        await client.post(
            url + "/audition",
            json={
                "target_id": "speaker",
                "use_preview": True,
            },
        )
    ).status_code == 404
    preview = paths.previews_dir / f"{sound['id']}.mp3"
    preview.write_bytes(b"preview")
    assert (
        await client.post(
            url + "/audition",
            json={
                "target_id": "speaker",
                "use_preview": True,
            },
        )
    ).status_code == 200
    assert (
        await client.post(
            url + "/audition",
            json={
                "target_id": "speaker",
                "use_preview": False,
            },
        )
    ).status_code == 404


async def test_import_copy_off_loop_and_cancellation_cleanup(ui, make_tone, paths, monkeypatch):
    import asyncio
    import threading

    app, client = ui
    shutil.copyfile(make_tone(seconds=0.5), paths.import_roots["media"] / "tone.wav")
    entered = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    copyfile = shutil.copyfile

    def paused_copy(src, dst):
        loop.call_soon_threadsafe(entered.set)
        assert release.wait(5)
        return copyfile(src, dst)

    monkeypatch.setattr(shutil, "copyfile", paused_copy)
    request = asyncio.create_task(
        client.post(
            "/api/ui/import",
            json={
                **PLACEMENT,
                "paths": ["media/tone.wav"],
            },
        )
    )
    try:
        await asyncio.wait_for(entered.wait(), 5)
        request.cancel()
        await asyncio.sleep(0)
        assert not request.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await request
        assert app.state.repo.list_sounds() == []
        assert not list(paths.originals_dir.iterdir())
    finally:
        release.set()
        await asyncio.gather(request, return_exceptions=True)


async def test_import_preserves_selected_symlink_filename(ui, make_tone, paths):
    app, client = ui
    media = paths.import_roots["media"]
    source = make_tone(seconds=0.5)
    shutil.copyfile(source, media / "target.txt")
    shutil.copyfile(source, media / "target.wav")
    (media / "chosen.WAV").symlink_to(media / "target.txt")
    (media / "unsupported.txt").symlink_to(media / "target.wav")
    response = await client.post(
        "/api/ui/import",
        json={
            **PLACEMENT,
            "paths": ["media/chosen.WAV", "media/unsupported.txt"],
        },
    )
    sounds = response.json()["sounds"]
    assert [sound["key"] for sound in sounds] == ["chosen.WAV"]
    await app.state.jobs.wait_idle()
    stored = app.state.repo.get_sound(sounds[0]["id"])
    assert stored.status == "ready" and stored.original.filename == "chosen.wav"


@pytest.mark.parametrize("size", [3, CHUNK_SIZE + 2])
async def test_chunk_stream_limits_before_storage(ui, size):
    app, client = ui
    body = (
        await client.post("/api/ui/uploads", json={"filename": "tone.wav", "size": size})
    ).json()
    url = f"/api/ui/uploads/{body['upload_id']}/chunks/0"
    consumed = []

    async def oversized():
        for chunk in (b"x" * min(size, CHUNK_SIZE), b"x", b"never read"):
            consumed.append(len(chunk))
            yield chunk

    response = await client.put(url, content=oversized())
    assert response.status_code == 413
    assert len(consumed) == 2
    assert next(app.state.paths.uploads_dir.iterdir()).read_bytes() == bytes(size)
    assert (
        await client.post(url.rsplit("/chunks", 1)[0] + "/complete", json=PLACEMENT)
    ).status_code == 422
    consumed.clear()
    response = await client.put(
        url, content=oversized(), headers={"Content-Length": str(CHUNK_SIZE + 1)}
    )
    assert response.status_code == 413 and consumed == []
    response = await client.put("/api/ui/uploads/missing/chunks/0", content=oversized())
    assert response.status_code == 404 and consumed == []


async def test_upload_session_cap(ui):
    app, client = ui
    for _ in range(20):
        assert (
            await client.post("/api/ui/uploads", json={"filename": "tone.wav", "size": 1})
        ).status_code == 200
    response = await client.post("/api/ui/uploads", json={"filename": "tone.wav", "size": 1})
    assert response.status_code in (422, 429) and response.json()["detail"]
    assert len(list(app.state.paths.uploads_dir.iterdir())) == 20


@pytest.mark.parametrize("missing", ["missing.wav", "missing.txt"])
async def test_import_missing_path_creates_nothing(ui, paths, make_tone, missing):
    app, client = ui
    shutil.copyfile(make_tone(seconds=0.5), paths.import_roots["media"] / "tone.wav")
    response = await client.post(
        "/api/ui/import", json={**PLACEMENT, "paths": ["media/tone.wav", f"media/{missing}"]}
    )
    assert response.status_code == 404
    assert app.state.repo.list_sounds() == []
    assert list(paths.originals_dir.iterdir()) == []
    assert app.state.jobs.list_jobs() == []


@pytest.mark.parametrize("method", ["upload", "import"])
async def test_unknown_placement_category_is_422(ui, make_tone, paths, method):
    app, client = ui
    source = make_tone(seconds=0.5)
    placement = {**PLACEMENT, "category_id": "missing"}
    if method == "upload":
        response = await upload(client, source, placement)
    else:
        shutil.copyfile(source, paths.import_roots["media"] / source.name)
        response = await client.post(
            "/api/ui/import", json={**placement, "paths": ["media/tone.wav"]}
        )
    assert response.status_code == 422 and app.state.repo.list_sounds() == []
    assert list(paths.originals_dir.iterdir()) == []


@pytest.mark.parametrize(
    "filename,key,title",
    [
        ("../Folder/Big__Bell\x00.WAV", "Big__Bell.WAV", "Big Bell"),
        ("---___.WAV", "---___.WAV", "---___"),
        ("X" * 200 + ".WAV", "X" * 116 + ".WAV", "X" * 116),
    ],
)
async def test_upload_sanitized_key_and_default_title(ui, make_tone, filename, key, title):
    app, client = ui
    data = make_tone(seconds=0.5).read_bytes()
    body = (
        await client.post("/api/ui/uploads", json={"filename": filename, "size": len(data)})
    ).json()
    url = f"/api/ui/uploads/{body['upload_id']}"
    await client.put(url + "/chunks/0", content=data)
    response = await client.post(url + "/complete", json=PLACEMENT)
    assert response.status_code == 200
    assert response.json()["key"] == key and response.json()["title"] == title
    await app.state.jobs.wait_idle()


@pytest.mark.parametrize("operation", ["chunk", "browse"])
async def test_chunk_and_browse_run_off_event_loop(ui, monkeypatch, operation):
    from sound_effects_studio.importer import ImportBrowser
    from sound_effects_studio.uploads import UploadStore

    _, client = ui
    entered = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    cls, name = (UploadStore, "write_chunk") if operation == "chunk" else (ImportBrowser, "browse")
    original = getattr(cls, name)

    def paused(*args):
        loop.call_soon_threadsafe(entered.set)
        assert release.wait(5)
        return original(*args)

    monkeypatch.setattr(cls, name, paused)
    if operation == "chunk":
        body = (
            await client.post("/api/ui/uploads", json={"filename": "tone.wav", "size": 1})
        ).json()
        request = asyncio.create_task(
            client.put(f"/api/ui/uploads/{body['upload_id']}/chunks/0", content=b"x")
        )
    else:
        request = asyncio.create_task(client.get("/api/ui/import/browse"))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        assert not request.done()
        release.set()
        assert (await request).status_code == 200
    finally:
        release.set()
        await asyncio.gather(request, return_exceptions=True)


async def test_script_audition_probe_error_falls_back(ui, make_tone, paths, monkeypatch):
    app, client = ui
    sound = await ready(ui, make_tone)
    app.state.supervisor = FakeSupervisor()
    app.state.media_base_url_effective = "http://ha:8123"
    app.state.repo.update_settings(
        Settings(
            audition_targets=[
                AuditionTarget(id="script", label="Script", kind="script", entity_id="script.play")
            ]
        )
    )
    preview = paths.previews_dir / f"{sound['id']}.mp3"
    preview.write_bytes(b"invalid preview")

    async def fail_probe(file):
        assert file == preview
        raise media.MediaError("invalid audio")

    monkeypatch.setattr(media, "probe", fail_probe)
    response = await client.post(
        f"/api/ui/sounds/{sound['id']}/audition", json={"target_id": "script", "use_preview": True}
    )
    assert response.status_code == 200
    assert (
        app.state.supervisor.calls[-1][2]["variables"]["duration"] == sound["published"]["duration"]
    )


async def test_unsupported_upload_is_extension_error(ui):
    app, client = ui
    response = await client.post("/api/ui/uploads", json={"filename": "bad.EXE", "size": 1})
    assert response.status_code == 415
    assert "extension" in response.json()["detail"].lower()
    assert list(app.state.paths.uploads_dir.iterdir()) == []


async def test_import_sanitizes_key_preserving_case(ui, paths, make_tone):
    app, client = ui
    source = paths.import_roots["media"] / "Big__Bell\x01.WAV"
    shutil.copyfile(make_tone(seconds=0.5), source)
    response = await client.post(
        "/api/ui/import", json={**PLACEMENT, "paths": ["media/" + source.name]}
    )
    assert response.status_code == 200
    sound = response.json()["sounds"][0]
    assert sound["key"] == "Big__Bell.WAV" and sound["title"] == "Big Bell"
    assert (paths.originals_dir / sound["id"] / "Big__Bell.wav").is_file()
    await app.state.jobs.wait_idle()


async def test_complete_off_loop_cancellation_cleanup(ui, make_tone, monkeypatch):
    from sound_effects_studio.uploads import UploadStore

    app, client = ui
    data = make_tone(seconds=0.5).read_bytes()
    body = (
        await client.post("/api/ui/uploads", json={"filename": "tone.wav", "size": len(data)})
    ).json()
    url = f"/api/ui/uploads/{body['upload_id']}"
    assert (await client.put(url + "/chunks/0", content=data)).status_code == 200
    entered = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    finish = UploadStore.finish

    def paused_finish(*args):
        loop.call_soon_threadsafe(entered.set)
        assert release.wait(5)
        return finish(*args)

    monkeypatch.setattr(UploadStore, "finish", paused_finish)
    request = asyncio.create_task(client.post(url + "/complete", json=PLACEMENT))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        request.cancel()
        await asyncio.sleep(0)
        assert not request.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await request
        assert app.state.repo.list_sounds() == []
        assert list(app.state.paths.originals_dir.iterdir()) == []
        assert app.state.jobs.list_jobs() == []
    finally:
        release.set()
        await asyncio.gather(request, return_exceptions=True)
