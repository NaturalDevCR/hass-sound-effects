# Sound Effects Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a Home Assistant Supervisor App ("Sound Effects Studio") and a HACS integration (`sound_effects`) that manage, edit, normalize, and select short sound effects, per `docs/superpowers/specs/2026-10-03-sound-effects-design.md`.

**Architecture:** The App (FastAPI + SQLite + ffmpeg + Vue SPA via Ingress) owns files, recipes, rendering, categories, seasons, and normalization profiles, and publishes immutable MP3s to `/config/www/sound-effects/`. The integration caches the App catalog on disk, resolves the season, runs a persisted shuffle bag, and answers `sound_effects.select` with a URL and duration without contacting the App. Automations keep playback.

**Tech Stack:** Python 3.13, FastAPI, uvicorn, httpx, sqlite3, ffmpeg/ffprobe; Home Assistant custom integration (aiohttp, DataUpdateCoordinator, Store); Vue 3 + TypeScript + Vite + Tailwind 4 + wavesurfer.js 7 + @mdi/js; pytest, pytest-homeassistant-custom-component, vitest; uv; GitHub Actions.

## Global Constraints

- Repository: `NaturalDevCR/hass-sound-effects`, public, license Apache-2.0, default branch `main`.
- Python `>=3.13`; ruff line length 100, `target-version = "py313"`, lint rules `E,F,I,UP,B,SIM`; pyright `strict` for `app/src/sound_effects_studio` and `custom_components/sound_effects`.
- App slug `sound_effects_studio`; Ingress port `8099`; base image `ghcr.io/home-assistant/{arch}-base-python:3.13-alpine3.22`; arch `aarch64`, `amd64`; built locally by the Supervisor (no `image:` key).
- Integration domain `sound_effects`; `single_config_entry: true`; `iot_class: local_polling`; `integration_type: service`; HA minimum `2025.3.0` in `hacs.json`.
- Published files: `/homeassistant/www/sound-effects/<sound_id>-r<revision>.mp3` in the App container == `/config/www/sound-effects/...` in HA == URL path `/local/sound-effects/...`.
- Ingress peer address `172.30.32.2`; dev bypass env `SOUND_EFFECTS_DEV=1`.
- API token file `/data/api_token`; instance id file `/data/instance_id`.
- Built-in season `regular` (cannot be deleted). Built-in profiles: `standard` (−16, −1.5, 11), `loud` (−13, −1.0, 11), `soft` (−20, −1.5, 11), `voice` (−18, −1.5, 7). Seed category `general` "General".
- MP3 output: `libmp3lame -q:a 2`, 44.1 kHz, channels = min(source, 2). Identity recipe + mp3 source ⇒ byte-identical copy.
- UI: all URLs relative (no leading `/`), hash router, Spanish + English, dark theme, accent `#8b5cf6`, mobile-first (bottom tabs < `md`, sidebar ≥ `md`).
- Commits: Conventional Commits; every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Stage only the files your task touched (`git add <paths>`), never `git add -A`.

---

## File Structure

```
.github/workflows/quality.yml       ruff, pyright, pytest, vitest, UI build (scripts/verify.sh)
.github/workflows/validate.yml      hassfest + HACS action
.github/workflows/app-build.yml     docker buildx of app/ for amd64 + aarch64 (no push)
pyproject.toml  uv.lock  .gitignore  LICENSE  README.md  hacs.json  repository.yaml
scripts/verify.sh
contract/openapi-v1.yaml            App ⇄ integration contract (v1 endpoints only)
contract/season_cases.json          shared calendar fixtures (both Python implementations)

app/config.yaml  app/Dockerfile  app/DOCS.md  app/CHANGELOG.md  app/icon.png  app/logo.png
app/translations/en.yaml  app/translations/es.yaml
app/rootfs/usr/bin/sound-effects-studio
app/src/sound_effects_studio/
  __init__.py        __version__
  config.py          Paths (filesystem layout, env), load_options()
  errors.py          NotFoundError, ConflictError, InvalidError
  models.py          pydantic models shared by DB/API
  seasons.py         season_matches(), resolve_calendar_season()
  db.py              Database (sqlite3 connection, schema, migrations, seeds)
  repository.py      Repository (CRUD, catalog revision, catalog document)
  media.py           ffprobe/ffmpeg: probe, measure_loudness, build_filter_chain, render
  publisher.py       Publisher (www dirs, atomic commit, cleanup, audition copies)
  jobs.py            JobQueue (import / publish / preview)
  uploads.py         UploadStore (chunked uploads)
  importer.py        ImportBrowser (virtual roots, traversal-safe)
  supervisor.py      SupervisorClient (discovery, events, services, config)
  auth.py            TokenStore, require_ingress, require_bearer
  notifier.py        CatalogNotifier (debounced HA event)
  api_v1.py          /api/v1 router (integration)
  api_ui_organize.py /api/ui categories, seasons, profiles, settings, state, token
  api_ui_sounds.py   /api/ui sounds, uploads, import, audition, jobs, audio streams
  app.py             create_app(), lifespan, SPA static
  main.py            uvicorn entry
app/ui/ ...                          (see Track C)

custom_components/sound_effects/
  __init__.py  manifest.json  const.py  api.py  catalog.py  seasons.py  selection.py
  coordinator.py  manager.py  services.py  services.yaml  config_flow.py
  entity.py  sensor.py  select.py  binary_sensor.py  diagnostics.py  icons.json
  translations/en.json  translations/es.json  brand/icon.png

tests/
  conftest.py                         (none; per-suite conftests)
  studio/conftest.py  studio/test_*.py
  integration/conftest.py  integration/test_*.py
  contract/test_openapi.py  contract/test_season_cases.py
  test_repository_metadata.py
```

Tracks after Task 1 run in parallel in separate git worktrees:
- **Track A (App backend):** Tasks 2–8 on branch `track/studio`.
- **Track B (Integration):** Tasks 9–12 on branch `track/integration`.
- **Track C (UI):** Tasks 13–17 on branch `track/ui`.
- **Final:** Task 18 (docs, release) on `main` after merging tracks.

---

## Shared API Reference (binding for Tracks A, B, C)

All JSON uses snake_case. Timestamps are ISO-8601 UTC strings with `Z`. Errors use FastAPI's `{"detail": "<human message>"}` with status 400/401/403/404/409/413/415/422.

### Types (TypeScript notation; Python models in `models.py` mirror them)

```ts
type Season = { id: string; name: string; color: string; icon: string;
  start: string | null; end: string | null;   // "MM-DD", inclusive; null only for regular
  priority: number; builtin: boolean }
type Category = { id: string; name: string; icon: string; color: string; description: string;
  sort_order: number; default_profile_id: string | null }
type Profile = { id: string; name: string; target_lufs: number; true_peak: number; lra: number }
type Recipe = { trim_start: number; trim_end: number | null; gain_db: number;
  fade_in: number; fade_out: number; profile_id: string | null }
type OriginalInfo = { filename: string; size: number; format: string; codec: string;
  duration: number; sample_rate: number; channels: number }
type Published = { revision: number; filename: string; duration: number;
  loudness_lufs: number | null; true_peak_db: number | null; size: number;
  published_at: string; mime_type: "audio/mpeg" }
type SoundStatus = "processing" | "ready" | "rendering" | "failed"
type Sound = { id: string; category_id: string; title: string; key: string; tags: string[];
  seasons: string[]; all_seasons: boolean; enabled: boolean; notes: string;
  original: OriginalInfo | null; recipe: Recipe; published: Published | null;
  status: SoundStatus; error: string | null; selection_count: number;
  last_selected_at: string | null; created_at: string; updated_at: string; has_preview: boolean }
type Job = { id: string; kind: "import" | "publish" | "preview"; sound_id: string;
  sound_title: string; status: "queued" | "running" | "done" | "failed"; progress: number;
  error: string | null; created_at: string; started_at: string | null; finished_at: string | null }
type AuditionTarget = { id: string; label: string; kind: "media_player" | "script";
  entity_id: string; volume: number | null }
type Settings = { max_upload_mb: number; max_duration_s: number;
  audition_targets: AuditionTarget[]; media_base_url: string }   // "" = auto-detect
type State = { version: string; api_token_masked: string; catalog_revision: number;
  discovery: { status: "ok" | "failed" | "unavailable"; message: string | null };
  www: { exists: boolean; served: boolean | null; created_by_app: boolean };
  media_base_url_effective: string;
  storage: { originals_bytes: number; published_bytes: number; previews_bytes: number };
  settings: Settings }
```

### Integration API v1 (bearer auth)

| Method | Path | Request | Response |
|---|---|---|---|
| GET | `api/v1/health` | – | `{status:"ok", version, api_version:1, instance_id}` |
| GET | `api/v1/catalog` | `If-None-Match` | `200 Catalog` + `ETag: "rev-<n>"`, or `304` |
| POST | `api/v1/selections` | `{events:[{sound_id, category_id, season_id, selected_at}]}` | `204` |

```ts
type Catalog = { revision: number; generated_at: string;
  seasons: Omit<Season, "builtin">[];
  categories: Omit<Category, "default_profile_id">[];
  sounds: { id: string; category_id: string; title: string; key: string; tags: string[];
    seasons: string[]; all_seasons: boolean; enabled: boolean;
    published: { revision: number; filename: string; duration: number; mime_type: string } }[] }
// Catalog.sounds contains only sounds whose `published` is not null.
```

### UI API (`api/ui/*`, Ingress auth)

| Method | Path | Request | Response |
|---|---|---|---|
| GET | `state` | – | `State` |
| GET | `token` | – | `{token}` |
| POST | `token/rotate` | – | `{api_token_masked}` |
| GET / PUT | `settings` | `Settings` | `Settings` |
| GET | `categories` | – | `Category[]` (sorted by sort_order, name) |
| POST | `categories` | `{id?, name, icon?, color?, description?, default_profile_id?}` | `Category` (id = slugify(name) when absent; 409 if exists) |
| PATCH | `categories/{id}` | partial (no id) | `Category` |
| DELETE | `categories/{id}` | – | `204` (409 when sounds reference it) |
| PUT | `categories/order` | `{ids: string[]}` | `Category[]` |
| GET | `seasons` | – | `Season[]` (regular first, then priority desc, name) |
| POST | `seasons` | `{id?, name, color?, icon?, start, end, priority?}` | `Season` |
| PATCH | `seasons/{id}` | partial | `Season` (regular: only name/color/icon) |
| DELETE | `seasons/{id}` | – | `204` (400 for regular; removes id from sounds; empty → `["regular"]`) |
| GET | `seasons/resolve?date=YYYY-MM-DD` | – | `{date, season_id}` |
| GET | `profiles` | – | `Profile[]` |
| POST | `profiles` | `{id?, name, target_lufs, true_peak, lra}` | `Profile` |
| PATCH | `profiles/{id}` | partial | `{profile: Profile, affected_sound_ids: string[]}` |
| DELETE | `profiles/{id}` | – | `204` (409 when used by a recipe or category default) |
| POST | `profiles/{id}/apply` | `{sound_ids: string[]}` or `{category_id}` | `{queued: number}` |
| GET | `sounds` | – | `Sound[]` |
| GET | `sounds/{id}` | – | `Sound` |
| PATCH | `sounds/{id}` | `{title?, category_id?, key?, tags?, seasons?, all_seasons?, enabled?, notes?}` | `Sound` |
| PUT | `sounds/{id}/recipe` | `Recipe` | `{sound: Sound, job: Job}` (queues publish) |
| POST | `sounds/{id}/preview` | `Recipe` | `{job: Job}` (queues preview, recipe not saved) |
| DELETE | `sounds/{id}` | – | `204` |
| POST | `sounds/bulk` | `{ids, set:{category_id?, seasons?, all_seasons?, add_tags?, remove_tags?, enabled?, profile_id?}}` | `{updated: number, queued: number}` (`profile_id` key present ⇒ set recipe + queue publish) |
| POST | `sounds/bulk-delete` | `{ids}` | `{deleted: number}` |
| GET | `sounds/{id}/original`, `sounds/{id}/preview`, `sounds/{id}/published` | Range | audio bytes |
| POST | `sounds/{id}/audition` | `{target_id, use_preview: boolean}` | `{ok: true, url}` |
| POST | `uploads` | `{filename, size}` | `{upload_id, chunk_size}` (chunk_size = 4194304) |
| PUT | `uploads/{id}/chunks/{index}` | raw bytes | `{received: number}` |
| POST | `uploads/{id}/complete` | `{category_id, seasons, all_seasons, tags, title?, profile_id?}` | `Sound` (status `processing`); `profile_id` absent ⇒ category default, `null` ⇒ none |
| GET | `import/browse?path=` | – | `{path, parent, roots, entries:[{name, path, kind:"dir"|"file", size, supported}]}` |
| POST | `import` | `{paths, category_id, seasons, all_seasons, tags, profile_id?}` | `{sounds: Sound[]}` |
| GET | `jobs` | – | `Job[]` (running/queued first, then last 50 finished, newest first) |

Import virtual roots: `config/www` → `/homeassistant/www`, `media` → `/media`, `share` → `/share`. `path=""` lists roots. Supported extensions: `.mp3 .wav .flac .ogg .opus .m4a .aac .webm .mp4 .mov`.

### Home Assistant contract

- Event fired by the App: `sound_effects_catalog_changed` with `{revision}` (debounced 1 s).
- Discovery payload: `{service: "sound_effects", config: {host, port: 8099, token, instance_id}}`.
- Action `sound_effects.select` response keys: `sound_id, key, title, category, tags, season, requested_season, season_fallback, url, path, duration, revision, mime_type`. `category` = category id; `requested_season` = effective season before fallback; `path` = `/local/sound-effects/<filename>`.

