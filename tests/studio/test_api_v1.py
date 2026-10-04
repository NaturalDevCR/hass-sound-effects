"""Integration API v1, error mapping and the UI shell served by the app factory."""

import dataclasses
import importlib.machinery
import importlib.util
import re
import sys
import types
from collections.abc import Iterator

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from sound_effects_studio import __version__
from sound_effects_studio.app import create_app
from sound_effects_studio.auth import INGRESS_PEER
from sound_effects_studio.config import Paths
from sound_effects_studio.errors import ConflictError, InvalidError, NotFoundError
from sound_effects_studio.models import Published, Recipe, Sound, SoundUpdate
from sound_effects_studio.repository import Repository

pytestmark = pytest.mark.studio


@pytest.fixture
def app(paths: Paths) -> Iterator[FastAPI]:
    application = create_app(paths, start_background=False)
    yield application
    application.state.db.close()


@pytest.fixture
def repo(app: FastAPI) -> Repository:
    return app.state.repo


@pytest.fixture
def auth(app: FastAPI) -> dict[str, str]:
    return {"Authorization": f"Bearer {app.state.tokens.get()}"}


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


@pytest.fixture
def ingress(app: FastAPI) -> TestClient:
    return TestClient(app, client=(INGRESS_PEER, 50000))


def publish_sound(repo: Repository, title: str = "Chime") -> Sound:
    sound = repo.create_sound(
        category_id="general",
        title=title,
        key=title.lower(),
        tags=["door"],
        seasons=["regular"],
        all_seasons=False,
        recipe=Recipe(),
        original=None,
    )
    return repo.set_published(
        sound.id,
        Published(
            revision=1,
            filename=f"{sound.id}-r1.mp3",
            duration=1.5,
            loudness_lufs=-16.0,
            true_peak_db=-1.5,
            size=1000,
            published_at="2026-01-01T00:00:00Z",
        ),
    )


# --- authentication ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/v1/health"),
        ("GET", "/api/v1/catalog"),
        ("POST", "/api/v1/selections"),
    ],
)
def test_v1_requires_a_bearer_token(client: TestClient, method: str, path: str):
    missing = client.request(method, path, json={"events": []})
    assert missing.status_code == 401
    assert isinstance(missing.json()["detail"], str)
    wrong = client.request(
        method, path, json={"events": []}, headers={"Authorization": "Bearer wrong"}
    )
    assert wrong.status_code == 401


def test_v1_is_reachable_from_any_peer_with_the_token(client: TestClient, auth: dict[str, str]):
    assert client.get("/api/v1/health", headers=auth).status_code == 200


# --- health --------------------------------------------------------------------------------


def test_health_reports_identity(client: TestClient, auth: dict[str, str], paths: Paths):
    body = client.get("/api/v1/health", headers=auth).json()
    assert body["status"] == "ok"
    assert body["version"] == __version__
    assert body["api_version"] == 1
    assert re.fullmatch(r"[0-9a-f]{32}", body["instance_id"])
    assert body["instance_id"] == (paths.data_dir / "instance_id").read_text().strip()


def test_instance_id_is_stable_across_restarts(paths: Paths):
    first = create_app(paths, start_background=False)
    second = create_app(paths, start_background=False)
    try:
        assert first.state.instance_id == second.state.instance_id
        assert first.state.tokens.get() == second.state.tokens.get()
    finally:
        first.state.db.close()
        second.state.db.close()


# --- catalog -------------------------------------------------------------------------------


def test_catalog_returns_published_sounds_with_an_etag(
    client: TestClient, auth: dict[str, str], repo: Repository
):
    sound = publish_sound(repo)
    revision = repo.catalog_revision()
    response = client.get("/api/v1/catalog", headers=auth)
    assert response.status_code == 200
    assert response.headers["etag"] == f'"rev-{revision}"'
    body = response.json()
    assert body["revision"] == revision
    assert [s["id"] for s in body["sounds"]] == [sound.id]
    assert body["sounds"][0]["published"] == {
        "revision": 1,
        "filename": f"{sound.id}-r1.mp3",
        "duration": 1.5,
        "mime_type": "audio/mpeg",
    }
    assert {season["id"] for season in body["seasons"]} == {"regular"}
    assert "builtin" not in body["seasons"][0]
    assert [c["id"] for c in body["categories"]] == ["general"]
    assert "default_profile_id" not in body["categories"][0]


def test_catalog_omits_unpublished_sounds(
    client: TestClient, auth: dict[str, str], repo: Repository
):
    repo.create_sound(
        category_id="general",
        title="Draft",
        key="draft",
        tags=[],
        seasons=["regular"],
        all_seasons=False,
        recipe=Recipe(),
        original=None,
    )
    assert client.get("/api/v1/catalog", headers=auth).json()["sounds"] == []


def test_catalog_answers_304_for_a_current_etag(
    client: TestClient, auth: dict[str, str], repo: Repository
):
    publish_sound(repo)
    etag = client.get("/api/v1/catalog", headers=auth).headers["etag"]
    for header in (etag, f"W/{etag}", f'"rev-0", {etag}', "*"):
        cached = client.get("/api/v1/catalog", headers={**auth, "If-None-Match": header})
        assert cached.status_code == 304, header
        assert cached.content == b""
        assert cached.headers["etag"] == etag


