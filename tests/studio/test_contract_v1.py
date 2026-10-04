"""The App's v1 responses conform to the published OpenAPI schemas."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from sound_effects_studio.app import create_app
from sound_effects_studio.config import Paths
from sound_effects_studio.models import Published, Recipe

pytestmark = pytest.mark.studio

CONTRACT = Path(__file__).resolve().parents[2] / "contract" / "openapi-v1.yaml"


@pytest.fixture(scope="module")
def document() -> dict[str, Any]:
    return yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))


def validator(document: dict[str, Any], schema: str) -> Draft202012Validator:
    return Draft202012Validator(
        {"$ref": f"#/components/schemas/{schema}", "components": document["components"]}
    )


@pytest.fixture
def app(tmp_path: Path) -> Iterator[FastAPI]:
    root = tmp_path / "root"
    paths = Paths(
        data_dir=root / "data",
        www_dir=root / "www",
        import_roots={},
        static_dir=root / "static",
        dev_mode=False,
    )
    application = create_app(paths, start_background=False)
    yield application
    application.state.db.close()


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app, headers={"Authorization": f"Bearer {app.state.tokens.get()}"})


def test_health_matches_the_contract(document: dict[str, Any], client: TestClient):
    validator(document, "Health").validate(client.get("/api/v1/health").json())


def test_empty_catalog_matches_the_contract(document: dict[str, Any], client: TestClient):
    response = client.get("/api/v1/catalog")
    validator(document, "Catalog").validate(response.json())
    assert response.headers["etag"] == f'"rev-{response.json()["revision"]}"'


def test_catalog_with_sounds_matches_the_contract(
    document: dict[str, Any], app: FastAPI, client: TestClient
):
    repo = app.state.repo
    sound = repo.create_sound(
        category_id="general",
        title="Chime",
        key="chime",
        tags=["door", "bell"],
        seasons=["regular"],
        all_seasons=True,
        recipe=Recipe(),
        original=None,
    )
    repo.set_published(
        sound.id,
        Published(
            revision=3,
            filename=f"{sound.id}-r3.mp3",
            duration=2.25,
            loudness_lufs=None,
            true_peak_db=None,
            size=2048,
            published_at="2026-01-01T00:00:00Z",
        ),
    )
    body = client.get("/api/v1/catalog").json()
    assert len(body["sounds"]) == 1
    errors = sorted(validator(document, "Catalog").iter_errors(body), key=str)
    assert errors == []
    assert body["generated_at"].endswith("Z")


def test_error_responses_match_the_contract(document: dict[str, Any], client: TestClient):
    error = validator(document, "Error")
    error.validate(TestClient(client.app).get("/api/v1/health").json())
    invalid = client.post("/api/v1/selections", json={"events": [{"sound_id": 1}]})
    assert invalid.status_code == 422
    error.validate(invalid.json())


def test_selection_request_body_matches_the_contract(document: dict[str, Any], client: TestClient):
    batch = {
        "events": [
            {
                "sound_id": "s",
                "category_id": "general",
                "season_id": "regular",
                "selected_at": "2026-03-01T10:00:00Z",
            }
        ]
    }
    validator(document, "SelectionBatch").validate(batch)
    assert client.post("/api/v1/selections", json=batch).status_code == 204