---

## Task 1: Repository scaffold, tooling, CI, contract

**Model:** Sonnet. **Branch:** `main`.

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `LICENSE`, `README.md` (stub), `hacs.json`, `repository.yaml`, `scripts/verify.sh`, `.github/workflows/{quality,validate,app-build}.yml`, `contract/openapi-v1.yaml`, `contract/season_cases.json`, `tests/contract/test_openapi.py`, `tests/test_repository_metadata.py`, `app/src/sound_effects_studio/__init__.py`, `custom_components/sound_effects/manifest.json` (initial), `app/config.yaml` (initial)

**Interfaces:**
- Produces: `uv sync --all-groups` environment with every Python dependency for all tracks; `scripts/verify.sh`; `contract/season_cases.json` format `[{"seasons":[{id,start,end,priority}], "date":"YYYY-MM-DD", "expected":"<id>"}]`.

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling>=1.25"]
build-backend = "hatchling.build"

[project]
name = "hass-sound-effects"
version = "1.0.0"
description = "Home Assistant Sound Effects app and integration"
readme = "README.md"
requires-python = ">=3.13"
license = { file = "LICENSE" }
authors = [{ name = "NaturalDevCR" }]
dependencies = []

[tool.hatch.build.targets.wheel]
packages = ["app/src/sound_effects_studio"]

