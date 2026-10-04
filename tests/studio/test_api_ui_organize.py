"""Ingress API for Studio state, settings, organization and profiles."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sound_effects_studio.app import create_app
from sound_effects_studio.config import Paths
from sound_effects_studio.models import CategoryUpdate, Recipe, Sound, SoundUpdate
from sound_effects_studio.repository import Repository

pytestmark = pytest.mark.studio


@pytest.fixture
def app(paths: Paths) -> Iterator[FastAPI]:
    application = create_app(paths, start_background=False)
    yield application
    application.state.db.close()


@pytest.fixture
def ingress(app: FastAPI) -> TestClient:
    from sound_effects_studio.auth import INGRESS_PEER

    return TestClient(app, client=(INGRESS_PEER, 50000))


@pytest.fixture
def repo(app: FastAPI) -> Repository:
    return app.state.repo


def make_sound(repo: Repository, *, category_id: str = "general", title: str = "Door") -> Sound:
    return repo.create_sound(
        category_id=category_id,
        title=title,
        key=title.lower(),
        tags=[],
        seasons=["regular"],
        all_seasons=False,
        recipe=Recipe(gain_db=2),
        original=None,
    )


def test_state_and_token(ingress: TestClient, app: FastAPI):
    token = app.state.tokens.get()
    body = ingress.get("/api/ui/state").json()
    assert body == {
        "version": app.version,
        "api_token_masked": app.state.tokens.masked(),
        "catalog_revision": app.state.repo.catalog_revision(),
        "discovery": app.state.discovery_status,
        "www": {"exists": True, "served": None, "created_by_app": False},
        "media_base_url_effective": "",
        "hostname": None,
        "storage": app.state.publisher.storage_usage(),
        "settings": app.state.repo.get_settings().model_dump(),
    }
    assert body["api_token_masked"] != token
    assert ingress.get("/api/ui/token").json() == {"token": token}


def test_token_rotate_schedules_discovery(ingress: TestClient, app: FastAPI, monkeypatch):
    from sound_effects_studio import api_ui_organize

    calls: list[FastAPI] = []

    async def publish(application: FastAPI) -> None:
        calls.append(application)

    monkeypatch.setattr(api_ui_organize, "publish_discovery", publish)
    app.state.supervisor = type("AvailableSupervisor", (), {"available": True})()
    old = app.state.tokens.get()
    response = ingress.post("/api/ui/token/rotate")
    assert response.status_code == 200
    assert app.state.tokens.get() != old
    assert response.json() == {"api_token_masked": app.state.tokens.masked()}
    assert calls == [app]


def test_token_rotate_without_supervisor_does_not_schedule_discovery(
    ingress: TestClient, app: FastAPI, monkeypatch
):
    from sound_effects_studio import api_ui_organize

    calls: list[FastAPI] = []

    async def publish(application: FastAPI) -> None:
        calls.append(application)

    monkeypatch.setattr(api_ui_organize, "publish_discovery", publish)
    assert ingress.post("/api/ui/token/rotate").status_code == 200
    assert calls == []


def test_ui_router_rejects_non_ingress_peer(app: FastAPI):
    denied = TestClient(app, client=("192.168.1.20", 50000)).get("/api/ui/token")
    assert denied.status_code == 403
    assert isinstance(denied.json()["detail"], str)


async def test_discovery_publication_is_serialized(app: FastAPI):
    from sound_effects_studio.lifecycle import publish_discovery

    class ConcurrentSupervisor:
        available = True

        def __init__(self) -> None:
            self.next_id = 0
            self.deleted: list[str] = []

        async def self_info(self) -> dict[str, str]:
            await asyncio.sleep(0)
            return {"hostname": "studio"}

        async def publish_discovery(self, _config: dict[str, object]) -> str:
            await asyncio.sleep(0)
            self.next_id += 1
            return f"uuid-{self.next_id}"

        async def delete_discovery(self, uuid: str) -> None:
            await asyncio.sleep(0)
            self.deleted.append(uuid)

    supervisor = ConcurrentSupervisor()
    app.state.supervisor = supervisor

    await asyncio.gather(publish_discovery(app), publish_discovery(app))
    remembered = (app.state.paths.data_dir / "discovery_uuid").read_text(encoding="utf-8")
    assert remembered == '["uuid-2"]\n'
    assert supervisor.deleted == ["uuid-1"]


def test_settings_validation_and_media_url_recompute(
    ingress: TestClient, app: FastAPI, monkeypatch
):
    from sound_effects_studio import api_ui_organize

    base = ingress.get("/api/ui/settings").json()
    for targets in (
        [{"id": "x", "label": "X", "kind": "other", "entity_id": "other.x", "volume": None}],
        [
            {
                "id": "x",
                "label": "X",
                "kind": "script",
                "entity_id": "media_player.x",
                "volume": None,
            }
        ],
        [
            {"id": "x", "label": "X", "kind": "script", "entity_id": "script.x", "volume": 1.1},
        ],
        [
            {"id": "x", "label": "X", "kind": "script", "entity_id": "script.x", "volume": None},
            {"id": "x", "label": "Y", "kind": "script", "entity_id": "script.y", "volume": None},
        ],
        [
            {
                "id": "x",
                "label": "X",
                "kind": "media_player",
                "entity_id": "media_player.",
                "volume": None,
            }
        ],
        [{"id": " ", "label": "X", "kind": "script", "entity_id": "script.x", "volume": None}],
        [{"id": "x", "label": "  ", "kind": "script", "entity_id": "script.x", "volume": None}],
        [{"id": "x", "label": "X", "kind": "script", "entity_id": "script.x", "volume": -0.1}],
    ):
        response = ingress.put("/api/ui/settings", json={**base, "audition_targets": targets})
        assert response.status_code == 422
        assert isinstance(response.json()["detail"], str)
        assert ingress.get("/api/ui/settings").json() == base

    valid = {
        **base,
        "audition_targets": [
            {
                "id": "living_room",
                "label": "Living room",
                "kind": "media_player",
                "entity_id": "media_player.living_room",
                "volume": 0.4,
            },
            {
                "id": "announce",
                "label": "Announce",
                "kind": "script",
                "entity_id": "script.announce",
                "volume": None,
            },
        ],
    }
    assert ingress.put("/api/ui/settings", json=valid).json() == valid
    assert ingress.get("/api/ui/settings").json() == valid

    class AvailableSupervisor:
        available = True

    app.state.supervisor = AvailableSupervisor()
    result = ingress.put("/api/ui/settings", json={**base, "media_base_url": "http://x/"})
    assert result.status_code == 200
    assert app.state.media_base_url_effective == "http://x"

    detected: list[tuple[object, str]] = []

    async def detect(supervisor, configured: str) -> str:
        detected.append((supervisor, configured))
        return "http://auto.test"

    monkeypatch.setattr(api_ui_organize, "detect_media_base_url", detect)
    result = ingress.put("/api/ui/settings", json={**base, "media_base_url": "   "})
    assert result.status_code == 200
    assert app.state.media_base_url_effective == "http://auto.test"
    assert detected == [(app.state.supervisor, "   ")]


def test_category_crud_order_and_delete_conflict(ingress: TestClient, repo: Repository):
    assert ingress.get("/api/ui/categories").json()[0]["id"] == "general"
    created = ingress.post("/api/ui/categories", json={"name": "Door Sounds"})
    assert created.status_code == 200
    category = created.json()
    assert category["id"] == "door_sounds"
    assert [item["id"] for item in ingress.get("/api/ui/categories").json()] == [
        "general",
        "door_sounds",
    ]
    assert (
        ingress.post("/api/ui/categories", json={"name": "Duplicate", "id": "general"}).status_code
        == 409
    )
    updated = ingress.patch(f"/api/ui/categories/{category['id']}", json={"name": "Doors"})
    assert updated.json()["name"] == "Doors"
    assert updated.json()["id"] == "door_sounds"
    ordered = ingress.put("/api/ui/categories/order", json={"ids": ["door_sounds"]}).json()
    assert [item["id"] for item in ordered] == ["door_sounds", "general"]
    for ids in (["unknown"], ["door_sounds", "door_sounds"]):
        invalid = ingress.put("/api/ui/categories/order", json={"ids": ids})
        assert invalid.status_code == 422
        assert isinstance(invalid.json()["detail"], str)
    repo.create_sound(
        category_id="door_sounds",
        title="Door",
        key="door",
        tags=[],
        seasons=["regular"],
        all_seasons=False,
        recipe=Recipe(),
        original=None,
    )
    assert ingress.delete("/api/ui/categories/door_sounds").status_code == 409
    assert ingress.delete("/api/ui/categories/general").status_code == 204


def test_season_crud_resolve_and_regular_restrictions(ingress: TestClient, repo: Repository):
    assert ingress.get("/api/ui/seasons").json()[0]["id"] == "regular"
    halloween = ingress.post(
        "/api/ui/seasons",
        json={
            "name": "Halloween",
            "start": "10-01",
            "end": "10-31",
            "priority": 2,
        },
    )
    assert halloween.status_code == 200
    assert halloween.json()["id"] == "halloween"
    spring = ingress.post(
        "/api/ui/seasons",
        json={"name": "Spring", "start": "03-01", "end": "05-31", "priority": 7},
    )
    assert spring.status_code == 200
    assert [season["id"] for season in ingress.get("/api/ui/seasons").json()] == [
        "regular",
        "spring",
        "halloween",
    ]
    for invalid_date in ("13-40", "1-01"):
        invalid_create = ingress.post(
            "/api/ui/seasons",
            json={"name": "Bad", "start": invalid_date, "end": "10-31"},
        )
        assert invalid_create.status_code == 422
        invalid_patch = ingress.patch("/api/ui/seasons/halloween", json={"start": invalid_date})
        assert invalid_patch.status_code == 422
    assert (
        ingress.post(
            "/api/ui/seasons",
            json={"id": "halloween", "name": "Duplicate", "start": "10-01", "end": "10-31"},
        ).status_code
        == 409
    )
    assert ingress.patch("/api/ui/seasons/regular", json={"name": "All year"}).status_code == 200
    assert ingress.patch("/api/ui/seasons/regular", json={"priority": 5}).status_code == 422
    assert ingress.get("/api/ui/seasons/resolve?date=2026-10-15").json() == {
        "date": "2026-10-15",
        "season_id": "halloween",
    }
    for invalid in ("no", "2026-02-30", "10-15"):
        assert ingress.get(f"/api/ui/seasons/resolve?date={invalid}").status_code == 422
    assert ingress.delete("/api/ui/seasons/regular").status_code == 400
    sound = repo.create_sound(
        category_id="general",
        title="Seasonal",
        key="seasonal",
        tags=[],
        seasons=["halloween"],
        all_seasons=False,
        recipe=Recipe(),
        original=None,
    )
    assert ingress.delete("/api/ui/seasons/halloween").status_code == 204
    assert repo.get_sound(sound.id).seasons == ["regular"]


def test_profile_crud_patch_affected_apply_and_delete_conflicts(
    ingress: TestClient, repo: Repository, app: FastAPI
):
    one = make_sound(repo)
    second = make_sound(repo, title="Other")
    profile = ingress.post(
        "/api/ui/profiles",
        json={
            "name": "Cinema",
            "target_lufs": -18,
            "true_peak": -1.5,
            "lra": 10,
        },
    ).json()
    assert profile["id"] in {item["id"] for item in ingress.get("/api/ui/profiles").json()}
    patched = ingress.patch(f"/api/ui/profiles/{profile['id']}", json={"target_lufs": -17}).json()
    assert patched["profile"]["target_lufs"] == -17
    assert patched["affected_sound_ids"] == []
    category = ingress.post("/api/ui/categories", json={"name": "Effects"}).json()
    one = repo.update_sound(one.id, SoundUpdate(category_id=category["id"]))
    second = repo.update_sound(second.id, SoundUpdate(category_id=category["id"]))
    response = ingress.post(
        f"/api/ui/profiles/{profile['id']}/apply", json={"category_id": category["id"]}
    )
    assert response.json() == {"queued": 2}
    assert all(
        repo.get_sound(sound.id).recipe.profile_id == profile["id"] for sound in (one, second)
    )
    assert repo.get_sound(one.id).recipe.gain_db == 2
    jobs = [job for job in app.state.jobs.list_jobs() if job.kind == "publish"]
    assert {job.sound_id for job in jobs} == {one.id, second.id}
    patched_again = ingress.patch(f"/api/ui/profiles/{profile['id']}", json={"lra": 9}).json()
    assert set(patched_again["affected_sound_ids"]) == {one.id, second.id}
    assert ingress.post(f"/api/ui/profiles/{profile['id']}/apply", json={}).status_code == 422
    assert (
        ingress.post(
            f"/api/ui/profiles/{profile['id']}/apply",
            json={"sound_ids": [], "category_id": category["id"]},
        ).status_code
        == 422
    )
    assert ingress.delete(f"/api/ui/profiles/{profile['id']}").status_code == 409


def test_apply_by_sound_ids_and_profile_delete(ingress: TestClient, repo: Repository):
    sound = make_sound(repo)
    profile = ingress.post(
        "/api/ui/profiles",
        json={
            "name": "Radio",
            "target_lufs": -16,
            "true_peak": -1.5,
            "lra": 11,
        },
    ).json()
    assert ingress.post(
        f"/api/ui/profiles/{profile['id']}/apply", json={"sound_ids": [sound.id]}
    ).json() == {"queued": 1}
    assert ingress.delete(f"/api/ui/profiles/{profile['id']}").status_code == 409
    assert ingress.delete("/api/ui/profiles/voice").status_code == 204


def test_apply_is_atomic_and_deduplicates_targets(
    ingress: TestClient, repo: Repository, app: FastAPI
):
    sound = make_sound(repo)
    profile = ingress.post(
        "/api/ui/profiles",
        json={"name": "Atomic", "target_lufs": -16, "true_peak": -1.5, "lra": 11},
    ).json()
    before_jobs = len([job for job in app.state.jobs.list_jobs() if job.kind == "publish"])
    response = ingress.post(
        f"/api/ui/profiles/{profile['id']}/apply",
        json={"sound_ids": [sound.id, "missing"]},
    )
    assert response.status_code == 404
    assert repo.get_sound(sound.id).recipe.profile_id is None
    assert len([job for job in app.state.jobs.list_jobs() if job.kind == "publish"]) == before_jobs

    duplicate = ingress.post(
        f"/api/ui/profiles/{profile['id']}/apply",
        json={"sound_ids": [sound.id, sound.id]},
    )
    assert duplicate.status_code == 200
    assert duplicate.json() == {"queued": 1}
    assert (
        len([job for job in app.state.jobs.list_jobs() if job.kind == "publish"]) == before_jobs + 1
    )
    assert (
        ingress.post("/api/ui/profiles/missing/apply", json={"sound_ids": [sound.id]}).status_code
        == 404
    )
    assert (
        ingress.post(
            f"/api/ui/profiles/{profile['id']}/apply", json={"category_id": "missing"}
        ).status_code
        == 404
    )
    assert repo.get_sound(sound.id).recipe.profile_id == profile["id"]
    assert (
        len([job for job in app.state.jobs.list_jobs() if job.kind == "publish"]) == before_jobs + 1
    )


def test_profile_delete_conflicts_with_category_default(ingress: TestClient, repo: Repository):
    profile = ingress.post(
        "/api/ui/profiles",
        json={"name": "Quiet", "target_lufs": -20, "true_peak": -1.5, "lra": 11},
    ).json()
    repo.update_category("general", CategoryUpdate(default_profile_id=profile["id"]))
    assert ingress.delete(f"/api/ui/profiles/{profile['id']}").status_code == 409
