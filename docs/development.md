# Development

## Repository layout

- `app/`: Supervisor App manifest, image build, documentation, and FastAPI/SQLite/ffmpeg backend in `app/src/sound_effects_studio/`.
- `custom_components/sound_effects/`: HACS integration, config flow, entities, selection and services.
- `contract/openapi-v1.yaml`: App-to-integration HTTP contract.
- `tests/`: App, integration and contract tests.
- `scripts/verify.sh`: repository verification script.

## Set up the Python environment

The project targets Python 3.13. Install `uv`, then run:

```sh
uv sync --all-groups
```

Run the verification script with:

```sh
scripts/verify.sh
```

It checks Ruff formatting and lint, runs Pyright and pytest, validates integration translation JSON, and runs UI tests/build when the UI is present. It builds the App Docker image when Docker is available. To run Python tests directly, use `uv run pytest`.

## Run the App locally

Set the development flag to bypass the Supervisor Ingress peer check. Point data and published-file paths at writable local directories:

```sh
SOUND_EFFECTS_DEV=1 \
SOUND_EFFECTS_DATA=/tmp/sound-effects-data \
SOUND_EFFECTS_WWW=/tmp/sound-effects-www \
uv run python -m sound_effects_studio.main
```

The API listens on port `8099`. `SOUND_EFFECTS_DATA` stores the local database, originals and token; `SOUND_EFFECTS_WWW` is the publication directory. Set up suitable local Home Assistant API/Supervisor behavior only when exercising those integrations; the development flag bypasses the Ingress peer check, not other App requirements.

## Run the UI development server

With the UI source available, run:

```sh
npm --prefix app/ui install
npm --prefix app/ui run dev
```

The Vite dev server proxies `/api` requests to `http://localhost:8099`. The UI source is included in this repository under `app/ui`.

## Tests

Python tests are under `tests/studio/`, `tests/integration/` and `tests/contract/`. UI tests and the production build run through the verification script. The project uses pytest, pytest-homeassistant-custom-component, ruff, pyright and OpenAPI validation.

## Release

Release the integration from a version tag named `vX.Y.Z`. Keep its version synchronized with `custom_components/sound_effects/manifest.json`; set the Supervisor App version in `app/config.yaml` to the corresponding release. The current versions are `1.0.1`.