def test_catalog_serves_a_new_body_once_the_revision_moves(
    client: TestClient, auth: dict[str, str], repo: Repository
):
    sound = publish_sound(repo)
    etag = client.get("/api/v1/catalog", headers=auth).headers["etag"]
    repo.update_sound(sound.id, SoundUpdate(title="Renamed"))
    fresh = client.get("/api/v1/catalog", headers={**auth, "If-None-Match": etag})
    assert fresh.status_code == 200
    assert fresh.headers["etag"] != etag
    assert fresh.json()["sounds"][0]["title"] == "Renamed"


def test_catalog_ignores_a_stale_or_malformed_etag(client: TestClient, auth: dict[str, str]):
    for header in ('"rev-9999"', "garbage", ""):
        response = client.get("/api/v1/catalog", headers={**auth, "If-None-Match": header})
        assert response.status_code == 200, header


# --- selections ----------------------------------------------------------------------------


def selection(sound_id: str, selected_at: str = "2026-03-01T10:00:00Z") -> dict[str, str]:
    return {
        "sound_id": sound_id,
        "category_id": "general",
        "season_id": "regular",
        "selected_at": selected_at,
    }


def test_selections_update_the_counters(client: TestClient, auth: dict[str, str], repo: Repository):
    sound = publish_sound(repo)
    revision = repo.catalog_revision()
    events = [
        selection(sound.id, "2026-03-01T10:00:00Z"),
        selection(sound.id, "2026-03-02T10:00:00Z"),
    ]
    response = client.post("/api/v1/selections", headers=auth, json={"events": events})
    assert response.status_code == 204
    assert response.content == b""
    updated = repo.get_sound(sound.id)
    assert updated.selection_count == 2
    assert updated.last_selected_at == "2026-03-02T10:00:00Z"
    assert repo.catalog_revision() == revision


def test_selections_accept_an_empty_batch_and_unknown_sounds(
    client: TestClient, auth: dict[str, str]
):
    assert client.post("/api/v1/selections", headers=auth, json={"events": []}).status_code == 204
    batch = {"events": [selection("gone")]}
    assert client.post("/api/v1/selections", headers=auth, json=batch).status_code == 204


def test_selections_reject_more_than_500_events_with_a_string_detail(
    client: TestClient, auth: dict[str, str]
):
    batch = {"events": [selection("s")] * 501}
    response = client.post("/api/v1/selections", headers=auth, json=batch)
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, str)
    assert detail.startswith("events: ")
    assert (
        client.post(
            "/api/v1/selections", headers=auth, json={"events": [selection("s")] * 500}
        ).status_code
        == 204
    )


def test_validation_errors_list_every_field(client: TestClient, auth: dict[str, str]):
    batch = {"events": [{"sound_id": "s", "selected_at": "not a date"}]}
    response = client.post("/api/v1/selections", headers=auth, json=batch)
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, str)
    assert "events.0.category_id: Field required" in detail
    assert "events.0.selected_at: " in detail
    assert "must be an ISO-8601 timestamp" in detail
    assert "Value error," not in detail
    assert "; " in detail


def test_malformed_bodies_get_a_string_detail(client: TestClient, auth: dict[str, str]):
    headers = {**auth, "Content-Type": "application/json"}
    response = client.post("/api/v1/selections", headers=headers, content="{nope")
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)
    response = client.post("/api/v1/selections", headers=auth, json=[1])
    assert response.status_code == 422
    assert response.json()["detail"].startswith("body: ")


# --- error mapping -------------------------------------------------------------------------


def test_domain_errors_map_to_http_statuses(app: FastAPI):
    router = APIRouter()

    @router.get("/boom/{kind}")
    async def boom(kind: str) -> None:
        raise {
            "missing": NotFoundError("Sound 'x' not found"),
            "clash": ConflictError("Category 'x' already exists"),
            "bad": InvalidError("Title must not be blank"),
        }[kind]

    app.include_router(router)
    client = TestClient(app)
    assert client.get("/boom/missing").status_code == 404
    assert client.get("/boom/missing").json() == {"detail": "Sound 'x' not found"}
    assert client.get("/boom/clash").status_code == 409
    assert client.get("/boom/clash").json() == {"detail": "Category 'x' already exists"}
    assert client.get("/boom/bad").status_code == 422
    assert client.get("/boom/bad").json() == {"detail": "Title must not be blank"}


def test_query_validation_errors_are_app_wide_strings(app: FastAPI):
    router = APIRouter()

    @router.get("/dated")
    async def dated(date: int) -> dict[str, int]:
        return {"date": date}

    app.include_router(router)
    response = TestClient(app).get("/dated", params={"date": "x"})
    assert response.status_code == 422
    assert response.json()["detail"].startswith("date: ")


def test_unknown_routes_keep_the_error_shape(client: TestClient):
    response = client.get("/api/v1/nothing")
    assert response.status_code == 404
    assert isinstance(response.json()["detail"], str)