[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "pytest-homeassistant-custom-component>=0.13.300",
    "ruff>=0.8",
    "pyright>=1.1.390",
    "openapi-spec-validator>=0.7.2",
    "pyyaml>=6.0",
]
studio = ["fastapi>=0.115", "uvicorn[standard]>=0.32", "httpx>=0.28"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = [".", "app/src"]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
markers = [
  "studio: tests for the Sound Effects Studio app",
  "integration: tests for the Home Assistant integration",
]

[tool.ruff]
target-version = "py313"
line-length = 100
extend-exclude = [".venv", "build", "dist", "app/ui"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.pyright]
include = ["app/src/sound_effects_studio", "custom_components/sound_effects"]
typeCheckingMode = "strict"
pythonVersion = "3.13"
venvPath = "."
venv = ".venv"
reportMissingTypeStubs = false
```

- [ ] **Step 2: `.gitignore`, `LICENSE` (Apache-2.0 full text, copyright 2026 NaturalDevCR), `hacs.json`, `repository.yaml`**

```gitignore
.venv/
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
node_modules/
app/ui/dist/
app/src/sound_effects_studio/static/
.DS_Store
coverage/
```

```json
{
  "name": "Sound Effects",
  "content_in_root": false,
  "render_readme": true,
  "homeassistant": "2025.3.0"
}
```

```yaml
name: Sound Effects
url: https://github.com/NaturalDevCR/hass-sound-effects
maintainer: NaturalDevCR
```

- [ ] **Step 3: Initial `custom_components/sound_effects/manifest.json` and `app/config.yaml`**

```json
{
  "domain": "sound_effects",
  "name": "Sound Effects",
  "codeowners": ["@NaturalDevCR"],
  "config_flow": true,
  "dependencies": [],
  "after_dependencies": ["hassio"],
  "documentation": "https://github.com/NaturalDevCR/hass-sound-effects",
  "integration_type": "service",
  "iot_class": "local_polling",
  "issue_tracker": "https://github.com/NaturalDevCR/hass-sound-effects/issues",
  "requirements": [],
  "single_config_entry": true,
  "version": "1.0.0"
}
```

```yaml
name: Sound Effects Studio
version: 1.0.0
slug: sound_effects_studio
description: Upload, edit, normalize and organize sound effects for Home Assistant
url: https://github.com/NaturalDevCR/hass-sound-effects
arch:
  - aarch64
  - amd64
startup: application
init: false
ingress: true
ingress_port: 8099
panel_icon: mdi:waveform
panel_title: Sound Effects
homeassistant_api: true
hassio_api: true
discovery:
  - sound_effects
map:
  - homeassistant_config:rw
  - media:ro
  - share:ro
options:
  log_level: info
schema:
  log_level: list(debug|info|warning|error)
```

`app/src/sound_effects_studio/__init__.py`:

```python
"""Sound Effects Studio: the Supervisor App behind the sound_effects integration."""

__version__ = "1.0.0"
```

- [ ] **Step 4: `contract/season_cases.json`** — at least these cases (both implementations must pass them):

```json
[
  {"name": "no special seasons", "seasons": [], "date": "2026-07-01", "expected": "regular"},
  {"name": "inside simple range", "seasons": [{"id": "halloween", "start": "10-01", "end": "10-31", "priority": 10}], "date": "2026-10-15", "expected": "halloween"},
  {"name": "range start inclusive", "seasons": [{"id": "halloween", "start": "10-01", "end": "10-31", "priority": 10}], "date": "2026-10-01", "expected": "halloween"},
  {"name": "range end inclusive", "seasons": [{"id": "halloween", "start": "10-01", "end": "10-31", "priority": 10}], "date": "2026-10-31", "expected": "halloween"},
  {"name": "outside range", "seasons": [{"id": "halloween", "start": "10-01", "end": "10-31", "priority": 10}], "date": "2026-11-01", "expected": "regular"},
  {"name": "wrapping range december", "seasons": [{"id": "christmas", "start": "12-01", "end": "01-06", "priority": 20}], "date": "2026-12-24", "expected": "christmas"},
  {"name": "wrapping range january", "seasons": [{"id": "christmas", "start": "12-01", "end": "01-06", "priority": 20}], "date": "2027-01-06", "expected": "christmas"},
  {"name": "wrapping range outside", "seasons": [{"id": "christmas", "start": "12-01", "end": "01-06", "priority": 20}], "date": "2027-01-07", "expected": "regular"},
  {"name": "overlap higher priority wins", "seasons": [{"id": "halloween", "start": "10-15", "end": "11-30", "priority": 10}, {"id": "christmas", "start": "11-15", "end": "01-06", "priority": 20}], "date": "2026-11-20", "expected": "christmas"},
  {"name": "overlap equal priority id order", "seasons": [{"id": "b-season", "start": "05-01", "end": "05-31", "priority": 5}, {"id": "a-season", "start": "05-10", "end": "05-20", "priority": 5}], "date": "2026-05-15", "expected": "a-season"},
  {"name": "leap day inside", "seasons": [{"id": "feb", "start": "02-01", "end": "02-29", "priority": 1}], "date": "2028-02-29", "expected": "feb"},
  {"name": "regular entry ignored", "seasons": [{"id": "regular", "start": null, "end": null, "priority": 0}], "date": "2026-03-03", "expected": "regular"}
]
```

- [ ] **Step 5: `contract/openapi-v1.yaml`** — OpenAPI 3.1 document describing exactly the three v1 endpoints, `bearerAuth` security scheme, and schemas `Health`, `Catalog`, `CatalogSeason`, `CatalogCategory`, `CatalogSound`, `SelectionEvent`, `SelectionBatch`, `Error`, matching the Shared API Reference field-for-field (all fields `required`, nullable fields typed `["string","null"]`).

- [ ] **Step 6: Tests `tests/contract/test_openapi.py` and `tests/test_repository_metadata.py`**

```python
# tests/contract/test_openapi.py
from pathlib import Path

import yaml
from openapi_spec_validator import validate

CONTRACT = Path(__file__).resolve().parents[2] / "contract" / "openapi-v1.yaml"


def test_contract_is_valid_openapi() -> None:
    validate(yaml.safe_load(CONTRACT.read_text(encoding="utf-8")))


def test_contract_declares_v1_paths() -> None:
    document = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    assert set(document["paths"]) == {"/api/v1/health", "/api/v1/catalog", "/api/v1/selections"}
```

```python
# tests/test_repository_metadata.py
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_versions_agree() -> None:
    manifest = json.loads((ROOT / "custom_components/sound_effects/manifest.json").read_text())
    app_config = yaml.safe_load((ROOT / "app/config.yaml").read_text())
    namespace: dict[str, str] = {}
    exec((ROOT / "app/src/sound_effects_studio/__init__.py").read_text(), namespace)
    assert manifest["version"] == app_config["version"] == namespace["__version__"]


def test_hacs_metadata() -> None:
    hacs = json.loads((ROOT / "hacs.json").read_text())
    assert hacs["name"] == "Sound Effects"
    assert hacs["content_in_root"] is False


def test_app_manifest_core_fields() -> None:
    app_config = yaml.safe_load((ROOT / "app/config.yaml").read_text())
    assert app_config["slug"] == "sound_effects_studio"
    assert app_config["ingress_port"] == 8099
    assert "homeassistant_config:rw" in app_config["map"]
    assert app_config["discovery"] == ["sound_effects"]
    assert "image" not in app_config
```

- [ ] **Step 7: `scripts/verify.sh`** (executable)

```bash
#!/usr/bin/env bash
# Release gate. Runs from the repository root; never contacts Home Assistant.
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest -q

for translation in custom_components/sound_effects/translations/*.json; do
    [ -e "$translation" ] || continue
    uv run python -m json.tool "$translation" >/dev/null
done

if [ -f app/ui/package.json ] && command -v npm >/dev/null 2>&1; then
    npm --prefix app/ui ci
    npm --prefix app/ui run test:unit
    npm --prefix app/ui run build
else
    echo "Skipped UI tests/build (no npm or no UI yet)." >&2
fi

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    docker build --build-arg BUILD_ARCH=amd64 --file app/Dockerfile --tag sound-effects-studio:verify app
else
    echo "Skipped Docker build (daemon unavailable); CI builds the image." >&2
fi
```

- [ ] **Step 8: Workflows**

`quality.yml`: on push/pull_request; ubuntu-latest; `sudo apt-get update && sudo apt-get install -y ffmpeg`; setup-python 3.13; setup-node 22; `pip install uv`; `uv sync --all-groups`; `scripts/verify.sh`.

`validate.yml`: two jobs — `hassfest` (`actions/checkout@v4`, `home-assistant/actions/hassfest@master`) and `hacs` (`hacs/action@main` with `category: integration`, `ignore: brands`).

`app-build.yml`: on push/pull_request; matrix `{build_arch: amd64, platform: linux/amd64}`, `{build_arch: aarch64, platform: linux/arm64}`; `docker/setup-qemu-action@v3`, `docker/setup-buildx-action@v3`, `docker/build-push-action@v6` with `context: app`, `file: app/Dockerfile`, `build-args: BUILD_ARCH=${{ matrix.build_arch }}`, `push: false`.

- [ ] **Step 9: Sync and verify**

Run: `uv sync --all-groups && uv run pytest -q tests/contract tests/test_repository_metadata.py && uv run ruff check . && uv run ruff format --check .`
Expected: all pass (pyright may report "no files" until code exists — acceptable at this step).

- [ ] **Step 10: README stub** — title, one-paragraph description, "Work in progress" note (replaced in Task 18).

- [ ] **Step 11: Commit**

```bash
git add pyproject.toml uv.lock .gitignore LICENSE README.md hacs.json repository.yaml scripts .github contract tests app/config.yaml app/src custom_components
git commit -m "chore: scaffold repository, tooling, CI and v1 contract"
```

---

# Track A — Sound Effects Studio (App backend)

All Track A tests live in `tests/studio/`, are marked `pytestmark = pytest.mark.studio`, and use real `ffmpeg`/`ffprobe`. Shared fixtures in `tests/studio/conftest.py`:

```python
"""Fixtures for Sound Effects Studio tests."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from sound_effects_studio.config import Paths


@pytest.fixture
def paths(tmp_path: Path) -> Paths:
    root = tmp_path / "root"
    p = Paths(
        data_dir=root / "data",
        www_dir=root / "homeassistant" / "www",
        import_roots={
            "config/www": root / "homeassistant" / "www",
            "media": root / "media",
            "share": root / "share",
        },
        static_dir=root / "static",
        dev_mode=False,
    )
    for directory in (p.data_dir, p.import_roots["media"], p.import_roots["share"]):
        directory.mkdir(parents=True, exist_ok=True)
    p.www_dir.mkdir(parents=True, exist_ok=True)
    return p


@pytest.fixture
def make_tone(tmp_path: Path) -> Callable[..., Path]:
    """Generate a sine tone file with ffmpeg (lavfi)."""

    def _make(
        name: str = "tone.wav",
        seconds: float = 3.0,
        frequency: int = 440,
        volume_db: float = -20.0,
        channels: int = 2,
    ) -> Path:
        out = tmp_path / "fixtures" / name
        out.parent.mkdir(parents=True, exist_ok=True)
        layout = "stereo" if channels == 2 else "mono"
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", f"sine=frequency={frequency}:duration={seconds}:sample_rate=44100",
                "-af", f"volume={volume_db}dB,aformat=channel_layouts={layout}",
                *(["-c:a", "libmp3lame", "-q:a", "4"] if name.endswith(".mp3") else []),
                str(out),
            ],
            check=True,
        )
        return out

    return _make
```

## Task 2: Studio core — config, errors, models, seasons, database, repository

**Model:** Sonnet. **Branch:** `track/studio`.

**Files:**
- Create: `app/src/sound_effects_studio/{config,errors,models,seasons,db,repository}.py`
- Test: `tests/studio/conftest.py`, `tests/studio/test_seasons.py`, `tests/studio/test_repository.py`, `tests/contract/test_season_cases.py` (studio half)

**Interfaces (Produces):**

```python
# config.py
@dataclass(frozen=True)
class Paths:
    data_dir: Path
    www_dir: Path
    import_roots: dict[str, Path]
    static_dir: Path
    dev_mode: bool
    @property
    def publish_dir(self) -> Path: ...        # www_dir / "sound-effects"
    @property
    def originals_dir(self) -> Path: ...      # data_dir / "originals"
    @property
    def previews_dir(self) -> Path: ...       # data_dir / "previews"
    @property
    def uploads_dir(self) -> Path: ...        # data_dir / "uploads"
    @property
    def database_path(self) -> Path: ...      # data_dir / "studio.db"
    @classmethod
    def from_env(cls) -> "Paths": ...  # defaults /data, /homeassistant/www, /media, /share,
                                        # static = package dir / "static" / "ui"; env overrides
                                        # SOUND_EFFECTS_DATA, SOUND_EFFECTS_WWW, SOUND_EFFECTS_DEV
def load_options(path: Path) -> dict[str, object]  # {} when missing/invalid

# errors.py
class StudioError(Exception): ...
class NotFoundError(StudioError): ...
class ConflictError(StudioError): ...
class InvalidError(StudioError): ...

# models.py (pydantic v2 BaseModel, model_config = ConfigDict(extra="forbid") on inputs)
class Season, SeasonCreate, SeasonUpdate
class Category, CategoryCreate, CategoryUpdate
class Profile, ProfileCreate, ProfileUpdate
class Recipe          # defaults identity; method is_identity() -> bool; validate_for(duration) -> None (raises InvalidError)
class OriginalInfo, Published, Sound, SoundUpdate, BulkSet, AuditionTarget, Settings
class SelectionEvent(sound_id: str, category_id: str, season_id: str, selected_at: str), SelectionBatch(events: list[SelectionEvent], max 500)
class Job(id, kind, sound_id, sound_title, status, progress, error, created_at, started_at, finished_at)
SoundStatus = Literal["processing", "ready", "rendering", "failed"]
def slugify(text: str) -> str   # lowercase ascii, accents stripped, non [a-z0-9] -> "_", trimmed, max 48; "" -> "item"
def utcnow_iso() -> str          # "2026-10-03T12:00:00Z"

# seasons.py
def season_matches(start: str | None, end: str | None, mmdd: str) -> bool
def resolve_calendar_season(seasons: Iterable[SeasonLike], day: date) -> str
class SeasonLike(Protocol): id: str; start: str | None; end: str | None; priority: int

# db.py
class Database:
    def __init__(self, path: Path) -> None   # opens sqlite3, WAL, foreign_keys=ON, row_factory Row, creates schema, seeds
    connection: sqlite3.Connection
    def transaction(self) -> ContextManager[sqlite3.Connection]
    def close(self) -> None

# repository.py
class Repository:
    def __init__(self, db: Database, on_catalog_change: Callable[[int], None] | None = None) -> None
    # seasons
    def list_seasons(self) -> list[Season]; def get_season(self, season_id: str) -> Season
    def create_season(self, data: SeasonCreate) -> Season; def update_season(self, season_id: str, data: SeasonUpdate) -> Season
    def delete_season(self, season_id: str) -> None
    # categories
    def list_categories(self) -> list[Category]; def get_category(self, category_id: str) -> Category
    def create_category(self, data: CategoryCreate) -> Category; def update_category(self, category_id: str, data: CategoryUpdate) -> Category
    def delete_category(self, category_id: str) -> None; def reorder_categories(self, ids: list[str]) -> list[Category]
    # profiles
    def list_profiles(self) -> list[Profile]; def get_profile(self, profile_id: str) -> Profile
    def create_profile(self, data: ProfileCreate) -> Profile
    def update_profile(self, profile_id: str, data: ProfileUpdate) -> tuple[Profile, list[str]]
    def delete_profile(self, profile_id: str) -> None
    def sounds_using_profile(self, profile_id: str) -> list[str]
    # sounds
    def list_sounds(self) -> list[Sound]; def get_sound(self, sound_id: str) -> Sound
    def create_sound(self, *, category_id: str, title: str, key: str, tags: list[str], seasons: list[str],
                     all_seasons: bool, recipe: Recipe, original: OriginalInfo | None) -> Sound
    def update_sound(self, sound_id: str, data: SoundUpdate) -> Sound
    def set_recipe(self, sound_id: str, recipe: Recipe) -> Sound
    def set_original(self, sound_id: str, original: OriginalInfo) -> Sound
    def set_status(self, sound_id: str, status: SoundStatus, error: str | None = None) -> Sound
    def set_published(self, sound_id: str, published: Published) -> Sound   # also status ready, error None
    def set_has_preview(self, sound_id: str, value: bool) -> None
    def delete_sound(self, sound_id: str) -> None
    def bulk_update(self, ids: list[str], data: BulkSet) -> int   # metadata only; profile handled by API layer
    def record_selections(self, events: list[SelectionEvent]) -> None
    # settings & catalog
    def get_settings(self) -> Settings; def update_settings(self, data: Settings) -> Settings
    def catalog_revision(self) -> int
    def catalog_document(self) -> dict[str, object]   # Catalog shape from the API reference
```

Rules the repository enforces (raise the listed error):
- Season `start`/`end` must both be `MM-DD` valid dates (`02-29` allowed) for non-regular seasons → `InvalidError`. Regular: only `name`, `color`, `icon` updatable; delete → `InvalidError`.
- Deleting a season removes its id from every sound's `seasons`; a sound left empty gets `["regular"]`.
- Category delete with sounds → `ConflictError`. Profile delete when used by any sound recipe or category default → `ConflictError`.
- `create_*` with existing id → `ConflictError`; unknown ids → `NotFoundError`; sound `seasons` must reference existing seasons and be non-empty unless `all_seasons` → `InvalidError`; `category_id` must exist → `InvalidError`; tags normalized with `slugify`, deduplicated, sorted.
- Every write to seasons, categories, or sounds (including `set_published`, `delete_sound`, `bulk_update`) increments `catalog_revision` in `meta` within the same transaction, then calls `on_catalog_change(revision)` after commit. `record_selections`, `set_status` to `processing|rendering`, settings, and profile writes do not bump.
- `catalog_document()` returns `{revision, generated_at, seasons, categories, sounds}` exactly per the Catalog type (sounds with `published` only).
- Seeds on empty DB: season `regular` (name "Regular", color `#64748b`, icon `mdi:calendar-blank`, builtin), the four profiles, category `general` ("General", icon `mdi:music-note`, color `#8b5cf6`, default_profile_id null), `meta.catalog_revision = 0`, settings defaults `{max_upload_mb: 100, max_duration_s: 600, audition_targets: [], media_base_url: ""}`.

Schema (`db.py`, `PRAGMA user_version = 1`):

```sql
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS seasons (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, color TEXT NOT NULL, icon TEXT NOT NULL,
  start TEXT, "end" TEXT, priority INTEGER NOT NULL DEFAULT 0, builtin INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS profiles (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, target_lufs REAL NOT NULL, true_peak REAL NOT NULL, lra REAL NOT NULL);
CREATE TABLE IF NOT EXISTS categories (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, icon TEXT NOT NULL, color TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '', sort_order INTEGER NOT NULL DEFAULT 0,
  default_profile_id TEXT REFERENCES profiles(id));
CREATE TABLE IF NOT EXISTS sounds (
  id TEXT PRIMARY KEY, category_id TEXT NOT NULL REFERENCES categories(id),
  title TEXT NOT NULL, key TEXT NOT NULL, tags TEXT NOT NULL DEFAULT '[]',
  seasons TEXT NOT NULL DEFAULT '["regular"]', all_seasons INTEGER NOT NULL DEFAULT 0,
  enabled INTEGER NOT NULL DEFAULT 1, notes TEXT NOT NULL DEFAULT '',
  original TEXT, recipe TEXT NOT NULL, published TEXT, status TEXT NOT NULL,
  error TEXT, selection_count INTEGER NOT NULL DEFAULT 0, last_selected_at TEXT,
  has_preview INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
```

Season calendar (`seasons.py`, also copied verbatim into the integration in Task 9):

```python
"""Yearly season calendar shared (by copy) with the sound_effects integration."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Protocol

REGULAR = "regular"


class SeasonLike(Protocol):
    id: str
    start: str | None
    end: str | None
    priority: int


def season_matches(start: str | None, end: str | None, mmdd: str) -> bool:
    """Return True when MM-DD falls inside an inclusive, possibly year-wrapping range."""
    if not start or not end:
        return False
    if start <= end:
        return start <= mmdd <= end
    return mmdd >= start or mmdd <= end


def resolve_calendar_season(seasons: Iterable[SeasonLike], day: date) -> str:
    """Pick the highest-priority season whose range contains the day, else regular."""
    mmdd = day.strftime("%m-%d")
    matches = [
        season
        for season in seasons
        if season.id != REGULAR and season_matches(season.start, season.end, mmdd)
    ]
    if not matches:
        return REGULAR
    matches.sort(key=lambda season: (-season.priority, season.id))
    return matches[0].id
```

- [ ] **Step 1: Write failing tests**

`tests/contract/test_season_cases.py` (studio half; Task 9 adds the integration half to the same file):

```python
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest

from sound_effects_studio.seasons import resolve_calendar_season as studio_resolve

CASES = json.loads(
    (Path(__file__).resolve().parents[2] / "contract" / "season_cases.json").read_text()
)


@dataclass
class _Season:
    id: str
    start: str | None
    end: str | None
    priority: int


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_studio_calendar(case: dict) -> None:
    seasons = [_Season(**season) for season in case["seasons"]]
    assert studio_resolve(seasons, date.fromisoformat(case["date"])) == case["expected"]
```

`tests/studio/test_repository.py` must cover (one test each): seeds present after init; `catalog_revision` starts at 0 and increments on create_category, update_season, set_published, delete_sound, bulk_update but not on record_selections or profile update; `on_catalog_change` called with the new revision after commit; category slug id derived from name ("Intro Entrada" → `intro_entrada`, "León Infinito" → `leon_infinito`); duplicate id → ConflictError; delete category with sounds → ConflictError; delete regular → InvalidError; deleting season `halloween` turns a sound with `["halloween"]` into `["regular"]`; invalid `13-40` start → InvalidError; profile delete while used → ConflictError; `update_profile` returns affected sound ids; tags normalized (`["ES", "es", " En "]` → `["en", "es"]`); `catalog_document()` excludes unpublished sounds and matches the Catalog key set; `Recipe().is_identity()` true and `Recipe(gain_db=1).is_identity()` false; `Recipe.validate_for(10)` rejects `trim_start >= trim_end`, `trim_end > duration + 0.05`, and `fade_in + fade_out > clip length`.

Example (write all similarly):

```python
import pytest

from sound_effects_studio.db import Database
from sound_effects_studio.errors import ConflictError, InvalidError
from sound_effects_studio.models import CategoryCreate, Recipe, SeasonCreate
from sound_effects_studio.repository import Repository

pytestmark = pytest.mark.studio


@pytest.fixture
def repo(paths) -> Repository:
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    return Repository(Database(paths.database_path))


def test_seeds(repo: Repository) -> None:
    assert [s.id for s in repo.list_seasons()] == ["regular"]
    assert {p.id for p in repo.list_profiles()} == {"standard", "loud", "soft", "voice"}
    assert [c.id for c in repo.list_categories()] == ["general"]
    assert repo.catalog_revision() == 0


def test_category_slug_and_revision(repo: Repository) -> None:
    seen: list[int] = []
    repo._on_catalog_change = seen.append  # type: ignore[attr-defined]
    category = repo.create_category(CategoryCreate(name="León Infinito"))
    assert category.id == "leon_infinito"
    assert repo.catalog_revision() == 1
    assert seen == [1]
    with pytest.raises(ConflictError):
        repo.create_category(CategoryCreate(name="León Infinito"))


def test_deleting_season_falls_back_to_regular(repo: Repository) -> None:
    repo.create_season(SeasonCreate(name="Halloween", start="10-01", end="10-31", priority=10))
    sound = repo.create_sound(
        category_id="general", title="Boo", key="boo.mp3", tags=[], seasons=["halloween"],
        all_seasons=False, recipe=Recipe(), original=None,
    )
    repo.delete_season("halloween")
    assert repo.get_sound(sound.id).seasons == ["regular"]


def test_regular_cannot_be_deleted(repo: Repository) -> None:
    with pytest.raises(InvalidError):
        repo.delete_season("regular")
```

- [ ] **Step 2: Run** `uv run pytest tests/studio tests/contract/test_season_cases.py -q` → FAIL (modules missing).
- [ ] **Step 3: Implement** the six modules to the interfaces above. Sound ids: `secrets.token_hex(6)`. JSON columns via `json.dumps(..., separators=(",", ":"))`. `Repository._on_catalog_change` attribute name is exactly `_on_catalog_change`.
- [ ] **Step 4: Run** `uv run pytest tests/studio tests/contract -q && uv run pyright && uv run ruff check . && uv run ruff format --check .` → PASS.
- [ ] **Step 5: Commit** `feat(studio): add models, season calendar, database and repository`.

## Task 3: Media pipeline (probe, loudness, filters, render)

**Model:** GPT-6-Luna. **Branch:** `track/studio`.

**Files:** Create `app/src/sound_effects_studio/media.py`; Test `tests/studio/test_media.py`.

**Interfaces:**
- Consumes: `models.Recipe`, `models.Profile`.
- Produces:

```python
FFMPEG = os.environ.get("SOUND_EFFECTS_FFMPEG", "ffmpeg")
FFPROBE = os.environ.get("SOUND_EFFECTS_FFPROBE", "ffprobe")
SUPPORTED_EXTENSIONS = frozenset({".mp3", ".wav", ".flac", ".ogg", ".opus", ".m4a", ".aac", ".webm", ".mp4", ".mov"})

class MediaError(Exception): ...

@dataclass(frozen=True)
class ProbeResult:
    format: str        # ffprobe format_name first token, e.g. "mp3", "wav"
    codec: str         # audio codec_name, e.g. "mp3", "pcm_s16le"
    duration: float
    sample_rate: int
    channels: int

@dataclass(frozen=True)
class LoudnessMeasurement:
    input_i: float; input_tp: float; input_lra: float; input_thresh: float; target_offset: float

async def probe(path: Path) -> ProbeResult                         # MediaError if no audio stream / ffprobe fails
async def measure_loudness(path: Path, *, trim_start: float = 0.0, trim_end: float | None = None,
                           profile: Profile | None = None) -> LoudnessMeasurement
def build_filter_chain(recipe: Recipe, duration: float, profile: Profile | None,
                       measured: LoudnessMeasurement | None) -> list[str]
def can_copy_verbatim(info: ProbeResult, recipe: Recipe) -> bool  # info.codec == "mp3" and recipe.is_identity()
async def render(src: Path, dst: Path, *, recipe: Recipe, duration: float, channels: int,
                 profile: Profile | None, on_progress: Callable[[float], None] | None = None,
                 timeout: float | None = None) -> None           # writes MP3 to dst; MediaError with stderr tail on failure
```

`build_filter_chain` exact output rules (tested as strings):
1. `end = recipe.trim_end if recipe.trim_end is not None else duration`. If `recipe.trim_start > 0` or `end < duration - 0.0005`: append `atrim=start={trim_start:.3f}:end={end:.3f}` then `asetpts=PTS-STARTPTS`.
2. If `profile and measured`: append `loudnorm=I={profile.target_lufs:g}:TP={profile.true_peak:g}:LRA={profile.lra:g}:measured_I={m.input_i:g}:measured_TP={m.input_tp:g}:measured_LRA={m.input_lra:g}:measured_thresh={m.input_thresh:g}:offset={m.target_offset:g}:linear=true`, then `aresample=44100`.
3. If `recipe.gain_db != 0`: append `volume={gain_db:.2f}dB`.
4. `clip = end - trim_start`. If `fade_in > 0`: `afade=t=in:st=0:d={fade_in:.3f}`. If `fade_out > 0`: `afade=t=out:st={max(0.0, clip - fade_out):.3f}:d={fade_out:.3f}`.
5. If `recipe.gain_db > 0 or profile is not None`: ceiling = `profile.true_peak if profile else -1.0`; append `alimiter=limit={10 ** (ceiling / 20):.4f}:level=0`.

`measure_loudness` runs `ffmpeg -hide_banner -nostats -i <path> -af "<atrim chain if any>,loudnorm=I=..:TP=..:LRA=..:print_format=json" -f null -` (profile defaults to −16/−1.5/11 when None) and parses the last `{...}` JSON block in stderr (values are strings; `-inf` → `-70.0`).

`render` command: `ffmpeg -hide_banner -nostats -y -i <src> -vn -map 0:a:0 [-af <comma-joined chain>] -ac <min(channels,2)> -ar 44100 -c:a libmp3lame -q:a 2 -progress pipe:1 <dst>`; when a profile is set, first call `measure_loudness` with the recipe trim to obtain `measured`. Progress = `out_time_ms / 1e6 / clip` clamped 0..1. Timeout default `max(60, 4 * duration)`; on timeout kill the process and raise `MediaError("render timed out")`.

- [ ] **Step 1: Failing tests** in `tests/studio/test_media.py` (all `async def`, `pytestmark = pytest.mark.studio`):
  - `test_probe_wav` (make_tone 3 s stereo → duration ≈ 3.0 ± 0.05, channels 2, sample_rate 44100, codec startswith "pcm").
  - `test_probe_rejects_non_audio` (write `b"not audio"` to `x.mp3` → `MediaError`).
  - `test_filter_chain_identity_is_empty` → `build_filter_chain(Recipe(), 3.0, None, None) == []`.
  - `test_filter_chain_full` with `Recipe(trim_start=0.5, trim_end=2.5, gain_db=2, fade_in=0.25, fade_out=0.5, profile_id="standard")`, profile standard, measured `(−30, −10, 5, −40, 0.5)` → exact list:
    `["atrim=start=0.500:end=2.500", "asetpts=PTS-STARTPTS", "loudnorm=I=-16:TP=-1.5:LRA=11:measured_I=-30:measured_TP=-10:measured_LRA=5:measured_thresh=-40:offset=0.5:linear=true", "aresample=44100", "volume=2.00dB", "afade=t=in:st=0:d=0.250", "afade=t=out:st=1.500:d=0.500", "alimiter=limit=0.8414:level=0"]`.
  - `test_filter_chain_negative_gain_no_limiter` → `Recipe(gain_db=-3)` gives `["volume=-3.00dB"]`.
  - `test_can_copy_verbatim` (mp3 identity true; wav identity false; mp3 with gain false).
  - `test_render_trim_and_fade_duration` (5 s tone, trim 1→3, fades → output probe duration 2.0 ± 0.06, codec mp3, sample_rate 44100).
  - `test_render_normalizes_two_levels_close_together` (tones at −30 dB and −8 dB volume, both rendered with profile standard; measured `input_i` of both outputs within 1.0 LU of −16 and of each other).
  - `test_render_mono_stays_mono` (mono tone → channels 1).
  - `test_render_failure_raises_media_error` (src is a text file → `MediaError`, dst not created).
  - `test_render_reports_progress` (callback receives a final value ≥ 0.9).
- [ ] **Step 2: Run** `uv run pytest tests/studio/test_media.py -q` → FAIL.
- [ ] **Step 3: Implement** `media.py` with `asyncio.create_subprocess_exec` (never a shell).
- [ ] **Step 4: Run** tests + pyright + ruff → PASS.
- [ ] **Step 5: Commit** `feat(studio): add ffmpeg probe, loudness measurement and render pipeline`.

## Task 4: Publisher, notifier, and job queue

**Model:** GPT-6.1-Sol. **Branch:** `track/studio`.

**Files:** Create `publisher.py`, `notifier.py`, `jobs.py`; Test `tests/studio/test_publisher.py`, `tests/studio/test_jobs.py`.

**Interfaces:**
- Consumes: `Paths`, `Repository`, `media.*`, models.
- Produces:

```python
# publisher.py
@dataclass
class WwwStatus:
    exists: bool
    created_by_app: bool
    served: bool | None = None   # filled by the app lifespan HTTP probe

class Publisher:
    def __init__(self, paths: Paths) -> None
    def ensure_dirs(self) -> WwwStatus            # creates www_dir if missing (created_by_app=True), publish_dir, data subdirs
    def temp_path(self, sound_id: str) -> Path    # publish_dir / f".tmp-{sound_id}-{token_hex(4)}.mp3"
    def commit(self, tmp: Path, sound_id: str, revision: int) -> str   # os.replace → f"{sound_id}-r{revision}.mp3"; returns filename
    def published_path(self, filename: str) -> Path
    def cleanup(self, sound_id: str, keep: set[int], older_than: timedelta = timedelta(hours=24)) -> list[str]
        # deletes f"{sound_id}-r{n}.mp3" with n not in keep and mtime older than older_than; also stale .tmp-{sound_id}-* files
    def remove_all(self, sound_id: str) -> None   # published files, original dir, preview
    def audition_copy(self, src: Path, sound_id: str) -> str   # copies to publish_dir/"_audition"/f"{sound_id}-{token_hex(4)}.mp3"; returns "/local/sound-effects/_audition/<name>"
    def cleanup_auditions(self, older_than: timedelta = timedelta(minutes=10)) -> None
    def storage_usage(self) -> dict[str, int]     # originals_bytes, published_bytes, previews_bytes

# notifier.py
class CatalogNotifier:
    def __init__(self, send: Callable[[int], Awaitable[None]], delay: float = 1.0) -> None
    def mark_changed(self, revision: int) -> None   # thread-safe; debounces; sends latest revision once
    async def flush(self) -> None                    # for tests: wait for pending send
    async def close(self) -> None

# jobs.py
class JobQueue:
    def __init__(self, repo: Repository, publisher: Publisher, paths: Paths) -> None
    async def start(self) -> None; async def stop(self) -> None
    def enqueue_import(self, sound_id: str) -> Job
    def enqueue_publish(self, sound_id: str) -> Job      # coalesces: replaces a queued (not running) publish for the same sound
    def enqueue_preview(self, sound_id: str, recipe: Recipe) -> Job
    def list_jobs(self) -> list[Job]                       # running/queued first, then last 50 finished newest first
    async def wait_idle(self, timeout: float = 60) -> None # test helper
```

Job behavior:
- **import**: `set_status(processing)`; locate the single file in `originals_dir/<sound_id>/`; `probe` → `set_original`; duration > `settings.max_duration_s` → failed "longer than N s"; if `can_copy_verbatim` → `shutil.copyfile` to `temp_path`, else `render` (profile = `get_profile(recipe.profile_id)` when set); `probe(tmp)` must succeed; `revision = (published.revision if published else 0) + 1`; `commit`; `measure_loudness(final)` (no trim, default profile targets) → `Published(revision, filename, duration=probe.duration, loudness_lufs=input_i, true_peak_db=input_tp, size, published_at, mime_type="audio/mpeg")`; `set_published`; `cleanup(sound_id, keep={revision, revision-1})`.
- **publish**: like import from the render step, always rendering (the identity recipe on an mp3 source copies verbatim); status `rendering` while running; on failure `set_status(failed, error)` and the previous `published` stays untouched; tmp removed.
- **preview**: render to `previews_dir/<sound_id>.mp3` (via tmp + replace); `set_has_preview(True)`; status unchanged; failure only marks the job failed.
- Every job catches `Exception`, stores `error` = last 400 chars of the message, and never kills the worker loop. One worker coroutine processes jobs FIFO.

- [ ] **Step 1: Failing tests** — `test_publisher.py`: ensure_dirs creates www and reports `created_by_app`; commit is atomic (existing published file untouched until replace, final name pattern); cleanup keeps `keep` set and recent files, deletes old (set mtime with `os.utime`); audition_copy path and cleanup; storage_usage sums. `test_jobs.py` (real ffmpeg, `JobQueue` started in fixture, `await queue.wait_idle()`): import mp3 identity → published bytes equal original bytes, status ready, revision 1, revision bumped in catalog; import wav → mp3 output, loudness filled; publish with trim → revision 2, r1 file still present, duration changed; publish failure (replace original file with garbage after import) → status failed, published still revision 1 and file exists; preview → `has_preview` true, status stays ready, catalog revision unchanged; coalescing (enqueue publish twice before start → one job); import over max duration → failed with message; notifier debounce (three `mark_changed` calls within delay → one send with latest revision).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** tests + pyright + ruff → PASS.
- [ ] **Step 5: Commit** `feat(studio): add atomic publisher, catalog notifier and render job queue`.

## Task 5: Auth, Supervisor client, v1 API, app factory

**Model:** Sonnet. **Branch:** `track/studio`.

**Files:** Create `auth.py`, `supervisor.py`, `api_v1.py`, `app.py`, `main.py`; Test `tests/studio/test_auth.py`, `tests/studio/test_api_v1.py`, `tests/studio/test_supervisor.py`.

**Interfaces:**

```python
# auth.py
INGRESS_PEER = "172.30.32.2"
class TokenStore:
    def __init__(self, path: Path) -> None     # creates token (secrets.token_urlsafe(32)) when missing, file mode 0600
    def get(self) -> str; def rotate(self) -> str; def masked(self) -> str   # "abcd…wxyz" (first 4 + "…" + last 4)
def require_ingress(request: Request) -> None   # 403 unless request.client.host == INGRESS_PEER or app.state.paths.dev_mode
def require_bearer(request: Request) -> None    # 401 unless "Authorization: Bearer <token>" matches (hmac.compare_digest)

# supervisor.py
class SupervisorClient:
    def __init__(self, token: str | None, base_url: str = "http://supervisor", client: httpx.AsyncClient | None = None) -> None
    @property
    def available(self) -> bool
    async def self_info(self) -> dict[str, Any]          # GET /addons/self/info → ["data"]
    async def core_config(self) -> dict[str, Any]        # GET /core/api/config
    async def core_info(self) -> dict[str, Any]          # GET /core/info → ["data"]
    async def network_info(self) -> dict[str, Any]       # GET /network/info → ["data"]
    async def publish_discovery(self, config: dict[str, Any]) -> str   # POST /discovery → data.uuid
    async def delete_discovery(self, uuid: str) -> None
    async def fire_event(self, event_type: str, data: dict[str, Any]) -> None   # POST /core/api/events/<type>
    async def call_service(self, domain: str, service: str, data: dict[str, Any]) -> None   # POST /core/api/services/<d>/<s>
    async def aclose(self) -> None
class SupervisorError(Exception): ...

# app.py
def create_app(paths: Paths, *, supervisor: SupervisorClient | None = None, start_background: bool = True) -> FastAPI
# app.state: paths, repo, publisher, jobs, tokens, supervisor, notifier, instance_id, www_status,
#            discovery_status {"status","message"}, media_base_url_effective (str)
```

Lifespan (when `start_background`): `publisher.ensure_dirs()`; `jobs.start()`; instance id from `/data/instance_id` (uuid4 hex, created once); if supervisor available: discovery (`self_info()["hostname"]`, delete previous uuid stored in `/data/discovery_uuid`, publish `{host, port: 8099, token, instance_id}`, store uuid; failures → `discovery_status = {"status": "failed", "message": str(e)}`), media base URL detection (`settings.media_base_url` if non-empty; else `core_config()["internal_url"]`; else `http://<first IPv4 of the primary interface in network_info, without prefix>:<core_info()["port"]>`; else `""`), served check (write `publish_dir/".probe"` and GET `http://homeassistant:8123/local/sound-effects/.probe` via httpx with 3 s timeout → `www_status.served` True/False; no supervisor → None); periodic task every 10 min: `publisher.cleanup_auditions()` and (once Task 7 exists) `app.state.uploads.purge_stale()`. Notifier sends `supervisor.fire_event("sound_effects_catalog_changed", {"revision": n})`, swallowing errors. On shutdown: stop jobs, close notifier and supervisor.

`api_v1.py` router (prefix `/api/v1`, dependency `require_bearer`):
- `GET /health` → `{"status": "ok", "version": __version__, "api_version": 1, "instance_id": ...}`.
- `GET /catalog` → `catalog_document()`, header `ETag: "rev-<revision>"`; `If-None-Match` equal → `304` empty body.
- `POST /selections` → validates `SelectionBatch` (max 500 events) → `repo.record_selections` → `204`.

`app.py` also: maps `NotFoundError`→404, `ConflictError`→409, `InvalidError`→422 via exception handlers (`{"detail": str(exc)}`); includes routers from `api_ui_organize`/`api_ui_sounds` when those modules exist (Tasks 6–7 add them; import them unconditionally once present); serves the SPA: `GET /` → `static_dir/index.html` (503 text "UI not built" if missing) and `/assets/*` static, both behind `require_ingress`.

`main.py`: `Paths.from_env()`, `load_options(Path("/data/options.json"))` for `log_level`, `SupervisorClient(os.environ.get("SUPERVISOR_TOKEN"))`, `uvicorn.run(create_app(...), host="0.0.0.0", port=8099, log_level=...)`.

- [ ] **Step 1: Failing tests** — use `fastapi.testclient.TestClient(create_app(paths, start_background=False))`; TestClient's peer is `testclient`, so ingress tests pass `client=("172.30.32.2", 50000)` via `TestClient(app, client=("172.30.32.2", 50000))` (Starlette ≥0.40 supports the `client` argument) or set `paths.dev_mode`. Cases: v1 without token → 401; wrong token → 401; health ok fields; catalog ETag and 304; selections increments `selection_count` and `last_selected_at`; UI root from non-ingress peer → 403; from ingress peer with no build → 503; TokenStore masked/rotate/persist and 0600 mode; SupervisorClient against `httpx.MockTransport` (discovery POST body and auth header, fire_event path, call_service path).
- [ ] **Step 2–4:** Run → FAIL → implement → PASS (+ pyright, ruff).
- [ ] **Step 5: Commit** `feat(studio): add auth, supervisor client, v1 API and app factory`.

## Task 6: UI API — organize, settings, state, token

**Model:** Sonnet. **Branch:** `track/studio`.

**Files:** Create `api_ui_organize.py`; Modify `app.py` (include router); Test `tests/studio/test_api_ui_organize.py`.

Endpoints exactly as listed in the Shared API Reference rows `state`, `token`, `token/rotate`, `settings`, `categories*`, `seasons*`, `profiles*` (including `apply`). Router prefix `/api/ui`, dependency `require_ingress`. `profiles/{id}/apply`: resolve target ids (`category_id` → all sounds in the category), for each: `set_recipe(recipe with profile_id=id)` then `jobs.enqueue_publish`; return `{queued}`. `state` builds `State` from app.state + `publisher.storage_usage()`. `PUT settings` validates `audition_targets` (unique ids, kind in enum, entity_id domain matches kind: `media_player.` or `script.`) and if `media_base_url` changed, recomputes `media_base_url_effective` (non-empty value wins; empty → re-run auto detection).

- [ ] **Step 1: Failing tests** (ingress TestClient): CRUD round-trips for each resource; 409 on category delete with sounds; 422 on bad season dates; 400/422 on deleting regular; `seasons/resolve?date=2026-10-15` with a Halloween season → `halloween`; profile PATCH returns affected ids; profile apply by category queues one job per sound (inspect `jobs.list_jobs()`); settings validation errors; `token` returns full token equal to `TokenStore.get()`; `state.api_token_masked` never equals the full token.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5: Commit** `feat(studio): add organize, settings and state endpoints`.

## Task 7: UI API — sounds, uploads, import, audition, jobs, audio

**Model:** GPT-6.1-Sol. **Branch:** `track/studio`.

**Files:** Create `uploads.py`, `importer.py`, `api_ui_sounds.py`; Modify `app.py`; Test `tests/studio/test_uploads.py`, `tests/studio/test_importer.py`, `tests/studio/test_api_ui_sounds.py`.

**Interfaces:**

```python
# uploads.py
CHUNK_SIZE = 4 * 1024 * 1024
class UploadStore:
    def __init__(self, paths: Paths, max_bytes: Callable[[], int]) -> None
    def create(self, filename: str, size: int) -> str     # InvalidError: unsupported extension (415 in API) or size > max (413)
    def write_chunk(self, upload_id: str, index: int, data: bytes) -> int   # returns total received bytes; rejects overflow
    def finish(self, upload_id: str, dest_dir: Path) -> Path  # verifies all bytes received, moves assembled file to dest_dir/<safe filename>, removes session
    def purge_stale(self, older_than: timedelta = timedelta(hours=6)) -> None

# importer.py
class ImportBrowser:
    def __init__(self, roots: dict[str, Path]) -> None
    def browse(self, virtual_path: str) -> dict[str, Any]     # shape of import/browse response
    def resolve(self, virtual_path: str) -> Path              # InvalidError when outside roots (.., symlinks escaping, unknown root)
```

`api_ui_sounds.py` endpoints exactly as listed in the Shared API Reference (sounds, uploads, import, audition, jobs, audio streams). Rules:
- Upload complete: `sound_id = token_hex(6)`; original saved under `originals_dir/<sound_id>/<safe filename>`; `title` default = filename stem with `-`/`_` → spaces, collapsed; `key` = original filename; recipe = `Recipe(profile_id=<resolved>)`; `create_sound(... status processing)`; `enqueue_import`.
- Import: each path → copy (never move) into `originals_dir/<sound_id>/`, same creation flow; unsupported files are skipped and reported by omission.
- `PUT recipe`: validate against `original.duration` (`Recipe.validate_for`), profile must exist, `set_recipe`, `enqueue_publish`.
- `POST preview`: validate, `enqueue_preview(sound_id, recipe)`.
- Bulk: `set` without `profile_id` key → `repo.bulk_update`; with `profile_id` key → also per-sound `set_recipe(profile_id=...)` + `enqueue_publish` (`queued` count).
- Delete: `publisher.remove_all` then `repo.delete_sound`.
- Audio streams: `FileResponse` (`audio/mpeg` for published/preview; guessed type for original); 404 when missing.
- Audition: target from settings (404 unknown); file = preview (when `use_preview` and exists) else published; `rel = publisher.audition_copy(file, id)`; `url = media_base_url_effective + rel` (422 "media base URL unknown" when empty); `media_player` → `call_service("media_player", "play_media", {"entity_id", "media_content_id": url, "media_content_type": "music", "announce": True})`; `script` → `call_service("script", "turn_on", {"entity_id", "variables": {"url", "duration", "title", "volume"}})`; supervisor unavailable → 503; returns `{ok: true, url}`.

- [ ] **Step 1: Failing tests** — chunked upload happy path (3 chunks of a generated wav) → sound processing then ready after `wait_idle`; oversize → 413; bad extension → 415; missing chunk → 422 on complete; import browse lists roots, rejects `media/../../etc` (422) and symlink escape; import copies file (source unchanged) and creates ready sound; PATCH metadata; recipe PUT queues publish and new revision appears; invalid recipe → 422; preview → `has_preview`; bulk tags add/remove; bulk profile queues; bulk delete removes files; audio stream returns bytes and supports `Range: bytes=0-99` (206); audition with fake SupervisorClient records the call payload; jobs list ordering.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5: Commit** `feat(studio): add sound, upload, import, audition and job endpoints`.

## Task 8: App packaging

**Model:** Sonnet. **Branch:** `track/studio`.

**Files:** Create `app/Dockerfile`, `app/.dockerignore`, `app/rootfs/usr/bin/sound-effects-studio`, `app/DOCS.md`, `app/CHANGELOG.md`, `app/translations/en.yaml`, `app/translations/es.yaml`, `app/icon.png` (128×128), `app/logo.png` (250×100); Test `tests/studio/test_app_package.py`.

```dockerfile
ARG BUILD_ARCH=amd64

# Vue SPA build stage; Node never reaches the final image. The Supervisor builds
# local Apps with app/ as the Docker context, so every COPY stays inside it.
FROM node:22-alpine AS ui
WORKDIR /ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci
COPY ui/ ./
RUN npm run build

FROM ghcr.io/home-assistant/${BUILD_ARCH}-base-python:3.13-alpine3.22

RUN apk add --no-cache ffmpeg \
    && pip install --no-cache-dir \
        "fastapi==0.115.14" "uvicorn[standard]==0.32.1" "httpx==0.28.1" "pydantic==2.11.7"

COPY src /opt/sound-effects-studio/src
COPY --from=ui /ui/dist /opt/sound-effects-studio/src/sound_effects_studio/static/ui
COPY rootfs /

ENV PYTHONPATH=/opt/sound-effects-studio/src
RUN chmod 0755 /usr/bin/sound-effects-studio

CMD ["/usr/bin/sound-effects-studio"]
```

`rootfs/usr/bin/sound-effects-studio`:

```sh
#!/bin/sh
# Started by the base image's s6 init; SUPERVISOR_TOKEN comes from the container env.
exec python3 -m sound_effects_studio.main
```

`translations/*.yaml` translate the `log_level` option (`configuration: log_level: {name, description}`). `DOCS.md`: what the App does, first steps (open panel → create categories → upload → install integration), the `/config/www` restart note, discovery/manual connection, backup notes. Icons: generate with Python/Pillow-free approach — write an SVG (violet rounded square, white waveform) and rasterize with `rsvg-convert` or `sips` if available; otherwise `ffmpeg -i icon.svg` is not suitable — use `qlmanage`/`sips` on macOS: `sips -s format png icon.svg --out icon.png` and resize with `sips -z`.

- [ ] **Step 1: Failing test** `test_app_package.py`: Dockerfile references `base-python:3.13-alpine3.22`, COPY sources exist (`src`, `rootfs`, `ui/package.json` once Track C lands — skip that assertion if `app/ui` absent), entry script executable bit set in git (`git ls-files -s` mode `100755`), translations parse and contain `log_level`, `icon.png` exists and is PNG (magic bytes).
- [ ] **Step 2–4:** FAIL → implement → PASS. If Docker is available (`docker info`), run `docker build --build-arg BUILD_ARCH=amd64 -f app/Dockerfile app` after Track C merge (Task 18 repeats this).
- [ ] **Step 5: Commit** `build(app): package Sound Effects Studio for the Supervisor`.

---

# Track B — Home Assistant integration

Tests in `tests/integration/`, marked `pytestmark = pytest.mark.integration`. `tests/integration/conftest.py`:

```python
"""Fixtures for the sound_effects integration tests."""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Make custom_components/ discoverable."""


@pytest.fixture
def catalog_payload() -> dict[str, Any]:
    def sound(sid: str, category: str, seasons: list[str], tags: list[str] | None = None,
              all_seasons: bool = False, enabled: bool = True) -> dict[str, Any]:
        return {
            "id": sid, "category_id": category, "title": sid.title(), "key": f"{sid}.mp3",
            "tags": tags or [], "seasons": seasons, "all_seasons": all_seasons, "enabled": enabled,
            "published": {"revision": 1, "filename": f"{sid}-r1.mp3", "duration": 2.5,
                          "mime_type": "audio/mpeg"},
        }

    return {
        "revision": 7,
        "generated_at": "2026-10-03T12:00:00Z",
        "seasons": [
            {"id": "regular", "name": "Regular", "color": "#64748b", "icon": "mdi:calendar-blank",
             "start": None, "end": None, "priority": 0},
            {"id": "halloween", "name": "Halloween", "color": "#f97316", "icon": "mdi:halloween",
             "start": "10-01", "end": "10-31", "priority": 10},
        ],
        "categories": [
            {"id": "intro", "name": "Intro entrada", "icon": "mdi:door-open", "color": "#8b5cf6",
             "description": "", "sort_order": 0},
            {"id": "lion", "name": "León", "icon": "mdi:paw", "color": "#eab308",
             "description": "", "sort_order": 1},
            {"id": "bath", "name": "Baños", "icon": "mdi:bullhorn", "color": "#22c55e",
             "description": "", "sort_order": 2},
        ],
        "sounds": [
            sound("fox", "intro", ["regular"]), sound("universal", "intro", ["regular"]),
            sound("pirates", "intro", ["regular"]), sound("boo", "intro", ["halloween"]),
            sound("roar", "lion", ["regular"], all_seasons=True),
            sound("bath_es", "bath", ["regular"], tags=["es"]),
            sound("bath_en", "bath", ["regular"], tags=["en"]),
            sound("off", "intro", ["regular"], enabled=False),
        ],
    }
```

## Task 9: Pure modules — catalog, seasons, selection

**Model:** GPT-6-Luna. **Branch:** `track/integration`.

**Files:** Create `custom_components/sound_effects/{const,catalog,seasons,selection}.py`; Test `tests/integration/test_catalog.py`, `tests/integration/test_selection.py`, `tests/integration/test_seasons.py`; Modify `tests/contract/test_season_cases.py` (add integration half).

**Interfaces (Produces):**

```python
# const.py
DOMAIN = "sound_effects"
EVENT_CATALOG_CHANGED = "sound_effects_catalog_changed"
EVENT_SELECTED = "sound_effects_selected"
CONF_HOST, CONF_PORT, CONF_TOKEN = "host", "port", "token"
CONF_PUBLIC_BASE_URL, CONF_SEASON_ENTITY, CONF_SCAN_INTERVAL = "public_base_url", "season_entity", "scan_interval"
DEFAULT_PORT = 8099
DEFAULT_SCAN_INTERVAL = 30
PUBLISHED_PATH_PREFIX = "/local/sound-effects/"
STORAGE_VERSION = 1
REGULAR = "regular"

# catalog.py
@dataclass(frozen=True) class SeasonDef: id: str; name: str; color: str; icon: str; start: str | None; end: str | None; priority: int
@dataclass(frozen=True) class CategoryDef: id: str; name: str; icon: str; color: str; description: str; sort_order: int
@dataclass(frozen=True) class PublishedDef: revision: int; filename: str; duration: float; mime_type: str
@dataclass(frozen=True) class SoundDef: id: str; category_id: str; title: str; key: str; tags: tuple[str, ...]; seasons: tuple[str, ...]; all_seasons: bool; enabled: bool; published: PublishedDef
@dataclass(frozen=True)
class Catalog:
    revision: int; seasons: tuple[SeasonDef, ...]; categories: tuple[CategoryDef, ...]; sounds: tuple[SoundDef, ...]
    def find_category(self, ref: str) -> CategoryDef | None   # id exact, else casefold id/name
    def find_season(self, ref: str) -> SeasonDef | None       # same rule
EMPTY_CATALOG: Catalog   # revision 0, seasons (regular only), no categories/sounds
def parse_catalog(data: Mapping[str, Any]) -> Catalog         # ValueError on missing/invalid fields

# seasons.py — verbatim copy of the studio seasons.py (season_matches, resolve_calendar_season, REGULAR, SeasonLike) plus:
class UnknownSeasonError(ValueError): ...
def resolve_effective_season(catalog: Catalog, day: date, *, action_season: str | None,
                             override: str | None, entity_state: str | None) -> tuple[str, str]
    # returns (season_id, source) with source in {"action","override","entity","calendar","default"}
    # action_season unknown → UnknownSeasonError; override unknown → ignored; entity_state unknown/"unknown"/"unavailable"/"" → ignored
    # calendar result "regular" with no matching range → source "default"

# selection.py
@dataclass
class BagState:
    remaining: list[str]; played: list[str]; last: str | None
    def to_dict(self) -> dict[str, Any]; @classmethod def from_dict(cls, data: Mapping[str, Any]) -> "BagState"
class NoEligibleSoundError(Exception): ...
@dataclass(frozen=True)
class SelectionOutcome:
    sound: SoundDef; season_id: str; requested_season: str; season_fallback: bool; bag_key: str; bag: BagState
def bag_key(category_id: str, season_id: str, tags: Iterable[str]) -> str   # f"{category}|{season}|{','.join(sorted(set(tags)))}"
def eligible_sounds(catalog: Catalog, category_id: str, season_id: str, tags: Iterable[str]) -> list[SoundDef]
def draw(bag: BagState, eligible_ids: Sequence[str], rng: random.Random) -> tuple[str, BagState]
def select(catalog: Catalog, *, category_id: str, season_id: str, tags: Iterable[str],
           bags: Mapping[str, BagState], rng: random.Random) -> SelectionOutcome
    # tries season_id; if no eligible and season_id != REGULAR tries REGULAR (season_fallback=True);
    # tags never relaxed; raises NoEligibleSoundError; does not mutate `bags` (caller stores outcome.bag)
```

`draw` implementation (binding):

```python
def draw(bag: BagState, eligible_ids: Sequence[str], rng: random.Random) -> tuple[str, BagState]:
    eligible = list(dict.fromkeys(eligible_ids))
    if not eligible:
        raise NoEligibleSoundError("no eligible sound")
    members = set(eligible)
    remaining = [sid for sid in bag.remaining if sid in members]
    played = [sid for sid in bag.played if sid in members]
    for sid in eligible:
        if sid not in remaining and sid not in played:
            remaining.append(sid)
    if not remaining:
        remaining = [sid for sid in eligible if sid != bag.last] or eligible[:]
        played = []
    pick = rng.choice(remaining)
    remaining = [sid for sid in remaining if sid != pick]
    return pick, BagState(remaining=remaining, played=[*played, pick], last=pick)
```

- [ ] **Step 1: Failing tests** — catalog parse round-trip from `catalog_payload`, `find_category("león")` by name casefold, parse rejects missing `sounds`; season precedence table (action > override > entity > calendar > default; entity state "Halloween" matches by name; unknown action raises; override "nope" ignored); contract cases for the integration resolver (append to `tests/contract/test_season_cases.py` a `test_integration_calendar` parametrized the same way importing `custom_components.sound_effects.seasons.resolve_calendar_season`); selection: eligible excludes disabled and other categories, tags subset (`["es"]` → only bath_es), all_seasons sound eligible in halloween; first N draws over N ids are a permutation; across 200 rounds with seeded rng the first pick of a round never equals the previous last (N ≥ 2); single sound repeats; newly added id joins the current round; removed id disappears; halloween with no halloween sounds in category `lion`… (roar is all_seasons → no fallback); category `bath` in halloween → fallback to regular with `season_fallback` True and `requested_season` "halloween"; tags never relaxed (`["fr"]` → NoEligibleSoundError); `select` does not mutate the input mapping.
- [ ] **Step 2–4:** FAIL → implement → PASS (`uv run pytest tests/integration/test_catalog.py tests/integration/test_seasons.py tests/integration/test_selection.py tests/contract -q`, pyright, ruff).
- [ ] **Step 5: Commit** `feat(integration): add catalog model, season resolution and shuffle-bag selection`.

## Task 10: Client, config flow, setup, coordinator, snapshot

**Model:** GPT-6.1-Sol. **Branch:** `track/integration`.

**Files:** Create `api.py`, `coordinator.py`, `config_flow.py`, `__init__.py`, `translations/en.json`, `translations/es.json` (config + options sections); Modify `manifest.json` only if needed; Test `tests/integration/test_api.py`, `tests/integration/test_config_flow.py`, `tests/integration/test_init.py`.

**Interfaces:**

```python
# api.py
class StudioConnectionError(Exception): ...
class StudioAuthError(StudioConnectionError): ...
@dataclass(frozen=True)
class CatalogResponse:
    data: dict[str, Any] | None   # None when 304
    etag: str | None
class StudioClient:
    def __init__(self, session: aiohttp.ClientSession, host: str, port: int, token: str) -> None
    async def health(self) -> dict[str, Any]
    async def catalog(self, etag: str | None = None) -> CatalogResponse
    async def post_selections(self, events: list[dict[str, Any]]) -> None
    # 10 s timeout; 401/403 → StudioAuthError; network/5xx → StudioConnectionError

# coordinator.py
@dataclass
class StudioState:
    catalog: Catalog; connected: bool; last_sync: datetime | None; app_version: str | None
class SoundEffectsCoordinator(DataUpdateCoordinator[StudioState]):
    def __init__(self, hass, entry, client: StudioClient, snapshot: Store[dict[str, Any]]) -> None
    async def async_load_snapshot(self) -> bool      # loads persisted raw catalog → self.data; True when loaded
    # _async_update_data: health (for app_version) + catalog(etag); on 200 parse, persist raw dict via
    # snapshot.async_save, keep etag; on 304 keep catalog; on StudioConnectionError: if a catalog exists
    # return StudioState(catalog, connected=False, ...) else raise UpdateFailed; StudioAuthError →
    # ConfigEntryAuthFailed
```

`__init__.py`:
- `async_setup(hass, config)`: registers services (Task 11 provides `async_register_services(hass)`; until then define a no-op placeholder function in `services.py` that Task 11 replaces — create `services.py` with `async def async_register_services(hass: HomeAssistant) -> None: return None` in this task).
- `async_setup_entry`: build client from `entry.data`, `Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}.catalog")`, coordinator; `had_snapshot = await coordinator.async_load_snapshot()`; `await coordinator.async_refresh()`; if `not coordinator.last_update_success and not had_snapshot` → `raise ConfigEntryNotReady`; `entry.runtime_data = SoundEffectsRuntime(client, coordinator, manager=None)` (Task 11 fills manager); listen to `EVENT_CATALOG_CHANGED` → `coordinator.async_request_refresh()` (unsub via `entry.async_on_unload`); update interval from options; options update listener reloads entry; forward platforms `[]` for now (Task 12 sets `[Platform.SENSOR, Platform.SELECT, Platform.BINARY_SENSOR]`).
- `async_unload_entry`: unload platforms.
- `SoundEffectsRuntime` dataclass in `__init__.py`: `client`, `coordinator`, `manager: SoundEffectsManager | None`. `type SoundEffectsConfigEntry = ConfigEntry[SoundEffectsRuntime]`.

`config_flow.py`:
- `async_step_user`: form host (default `""`), port (8099), token; validate with `StudioClient.health()`; errors `cannot_connect`, `invalid_auth`; `await self.async_set_unique_id(health["instance_id"])`; `_abort_if_unique_id_configured(updates=...)`; title "Sound Effects Studio".
- `async_step_hassio(discovery_info: HassioServiceInfo)`: config = `discovery_info.config`; set unique id = `config["instance_id"]`; `_abort_if_unique_id_configured(updates={host, port, token})`; store pending; `async_step_hassio_confirm` shows confirm form (`description_placeholders={"addon": discovery_info.name}`), validates health, creates entry.
- `OptionsFlow` (`async_get_options_flow`): `public_base_url` (str, optional, default current or `""`), `season_entity` (EntitySelector domains `sensor`, `input_select`, `select`, `input_text`; optional), `scan_interval` (NumberSelector 10–3600, default 30).
- Translations en/es for config (user, hassio_confirm), errors, aborts (`already_configured`, `cannot_connect`), options.

- [ ] **Step 1: Failing tests** — `test_api.py` with `aioclient_mock` (health ok, 401 → StudioAuthError, catalog 304 returns data None, timeout → StudioConnectionError, bearer header present); `test_config_flow.py`: user success creates entry with unique id; cannot_connect; invalid_auth; hassio discovery → confirm → entry; hassio rediscovery with existing unique id updates token and aborts `already_configured`; options flow stores values; `test_init.py`: setup with Studio online loads catalog and persists snapshot (`hass_storage` contains key); setup with Studio offline and stored snapshot (prefill `hass_storage`) succeeds with `connected False`; offline without snapshot → `ConfigEntryState.SETUP_RETRY`; firing `sound_effects_catalog_changed` triggers a refetch (aioclient_mock call count increases); 304 path keeps catalog; unload works.
- [ ] **Step 2–4:** FAIL → implement → PASS (+ pyright, ruff).
- [ ] **Step 5: Commit** `feat(integration): add studio client, config flow, coordinator and offline snapshot`.

## Task 11: Selection manager and actions

**Model:** GPT-6.1-Sol. **Branch:** `track/integration`.

**Files:** Create `manager.py`, `services.yaml`, `icons.json` (services section); Replace `services.py`; Modify `__init__.py` (create manager), translations (services + exceptions); Test `tests/integration/test_services.py`, `tests/integration/test_manager.py`.

**Interfaces:**

```python
# manager.py
class SoundEffectsManager:
    def __init__(self, hass: HomeAssistant, entry: SoundEffectsConfigEntry,
                 coordinator: SoundEffectsCoordinator, rng: random.Random | None = None) -> None
    async def async_load(self) -> None          # history Store f"{DOMAIN}.{entry_id}.history": {"bags": {...}, "last": {category_id: response}, "override": season_id|None}
    @property
    def override_season(self) -> str | None
    async def async_set_override(self, season_id: str | None) -> None   # persists; notifies listeners
    def active_season(self) -> tuple[str, str]   # resolve_effective_season(catalog, dt_util.now().date(), action_season=None, override, entity_state)
    def last_selection(self, category_id: str) -> dict[str, Any] | None
    def available_count(self, category_id: str) -> int   # eligible sounds for the active season (with regular fallback)
    async def async_select(self, *, category: str, tags: list[str] | None = None,
                           season: str | None = None, dry_run: bool = False) -> dict[str, Any]
    async def async_reset_history(self, category: str | None = None) -> int   # number of bags cleared
    @callback
    def async_add_listener(self, update: Callable[[], None]) -> Callable[[], None]
    def base_url(self) -> str   # options public_base_url or get_url(hass, allow_external=False, prefer_external=False) or ""
```

`async_select` flow under `asyncio.Lock`: find category (`ServiceValidationError(translation_key="unknown_category")`); resolve season (`UnknownSeasonError` → `ServiceValidationError(translation_key="unknown_season")`); `selection.select(...)` (`NoEligibleSoundError` → `ServiceValidationError(translation_key="no_eligible_sound", translation_placeholders={"category": ...})`); build response:

```python
{
    "sound_id": s.id, "key": s.key, "title": s.title, "category": s.category_id,
    "tags": list(s.tags), "season": outcome.season_id, "requested_season": outcome.requested_season,
    "season_fallback": outcome.season_fallback,
    "path": f"/local/sound-effects/{s.published.filename}",
    "url": f"{self.base_url().rstrip('/')}/local/sound-effects/{s.published.filename}",
    "duration": s.published.duration, "revision": s.published.revision,
    "mime_type": s.published.mime_type,
}
```

Unless `dry_run`: store `outcome.bag` under `outcome.bag_key`, set `last[category_id] = {**response, "selected_at": now_iso}`, `store.async_delay_save(..., 1.0)`, fire `EVENT_SELECTED` with the response, notify listeners, and schedule (`hass.async_create_background_task`) `client.post_selections([{sound_id, category_id, season_id, selected_at}])` ignoring errors. The selection path never awaits network I/O.

`services.py` — `async_register_services(hass)` registers (once) with `vol` schemas:
- `select`: `category` str required, `tags` list[str] optional (also accept comma string), `season` str optional, `dry_run` bool default False; `supports_response=SupportsResponse.OPTIONAL`; returns the response dict when `call.return_response` else None (still performs selection).
- `reset_history`: `category` optional → `{"cleared": n}` (`SupportsResponse.OPTIONAL`).
- `refresh`: forces `coordinator.async_refresh()`.
- Resolves the single loaded entry; none loaded → `ServiceValidationError(translation_key="not_loaded")`.

`services.yaml` with selectors (`text` for category/season, `text` multiple for tags, `boolean` for dry_run); translations en/es for services, fields, and exceptions (`unknown_category`, `unknown_season`, `no_eligible_sound`, `not_loaded`); `icons.json` services: select `mdi:dice-multiple`, reset_history `mdi:history`, refresh `mdi:refresh`.

- [ ] **Step 1: Failing tests** — select returns full key set and URL with configured base URL; shuffle across service calls covers all intro sounds before repeating (3 calls → 3 distinct of fox/universal/pirates); history persists across reload (`hass_storage`); dry_run doesn't change history nor fire event; event fired with payload; override select → halloween picks `boo`; season param "Halloween" by name; tags `es` only bath_es; fallback flags; unknown category/season/no eligible raise `ServiceValidationError` with the translation keys; reset_history clears; selection works with Studio offline (snapshot only, aioclient raising); post_selections called in background (assert aioclient_mock POST recorded after `await hass.async_block_till_done()`); `return_response=False` path works.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5: Commit** `feat(integration): add selection manager and select/reset/refresh actions`.

## Task 12: Entities, diagnostics, brand

**Model:** Sonnet. **Branch:** `track/integration`.

**Files:** Create `entity.py`, `sensor.py`, `select.py`, `binary_sensor.py`, `diagnostics.py`, `brand/icon.png`, `brand/icon.svg`; Modify `__init__.py` (platforms), `icons.json` (entities), translations (entity names/states); Test `tests/integration/test_entities.py`, `tests/integration/test_diagnostics.py`.

Entities (all `_attr_has_entity_name = True`, one device "Sound Effects Studio" `entry_type=DeviceEntryType.SERVICE`, `identifiers={(DOMAIN, entry.entry_id)}`, `sw_version` = app version):
- `SoundEffectsActiveSeasonSensor` — unique_id `{entry_id}_active_season`, translation_key `active_season`, state = season id, attributes `name`, `source`, `color`; updates on manager listener, coordinator update, `async_track_time_change(hour=0, minute=0, second=5)`, and `async_track_state_change_event` on the configured season entity.
- `SoundEffectsSeasonOverrideSelect` — unique_id `{entry_id}_season_override`, translation_key `season_override`, options `["Auto", *season names]`; `current_option` from `manager.override_season` (name), `async_select_option` → `manager.async_set_override(id or None)`; options refresh on catalog change (an override pointing at a deleted season reads as "Auto").
- `SoundEffectsCategorySensor` per category — unique_id `{entry_id}_category_{category_id}`, name = category name (`_attr_name`), icon from category (`mdi:` string), state = last title or None, attributes `category_id, sound_id, key, url, duration, season, selected_at, available`. A platform-level listener on coordinator updates adds entities for new categories and removes registry entries for deleted ones (`er.async_get(hass).async_remove(entity_id)`).
- `SoundEffectsConnectedBinarySensor` — unique_id `{entry_id}_connected`, device_class `connectivity`, entity_category `diagnostic`, `is_on = coordinator.data.connected`, attributes `catalog_revision`, `last_sync`, `app_version`.
- `diagnostics.py`: `async_get_config_entry_diagnostics` returns entry data with `token` redacted (`async_redact_data`), options, catalog revision and counts, bag keys with sizes, connection state.
- `brand/icon.svg` + `icon.png` (256×256), same artwork as the App icon.

- [ ] **Step 1: Failing tests** — entities created with expected entity_ids (`sensor.sound_effects_studio_active_season`, `select.sound_effects_studio_season_override`, `sensor.sound_effects_studio_intro_entrada` or per translation — assert via unique_id lookups in the entity registry, not hardcoded ids), override changes active season sensor to halloween with source override, category sensor updates after a `select` call, new category appears after catalog refresh, removed category entity removed, connectivity off when Studio offline, diagnostics redacts token.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5: Commit** `feat(integration): add season, override, category and connectivity entities`.

---

# Track C — Studio UI (`app/ui`)

Stack: `vue@^3.5`, `vue-router@^4.5`, `wavesurfer.js@^7.10`, `@mdi/js@^7.4`; dev: `vite@^6`, `@vitejs/plugin-vue@^5`, `tailwindcss@^4`, `@tailwindcss/vite@^4`, `typescript@^5.7`, `vue-tsc@^2.2`, `vitest@^3`, `happy-dom@^16`, `@vue/test-utils@^2.4`. Scripts: `dev`, `build` (`vue-tsc --noEmit && vite build`), `test:unit` (`vitest run`). `vite.config.ts`: `base: "./"`, alias `@` → `src`, `build.outDir: "dist"`, dev proxy `/api` → `http://localhost:8099`. Dev against a local Studio: `SOUND_EFFECTS_DEV=1 SOUND_EFFECTS_DATA=/tmp/sfx/data SOUND_EFFECTS_WWW=/tmp/sfx/www uv run python -m sound_effects_studio.main`.

UX rules for every view: touch targets ≥ 44 px; no horizontal page scroll at 360 px; focus-visible rings; every async action shows pending state and errors inline (`role="alert"`); destructive actions use `ConfirmDialog`; empty states explain the next step with a primary action; text from i18n only.

## Task 13: UI foundation

**Model:** Sonnet. **Branch:** `track/ui`.

**Files:** Create `app/ui/{package.json,package-lock.json,index.html,tsconfig.json,vite.config.ts,vitest.config.ts,.gitignore}`, `src/{main.ts,App.vue,router.ts,style.css}`, `src/api/{client.ts,types.ts}`, `src/i18n/{index.ts,en.ts,es.ts}`, `src/lib/{format.ts,recipe.ts,filters.ts}`, `src/composables/{useStudio.ts,useJobs.ts,usePlayer.ts,useToast.ts}`, `src/components/{Icon.vue,NavBar.vue,Sheet.vue,ConfirmDialog.vue,EmptyState.vue,JobTray.vue,ToastStack.vue,SeasonBadge.vue,StatusPill.vue}`, placeholder views `src/views/{LibraryView,UploadView,OrganizeView,SystemView,SoundEditorView}.vue` (heading + EmptyState); Tests `src/**/*.spec.ts`.

**Interfaces (Produces):**

```ts
// api/types.ts — exactly the Shared API Reference types, exported.
// api/client.ts
export class ApiError extends Error { status: number; detail: string }
export async function api<T>(path: string, init?: RequestInit & { json?: unknown }): Promise<T>
  // path relative, e.g. "api/ui/sounds"; JSON body via `json`; parses {detail}; 204 → undefined
export const ui = {
  state: () => api<State>("api/ui/state"),
  token: () => api<{ token: string }>("api/ui/token"),
  rotateToken: () => api<{ api_token_masked: string }>("api/ui/token/rotate", { method: "POST" }),
  settings: { get: ..., put: (s: Settings) => ... },
  categories: { list, create, update(id, patch), remove(id), reorder(ids) },
  seasons: { list, create, update(id, patch), remove(id), resolve(date) },
  profiles: { list, create, update(id, patch), remove(id), apply(id, body) },
  sounds: { list, get(id), update(id, patch), putRecipe(id, recipe), preview(id, recipe), remove(id),
            bulk(body), bulkDelete(ids), audition(id, body) },
  uploads: { create(filename, size), chunk(id, index, blob), complete(id, body) },
  importer: { browse(path), run(body) },
  jobs: () => api<Job[]>("api/ui/jobs"),
}
export const audioUrl = (id: string, kind: "original" | "preview" | "published", bust?: string | number) => string
  // `api/ui/sounds/${id}/${kind}` + (bust ? `?v=${bust}` : "")

// i18n
export type Locale = "es" | "en"
export function useI18n(): { t: (key: MessageKey, params?: Record<string, string | number>) => string;
                             locale: Ref<Locale>; setLocale(l: Locale): void }
  // default from navigator.language ("es*" → es else en); persisted in localStorage "sfx-locale" (try/catch)
// en.ts exports `en` object; es.ts exports `es: Record<keyof typeof en, string>` (type-enforced completeness)

// lib/format.ts
export function formatDuration(seconds: number): string        // 2.5 → "0:02.5"; 75.04 → "1:15.0"
export function formatLufs(value: number | null): string        // -16.04 → "−16.0 LUFS"; null → "—"
export function formatDb(value: number): string                  // 2 → "+2.0 dB"; -3 → "−3.0 dB"; 0 → "0 dB"
export function formatBytes(bytes: number): string              // 1536 → "1.5 KB"
export function formatDateTime(iso: string | null, locale: Locale): string

// lib/recipe.ts
export const IDENTITY: Recipe
export function isIdentity(r: Recipe): boolean
export function clipLength(r: Recipe, duration: number): number
export function validateRecipe(r: Recipe, duration: number): string[]   // i18n keys of problems
export function clampRecipe(r: Recipe, duration: number): Recipe          // keeps values in range, trim_end ≤ duration
export function recipesEqual(a: Recipe, b: Recipe): boolean

// lib/filters.ts
export type LibraryFilter = { categoryId: string | null; seasonId: string | null; tag: string | null; query: string; status: SoundStatus | null }
export function filterSounds(sounds: Sound[], f: LibraryFilter): Sound[]   // query matches title/key/tags, accent-insensitive
export function loudnessSpread(sounds: Sound[]): { min: number; max: number; spread: number } | null

// composables
export function useStudio(): { state, categories, seasons, profiles, sounds (Refs), loading, error,
  refresh(): Promise<void>, refreshSounds(): Promise<void>, categoryById(id), seasonById(id), profileById(id) }
  // module-level shared reactive store; refresh loads state+categories+seasons+profiles+sounds in parallel
export function useJobs(): { jobs: Ref<Job[]>; active: ComputedRef<Job[]>; start(): void; stop(): void }
  // polls every 1500 ms while any job is active, else every 10 s; when a job finishes calls useStudio().refreshSounds()
export function usePlayer(): { currentId: Ref<string | null>; playing: Ref<boolean>; toggle(id: string, url: string): void; stop(): void }
  // single shared HTMLAudioElement
export function useToast(): { push(message: string, kind?: "info" | "success" | "error"): void; toasts: Ref<...> }
```

Layout (`App.vue`): `NavBar` renders a left sidebar (≥ md: logo "Sound Effects", items Library `mdiMusicBoxMultiple`, Upload `mdiUpload`, Organize `mdiShapeOutline`, System `mdiCog`, language switch) and a fixed bottom tab bar (< md, same items, safe-area padding). Header shows view title and `JobTray` (badge with active job count; expands to a list with progress bars). Routes (hash history): `/` Library, `/upload`, `/organize`, `/system`, `/sounds/:id` (Library stays mounted underneath; the editor renders in `Sheet`).

`style.css` (Tailwind 4 `@theme`):

```css
@import "tailwindcss";

@theme {
  --color-ground: #0b0c10;
  --color-surface: #13151c;
  --color-raised: #1b1e28;
  --color-hover: #242836;
  --color-line: #2a2f3d;
  --color-ink: #eceef4;
  --color-muted: #9aa1b2;
  --color-accent: #8b5cf6;
  --color-accent-soft: #8b5cf633;
  --color-accent-ink: #ffffff;
  --color-ok: #34d399;
  --color-warn: #fbbf24;
  --color-danger: #f87171;
  --radius-panel: 0.875rem;
}
```

plus utilities `btn`, `btn-primary`, `btn-ghost`, `btn-danger`, `field`, `panel`, `chip`, `chip-active` (patterns as in clips-manager), `body { background: var(--color-ground); color: var(--color-ink); }`, `:focus-visible` accent outline, `@media (prefers-reduced-motion)` disables transitions.

`Sheet.vue`: props `open`, `title`; full-screen on < md, right drawer (max-w-2xl) ≥ md; traps focus, Esc closes (emits `close`), body scroll lock. `ConfirmDialog.vue`: `useConfirm()` promise API `confirm({title, message, confirmLabel, danger}) => Promise<boolean>`.

- [ ] **Step 1: Failing tests** — `format.spec.ts` (examples above), `recipe.spec.ts` (identity, clipLength with null trim_end, validate errors: start ≥ end, fades too long, gain out of range), `filters.spec.ts` (accent-insensitive "leon" matches "León", category/season/tag/status filters, loudnessSpread ignores nulls), `i18n.spec.ts` (es has every en key and no extras; params interpolation `{n}`), `client.spec.ts` (mock `fetch`: relative path kept, JSON body + content-type, `{detail}` → ApiError, 204 → undefined).
- [ ] **Step 2:** `npm --prefix app/ui run test:unit` → FAIL. **Step 3:** implement. **Step 4:** `npm --prefix app/ui run test:unit && npm --prefix app/ui run build` → PASS.
- [ ] **Step 5: Commit** `feat(ui): add Studio UI foundation, layout, i18n and API client`.

## Task 14: Library view

**Model:** GPT-6-Luna. **Branch:** `track/ui`.

**Files:** Modify `src/views/LibraryView.vue`; Create `src/components/{CategoryChips.vue,SoundItem.vue,BulkBar.vue,LoudnessStrip.vue,TagEditor.vue,SeasonPicker.vue,ProfilePicker.vue}`; Tests `src/components/{CategoryChips,SoundItem,BulkBar}.spec.ts`.

Behavior:
- Toolbar: search field (debounced 150 ms), season filter select, tag filter select (tags from all sounds), status filter; filter state kept in the route query (`?c=&s=&t=&q=`).
- `CategoryChips`: "All" + one chip per category (icon, color dot, count); horizontally scrollable with snap on phones; active chip uses `chip-active`.
- `LoudnessStrip` (shown when a category is selected and ≥ 2 sounds have loudness): min…max LUFS bar with each sound as a tick; spread label; "Level this category" button → `ProfilePicker` dialog → `profiles.apply(id, {category_id})` → toast "N sounds queued".
- `SoundItem`: phones = row (play button 48 px, title, duration · LUFS, season badges, tag chips truncated, status pill); ≥ lg grid cards. Clicking the body opens `/sounds/:id`; the play button toggles `usePlayer` with `audioUrl(id, "published", published.revision)`; disabled sounds dimmed with a "disabled" badge; `failed` shows error tooltip; `processing`/`rendering` show spinner.
- Multi-select: checkbox on hover (desktop) / long-press 450 ms (touch) enters selection mode; `BulkBar` fixed at bottom above the tab bar: count, "Select all (filtered)", actions Category, Seasons (`SeasonPicker` with "All seasons" toggle), Tags (`TagEditor` add/remove), Normalize (`ProfilePicker` incl. "None"), Enable, Disable, Delete (confirm). Each calls `sounds.bulk`/`bulkDelete`, toasts the result, refreshes.
- Empty states: no sounds at all → "Upload your first sound" (to `/upload`) + "Import existing files" (to `/system#import`); filters with no match → "No sounds match" + clear filters.
- Floating upload button (< md) bottom-right above the tab bar.

- [ ] **Step 1: Failing tests** — CategoryChips emits `update:modelValue` and shows counts; SoundItem renders duration/LUFS and emits `open`/`toggle-play`/`select`; BulkBar disabled actions when none selected and emits actions.
- [ ] **Step 2–4:** FAIL → implement → `test:unit` + `build` PASS.
- [ ] **Step 5: Commit** `feat(ui): add library with filters, playback, loudness strip and bulk actions`.

## Task 15: Upload and Organize views

**Model:** Sonnet. **Branch:** `track/ui`.

**Files:** Modify `src/views/UploadView.vue`, `src/views/OrganizeView.vue`; Create `src/composables/useUpload.ts`, `src/components/{DropZone.vue,UploadRow.vue,CategoryForm.vue,SeasonForm.vue,ProfileForm.vue,SeasonTimeline.vue,IconPicker.vue,ColorPicker.vue}`; Tests `src/composables/useUpload.spec.ts`, `src/components/SeasonTimeline.spec.ts`.

```ts
// useUpload.ts
export type UploadItem = { id: string; file: File; status: "pending" | "uploading" | "processing" | "done" | "error";
                           progress: number; error: string | null; soundId: string | null }
export function useUpload(): { items: Ref<UploadItem[]>; add(files: FileList | File[]): void;
  start(defaults: UploadDefaults): Promise<void>; remove(id: string): void; clearDone(): void }
export type UploadDefaults = { category_id: string; seasons: string[]; all_seasons: boolean; tags: string[];
                               profile_id?: string | null }   // omit profile_id → category default
// start(): 2 files concurrently; per file: uploads.create → chunks of chunk_size (sequential, progress by bytes)
//   → uploads.complete → status "processing" until the sound's status becomes ready/failed (via useStudio refresh)
```

Upload view: `DropZone` (drag & drop + "Choose files" button, `accept` = supported extensions, multiple); batch defaults panel (category select with inline "New category", `SeasonPicker`, `TagEditor`, `ProfilePicker` with "Category default" option); list of `UploadRow` (name, size, progress bar, status, error, "Edit" link when done); "Upload N files" primary button; unsupported files flagged before upload.

Organize view (tabs on phones, three columns ≥ xl): **Categories** (sortable list with up/down buttons → `categories.reorder`, `CategoryForm` in a `Sheet`: name, icon via `IconPicker` (curated ~60 mdi icons searchable), color via `ColorPicker` (12 swatches + hex input), description, default profile; delete with confirm, 409 message shown), **Seasons** (`SeasonTimeline`: 12-month horizontal band with colored ranges, wrap-around drawn as two segments, today marker; date probe input → `seasons.resolve` shows the result chip; `SeasonForm`: name, color, icon, start/end month+day selects, priority), **Profiles** (cards with LUFS/TP/LRA; `ProfileForm` with sliders + numeric inputs and helper text explaining LUFS; after PATCH with affected sounds → confirm "Re-render N sounds now?" → `profiles.apply(id, {sound_ids})`).

- [ ] **Step 1: Failing tests** — useUpload splits a 9 MB file into 3 chunk calls with correct indices and calls complete with defaults (mock `ui`); concurrency ≤ 2; error on chunk marks item error and continues others; SeasonTimeline computes segments for `12-01..01-06` as two segments and `10-01..10-31` as one.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5: Commit** `feat(ui): add chunked upload and organize views for categories, seasons and profiles`.

## Task 16: Sound editor

**Model:** GPT-6.1-Sol. **Branch:** `track/ui`.

**Files:** Modify `src/views/SoundEditorView.vue`; Create `src/components/{WaveformEditor.vue,TransportBar.vue,AuditionDialog.vue}`, `src/lib/{audioEngine.ts,peaks.ts}`; Tests `src/lib/{audioEngine,peaks}.spec.ts`, `src/views/SoundEditorView.spec.ts`.

```ts
// lib/peaks.ts
export function computePeaks(channels: Float32Array[], buckets: number): number[]   // max abs per bucket across channels, 0..1
// lib/audioEngine.ts
export type PreviewSettings = { trimStart: number; trimEnd: number; gainDb: number; fadeIn: number; fadeOut: number; bypass: boolean }
export class AudioEngine {
  constructor(ctx?: AudioContext)
  load(url: string): Promise<AudioBuffer>          // fetch + decodeAudioData (cached per url)
  play(buffer: AudioBuffer, s: PreviewSettings, opts?: { loop?: boolean; from?: number }): void
  stop(): void
  get position(): number                            // seconds in source timeline (for the playhead)
  get playing(): boolean
  onEnded?: () => void
}
export function gainSchedule(s: PreviewSettings): { time: number; value: number }[]
  // pure: gain automation points relative to playback start (linear dB → amplitude 10^(dB/20)); fades ramp from/to 0;
  // bypass → [{time: 0, value: 1}]
```

Editor layout (inside `Sheet`): header (title, status pill, close with unsaved-changes guard via `useConfirm`). Sections:
1. **Waveform** — `WaveformEditor` creates WaveSurfer with `peaks` + `duration` from the decoded original (no media element), height 120 (96 on phones), accent wave/progress colors, Regions plugin with one draggable/resizable region = trim; large handle hit areas (≥ 24 px) via CSS on `[part="region-handle"]`; playhead driven by `AudioEngine.position` with `requestAnimationFrame`; tap on waveform seeks. Numeric inputs for start/end (step 0.01 s) synced both ways; "Reset trim".
2. **Transport** — play/pause (space bar), loop region toggle, A/B toggle (`bypass`), position/clip length readout.
3. **Level** — gain slider −24…+24 dB (step 0.5, double-click resets), fade in/out sliders 0…min(5 s, clip/2), all applied live through `AudioEngine` (re-start playback at current position on change, debounced 80 ms).
4. **Normalization** — `ProfilePicker` (None + profiles) showing target LUFS; current published loudness/true peak; note that normalization is heard in "Preview render".
5. **Details** — title, category, `SeasonPicker` (+ all seasons), `TagEditor`, enabled switch, notes; saved via `sounds.update` with its own Save button state.
6. **Actions** (sticky footer) — "Preview render" (`sounds.preview` → wait for job via `useJobs` → play `audioUrl(id,"preview",Date.now())`), "Test on speaker" (`AuditionDialog`: target list from settings with label/entity/volume, "use preview" toggle when available, confirm sends `sounds.audition`; no targets → link to System), "Save & publish" (`sounds.putRecipe`; disabled when recipe unchanged or invalid; toast; stays open showing rendering status), "Revert" (back to saved recipe), "Delete" (confirm).

Loading: skeleton while decoding; decoding failure → error panel with "Retry". Works with touch (pointer events) and keyboard (arrow keys nudge focused trim handle input by 0.01 s, shift ×10).

- [ ] **Step 1: Failing tests** — `computePeaks` (bucket math, multi-channel max, silence → zeros); `gainSchedule` (no fades → single point at gain; fade in from 0 to gain at fadeIn; fade out from gain at clip−fadeOut to 0 at clip; bypass); `SoundEditorView.spec.ts` with mocked `ui` and a stub `WaveformEditor`: Save disabled for identity unchanged recipe, enabled after gain change, sends recipe with `profile_id` chosen, unsaved-changes guard asks before closing.
- [ ] **Step 2–4:** FAIL → implement → `test:unit` + `build` PASS.
- [ ] **Step 5: Commit** `feat(ui): add waveform sound editor with live preview, render preview and audition`.

## Task 17: System view

**Model:** GPT-6-Luna. **Branch:** `track/ui`.

**Files:** Modify `src/views/SystemView.vue`; Create `src/components/{ConnectionPanel.vue,ImportBrowser.vue,AuditionTargets.vue,StoragePanel.vue,JobsPanel.vue}`; Tests `src/components/{ImportBrowser,AuditionTargets}.spec.ts`.

Panels (stacked on phones, 2-column grid ≥ lg):
- **Connection**: discovery status chip; masked token with "Reveal" (fetches `ui.token()`, auto-hides after 30 s), "Copy" (clipboard, fallback select text), "Rotate" (confirm; warns the integration must be reconfigured); manual setup instructions (host = App hostname shown in `state`? use text "Use the hostname shown in the App's Info tab, port 8099").
- **Files served by Home Assistant**: `/config/www` exists / served / created_by_app; when not served show the restart notice.
- **Media base URL**: effective value, override input (empty = auto) → `settings.put`.
- **Import existing files** (`id="import"` anchor): `ImportBrowser` breadcrumb navigation over roots, checkbox per supported file, "Select all supported", batch defaults (category, seasons, tags, profile), "Import N files" → `importer.run` → toast + refresh.
- **Speakers for testing**: `AuditionTargets` list editor (label, kind select, entity_id input with domain hint, optional volume 0–1), save → `settings.put`.
- **Limits**: max upload MB, max duration s.
- **Storage**: bytes per area (`formatBytes`).
- **Jobs**: recent jobs with status, duration, errors.

- [ ] **Step 1: Failing tests** — ImportBrowser navigates into a dir (calls browse with child path), parent link, selects only supported files, emits import with selected paths; AuditionTargets validates entity_id prefix per kind and emits the list.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5: Commit** `feat(ui): add system view with connection, import, speakers and storage`.

---

## Task 18: Merge, end-to-end check, docs, publish, release

**Model:** Opus (orchestrator) + Sonnet for docs. **Branch:** `main`.

- [ ] **Step 1:** Merge `track/studio`, `track/integration`, `track/ui` into `main` (no fast-forward merges required; resolve conflicts only in shared files).
- [ ] **Step 2:** `scripts/verify.sh` → all green (start Docker Desktop if installed to include the image build).
- [ ] **Step 3: Local end-to-end smoke** — run Studio in dev mode with temp dirs and the built UI; open in the browser pane at phone (375×812) and desktop widths; upload a generated tone, edit trim/gain, preview render, save & publish, verify the file appears under the temp www dir with `-r2`; check no horizontal scroll and no console errors.
- [ ] **Step 4: Docs** — `README.md` (features, screenshots from step 3, installation: add App repository URL in Supervisor + HACS custom repository; connecting; using `sound_effects.select` with an example automation; Spanish quick start), `docs/installation.md`, `docs/usage.md`, `docs/automations.md` (select + `media_player.play_media` example; Music Assistant announcement example; migration example replacing a hardcoded catalog with a fallback), `docs/api.md`, `docs/troubleshooting.md`, `app/CHANGELOG.md` 1.0.0.
- [ ] **Step 5:** Commit docs; `gh repo create NaturalDevCR/hass-sound-effects --public --source . --push --description "Upload, edit, normalize and organize sound effects for Home Assistant (App + HACS integration)"`; add topics `home-assistant, hacs, home-assistant-addon, sound-effects, music-assistant`.
- [ ] **Step 6:** Watch CI (`gh run watch`) until quality, validate, and app-build succeed; fix failures.
- [ ] **Step 7:** Tag and release: `git tag v1.0.0 && git push origin v1.0.0 && gh release create v1.0.0 --title "v1.0.0" --notes-file app/CHANGELOG.md`.

## Task 19: Install and migrate (operational, user-confirmed)

Done by the orchestrator through the Home Assistant MCP, each step announced and confirmed with the user, following the spec's migration section: add App repository and install the App; start it; add HACS custom repository and install the integration; restart HA; accept discovery; create seasons from `input_datetime.party_halloween_*`/`party_christmas_*`; create categories; import existing files byte-identical with keys = filenames and `es`/`en` tags for bathroom files; verify `sound_effects.select` (dry run) returns reachable URLs; then per flow (bathrooms → intros → lion) create a disabled migrated copy with a fallback to the old catalog, review with the user, switch only on approval, keep originals for rollback.