def test_interactive_docs_are_not_exposed(ingress: TestClient):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert ingress.get(path).status_code == 404


# --- UI shell ------------------------------------------------------------------------------


def test_ui_root_requires_the_ingress_peer(client: TestClient):
    response = client.get("/")
    assert response.status_code == 403
    assert isinstance(response.json()["detail"], str)


def test_ui_root_without_a_build_is_503_text(ingress: TestClient):
    response = ingress.get("/")
    assert response.status_code == 503
    assert response.text == "UI not built"
    assert response.headers["content-type"].startswith("text/plain")


def build_ui(paths: Paths) -> None:
    (paths.static_dir / "assets").mkdir(parents=True)
    (paths.static_dir / "index.html").write_text("<html>studio</html>", encoding="utf-8")
    (paths.static_dir / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (paths.static_dir / "secret.txt").write_text("outside assets", encoding="utf-8")


def test_ui_root_serves_the_built_index(ingress: TestClient, paths: Paths):
    build_ui(paths)
    response = ingress.get("/")
    assert response.status_code == 200
    assert response.text == "<html>studio</html>"
    assert response.headers["content-type"].startswith("text/html")


def test_ui_assets_are_served_behind_ingress(client: TestClient, ingress: TestClient, paths: Paths):
    build_ui(paths)
    asset = ingress.get("/assets/app.js")
    assert asset.status_code == 200
    assert asset.text == "console.log(1)"
    assert client.get("/assets/app.js").status_code == 403
    assert ingress.get("/assets/missing.js").status_code == 404
    assert ingress.get("/assets/").status_code == 404


def test_ui_assets_cannot_escape_the_assets_directory(ingress: TestClient, paths: Paths):
    build_ui(paths)
    for path in ("/assets/../secret.txt", "/assets/%2e%2e/secret.txt", "/assets/..%2fsecret.txt"):
        assert ingress.get(path).status_code in (400, 404), path
        assert "outside assets" not in ingress.get(path).text


def test_dev_mode_opens_the_ui_to_any_peer(paths: Paths):
    app = create_app(dataclasses.replace(paths, dev_mode=True), start_background=False)
    try:
        assert TestClient(app).get("/").status_code == 503
    finally:
        app.state.db.close()


# --- app factory ---------------------------------------------------------------------------


def test_create_app_prepares_state_without_background_work(app: FastAPI, paths: Paths):
    state = app.state
    for name in (
        "paths",
        "db",
        "repo",
        "publisher",
        "jobs",
        "tokens",
        "supervisor",
        "instance_id",
        "www_status",
        "discovery_status",
        "media_base_url_effective",
    ):
        assert hasattr(state, name), name
    assert state.notifier is None
    assert state.paths is paths
    assert not state.supervisor.available
    assert state.www_status.exists
    assert state.www_status.created_by_app is False
    assert state.www_status.served is None
    assert state.discovery_status["status"] == "unavailable"
    assert state.media_base_url_effective == ""
    assert (paths.data_dir / "api_token").is_file()
    assert paths.publish_dir.is_dir()


def test_create_app_reports_a_www_directory_it_had_to_create(paths: Paths):
    paths.www_dir.rmdir()
    app = create_app(paths, start_background=False)
    try:
        assert app.state.www_status.created_by_app is True
    finally:
        app.state.db.close()


def fake_router_module(monkeypatch: pytest.MonkeyPatch, name: str, path: str) -> None:
    router = APIRouter()

    @router.get(path)
    async def handler() -> dict[str, str]:
        return {"from": name}

    module = types.ModuleType(f"sound_effects_studio.{name}")
    module.__spec__ = importlib.machinery.ModuleSpec(module.__name__, None)
    module.__dict__["router"] = router
    monkeypatch.setitem(sys.modules, module.__name__, module)


def test_optional_ui_routers_are_included_behind_ingress(
    paths: Paths, monkeypatch: pytest.MonkeyPatch
):
    fake_router_module(monkeypatch, "api_ui_organize", "/api/ui/organize-probe")
    fake_router_module(monkeypatch, "api_ui_sounds", "/api/ui/sounds-probe")
    app = create_app(paths, start_background=False)
    try:
        ingress = TestClient(app, client=(INGRESS_PEER, 50000))
        assert ingress.get("/api/ui/organize-probe").json() == {"from": "api_ui_organize"}
        assert ingress.get("/api/ui/sounds-probe").json() == {"from": "api_ui_sounds"}
        assert TestClient(app).get("/api/ui/organize-probe").status_code == 403
    finally:
        app.state.db.close()


def test_optional_ui_routers_are_skipped_when_the_module_is_absent(
    paths: Paths, monkeypatch: pytest.MonkeyPatch
):
    fake_router_module(monkeypatch, "api_ui_organize", "/api/ui/organize-probe")
    with monkeypatch.context() as patch:
        patch.setattr(importlib.util, "find_spec", lambda name, package=None: None)
        app = create_app(paths, start_background=False)
    try:
        ingress = TestClient(app, client=(INGRESS_PEER, 50000))
        assert ingress.get("/api/ui/organize-probe").status_code == 404
    finally:
        app.state.db.close()
