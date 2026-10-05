# Sound Effects — Home Assistant App + HACS integration

## Problem

Short sound effects in Home Assistant (entrance intros, a button-triggered lion
roar, door announcements) are managed by hand today:

- Each automation hardcodes its catalog in `variables:` as
  `{regular: [{key, duration, url}], halloween: [], christmas: []}` with URLs
  under `/local/...` and durations typed by hand.
- Shuffle history lives in an `input_text` (255-character limit).
- Adding a sound means a Samba/SSH upload plus YAML edits; loudness differs
  between files; nothing can be trimmed or leveled without external tools.
- Seasons are spread across an `input_select`, `input_datetime` pairs, and
  template sensors.

The automations' playback logic (Music Assistant announcements plus a
parallel Snapcast-client "rescue" branch that must act inside a ~230 ms
window) is delicate, proven, and must not change.

## Goals

- Upload, organize, trim, level, normalize, fade, and audition sounds from a
  responsive, mobile-first web UI inside Home Assistant.
- Make sounds play at a consistent perceived loudness through named
  normalization profiles applied per sound, per category, or in bulk.
- Categorize sounds and assign them to seasons with yearly date ranges.
- Replace hardcoded catalogs with one action call that returns a playable URL
  and a measured duration, with shuffle history that has no size limit.
- Keep the App out of the critical path: selection keeps working while the
  App is stopped, updating, or restarting.
- Never change how a sound is played. Automations stay the device-control
  layer.

## Non-goals (v1)

- Playing media from the integration (no generic `play` action).
- Weighted or sequential selection modes; only shuffle-bag.
- Continuous folder watching; imports are explicit, one-time.
- Detailed analytics beyond a selection counter and last-selected time.
- Quiet hours, cooldowns, volume, or interruption priority — these stay in
  Home Assistant automations.

## Architecture

One public repository, `NaturalDevCR/hass-sound-effects`, mirroring the layout
of `hass-clips-manager`:

```
app/                               Supervisor App "Sound Effects Studio"
  config.yaml  Dockerfile  DOCS.md  rootfs/
  src/sound_effects_studio/        FastAPI + SQLite + ffmpeg
  ui/                              Vue 3 + Vite + Tailwind 4 SPA (Ingress)
custom_components/sound_effects/   HACS integration
contract/openapi-v1.yaml           App ⇄ integration contract
docs/  tests/  scripts/verify.sh  .github/workflows/
hacs.json  repository.yaml  pyproject.toml  LICENSE (Apache-2.0)
```

Boundaries:

- **App** owns originals, edit recipes, rendering, published files, categories,
  seasons, settings, and selection statistics.
- **Integration** owns the cached catalog, season resolution, selection, and
  shuffle history.
- **Automations** own playback.

Data flow:

1. The user uploads or imports a sound in the App UI. The App analyzes it,
   renders it if needed, and publishes an immutable file under
   `/config/www/sound-effects/`. Home Assistant serves it at
   `/local/sound-effects/<file>`.
2. The App increments its catalog revision and fires the Home Assistant event
   `sound_effects_catalog_changed` through the Supervisor Core API proxy.
3. The integration refetches the catalog (on that event, and by polling every
   30 seconds as a fallback) and persists it with `homeassistant.helpers.storage.Store`.
4. An automation calls `sound_effects.select`; the integration resolves the
   season, picks from the shuffle bag, persists history, and returns the URL
   and duration. No HTTP call to the App happens on this path.
5. The integration reports the selection to the App asynchronously, fire and
   forget, for statistics.

## App: Sound Effects Studio

### Manifest (`app/config.yaml`)

- `slug: sound_effects_studio`, `ingress: true`, `ingress_port: 8099`,
  `panel_icon: mdi:waveform`, `panel_title: Sound Effects`.
- `arch: [aarch64, amd64]`, `startup: application`, `init: false`.
- `map: [homeassistant_config:rw, media:ro, share:ro]`.
- `homeassistant_api: true` (fire events, call services for audition).
- `hassio_api: true` and `discovery: [sound_effects]` (publish discovery,
  read own hostname).
- `options: {log_level: info}`; every other setting lives in the UI.
- Built locally by the Supervisor (no prebuilt image), like clips-manager.

### Storage

- SQLite database at `/data/studio.db`.
- Originals at `/data/originals/<sound_id>/<original_name>`; never modified.
- Unpublished render previews at `/data/previews/<sound_id>.mp3`.
- Published files at `/homeassistant/www/sound-effects/<sound_id>-r<revision>.mp3`.
  Renaming a sound or category never changes a URL. The
  current revision is always kept. Superseded and deleted publications are recorded
  in `retired_files` with the catalog revision that retired them and a retirement
  timestamp. Housekeeping removes them after 24 hours only once the integration
  acknowledges that catalog revision by presenting it as the `If-None-Match`
  ETag of a later `GET /api/v1/catalog` (proof the integration adopted and
  persisted it). Without any acknowledgement yet, grace alone applies. Original
  and preview files are removed immediately when a sound is deleted.
- API token at `/data/api_token` (generated on first start, 32 random bytes,
  URL-safe base64).
- Home Assistant only serves `/local` when `/config/www` existed at startup.
  If the App had to create `www`, the UI shows a banner asking for one Home
  Assistant restart.

### Data model

`Season`
: `id` (slug, immutable), `name`, `color`, `icon` (mdi name), `start` and
  `end` (`MM-DD`, inclusive, ranges may wrap the year end), `priority`
  (higher wins when ranges overlap). The built-in `regular` season has no
  range, cannot be deleted, and is the fallback.

`NormalizationProfile`
: `id` (slug, immutable), `name`, `target_lufs` (−30…−5), `true_peak`
  (−9…0 dBTP), `lra` (1…20). Built-in, editable, deletable defaults:
  `standard` "Standard" (−16 LUFS, −1.5 dBTP, LRA 11), `loud` "Loud"
  (−13, −1.0, 11), `soft` "Soft" (−20, −1.5, 11), `voice` "Voice /
  announcement" (−18, −1.5, 7). A profile in use by any recipe or category
  cannot be deleted.

`Category`
: `id` (slug, immutable), `name`, `icon`, `color`, `description`,
  `sort_order`, `default_profile_id` (nullable; applied to new uploads and
  imports into this category).

`Sound`
: `id` (12-character random id), `category_id`, `title`, `key` (stable legacy
  key, defaults to the original filename; used for migrating history and for
  automations that log keys), `tags` (list of lowercase slugs, e.g. `es`,
  `en`), `seasons` (non-empty list of season ids) or `all_seasons: true`,
  `enabled`, `notes`, `original` (name, size, format, duration, sample rate,
  channels), `recipe`, `published` (revision, filename, duration, integrated
  LUFS, true peak, size, published_at), `status`, `error`, `selection_count`,
  `last_selected_at`, `created_at`, `updated_at`.

New uploads default to `seasons: [regular]`, `enabled: true`.

`Recipe`
: `trim_start` (s, ≥ 0), `trim_end` (s or null for end of file), `gain_db`
  (−24…+24, applied after normalization as a deliberate offset), `fade_in`
  and `fade_out` (s, ≥ 0), `profile_id` (normalization profile or null for
  none). The identity recipe is `{0, null, 0, 0, 0, null}`.

`status`
: `processing` (import analysis or first render), `ready` (published, playable),
  `rendering` (a new revision is being produced; the previous one stays
  published and playable), `failed` (last render failed; previous revision
  still published if any).

A global `catalog_revision` integer increments on every change that affects
the published catalog.

### Settings (stored in SQLite, edited in the UI)

- `max_upload_mb` (default 100), `max_duration_s` (default 600).
- `audition_targets`: list of `{id, label, kind: media_player|script, entity_id, volume?}`. Volume is only supported for script targets and is passed as the `volume` script variable; media-player targets reject a non-null volume. The speakers editor clears volume when switching to a media player, and the audition dialog only displays script volume.
- `media_base_url`: base URL speakers use to fetch files during auditions.
  Auto-detected on start from the Core config `internal_url`, else from the
  Supervisor primary interface IPv4 and the Core port; overridable in the UI.
  The integration computes its own URLs independently.

### Rendering

- One in-process asyncio job queue, one worker, ffmpeg subprocess with a
  timeout of `max(60 s, 4 × duration)`.
- Supported inputs: mp3, wav, flac, ogg/opus, m4a/aac, webm, mp4/mov (audio
  stream only). Anything else is rejected at upload with a clear message.
- Import with an identity recipe and an mp3 input publishes a byte-identical
  copy (no re-encode). Otherwise output is MP3 (`libmp3lame -q:a 2`), 44.1 kHz,
  source channel count capped at 2.
- Filter chain order: `atrim` → `loudnorm` (two-pass: measure the trimmed
  audio, then apply with `linear=true` and the measured values, targets from
  the recipe's profile) → `volume=<gain_db>dB` → `afade` in/out → `alimiter`
  at the true-peak ceiling (profile `true_peak`, or −1 dBTP without a
  profile) when `gain_db > 0` or a profile is set.
- After render: ffprobe duration, loudnorm integrated loudness and true peak.
  Post-publish measurement, including its internal probe, has a shared timeout
  of `max(30, 2 * duration)` seconds. Timeout keeps the publication with null
  loudness and releases the worker.
- Publish: write to a temp file in the destination directory, validate with
  ffprobe, `os.replace` into the final name, then update the database and
  increment `catalog_revision`. A failed render never touches the published
  file.
- At worker startup, interrupted `rendering` sounds become `ready` when they
  have a publication, otherwise `failed` with error `interrupted`. Interrupted
  `processing` sounds re-enqueue import when their original exists, otherwise
  become `failed` with error `interrupted`.
- "Preview render" writes to `/data/previews` and does not publish.

### Authentication

- Ingress UI and `/api/ui/*`: allowed only when the peer address is the
  Supervisor Ingress proxy (`172.30.32.2`). A development flag
  (`SOUND_EFFECTS_DEV=1`) disables the check for local work.
- Integration API `/api/v1/*`: `Authorization: Bearer <api_token>`, compared
  with `hmac.compare_digest`. `GET /api/ui/state` only carries the masked
  token; the full token is returned by `GET /api/ui/token` when the user
  explicitly reveals or copies it (Ingress panels are admin-only).

### Discovery

On start the App reads its hostname from `GET http://supervisor/addons/self/info`
and posts `POST http://supervisor/discovery` with
`{service: "sound_effects", config: {host, port: 8099, token, instance_id}}`.
`instance_id` is a UUID persisted in `/data`. Failures are logged and shown in
the System view; manual configuration remains fully supported.

### Integration API v1 (documented in `contract/openapi-v1.yaml`)

- `GET /api/v1/health` → `{status, version, api_version: 1, instance_id}`.
- `GET /api/v1/catalog` → `{revision, generated_at, seasons[], categories[], sounds[]}`;
  sounds include every sound that has a published revision, whatever its
  current status (a `rendering` or `failed` sound still serves its previous
  revision).
  Supports `ETag`/`If-None-Match` (`304`).
- `POST /api/v1/selections` → body `{events: [{sound_id, category_id, season_id, selected_at}]}`;
  updates counters; returns `204`.

### UI API (`/api/ui`, Ingress only)

- `GET /state` (version, settings, masked token, discovery status, www status).
- Categories and seasons: list, create, update, delete (delete refuses when
  sounds reference the category; deleting a season removes it from sounds,
  and sounds left without seasons fall back to `regular`).
- `GET /seasons/resolve?date=YYYY-MM-DD` → the season the calendar picks.
- Normalization profiles: list, create, update, delete.
  `POST /profiles/{id}/apply` with `{sound_ids[]}` or `{category_id}` sets
  `recipe.profile_id` on those sounds and queues their renders.
  `POST /sounds/bulk` accepts `profile_id` too (null removes normalization).
  Updating a profile's targets returns the affected sound count; the UI then
  offers "re-render N sounds" which calls `apply` for them.
- Sounds: list, get, patch metadata, put recipe (queues render + publish),
  post preview (queues preview render), delete, bulk update
  (`{ids, set: {category_id?, seasons?, all_seasons?, add_tags?, remove_tags?, enabled?}}`),
  bulk delete.
- Audio streams: `GET /sounds/{id}/original`, `/preview`, `/published`
  (HTTP range support for seeking).
- Uploads in 4 MB chunks: `POST /uploads` → `PUT /uploads/{id}/chunks/{n}` →
  `POST /uploads/{id}/complete` with `{category_id, seasons, all_seasons, tags, title?}`.
- Import: `GET /import/browse?path=` limited to `/homeassistant/www`, `/media`,
  `/share` (resolved paths must stay inside those roots);
  `POST /import` with `{paths[], category_id, seasons, all_seasons, tags}`.
- `POST /sounds/{id}/audition` with `{target_id, use_preview}`; the App calls
  `media_player.play_media` (`announce: true`, media URL) or `script.turn_on`
  with variables `{url, duration, title, volume}` through the Supervisor Core
  API proxy. Auditions never touch shuffle history or counters.
- `GET /jobs` (recent and active), `POST /token/rotate`, `GET/PUT /settings`.

## Integration: `sound_effects`

### Setup

- Config flow: `hassio` discovery step (confirm dialog) and manual `user`
  step (host, port, token). Unique ID is the App `instance_id`; rediscovery
  updates host/token on the existing entry.
- Options flow: `public_base_url` (default from
  `homeassistant.helpers.network.get_url(hass, allow_external=False, prefer_external=False)`),
  `season_entity` (optional entity whose state names a season by id or name,
  case-insensitive), `scan_interval` (default 30 s).
- On setup the integration loads the persisted catalog snapshot first, so it
  is usable with the App offline; then it starts the coordinator.
- `iot_class: local_polling`, `integration_type: service`, translations
  `en` and `es`.

### Season resolution

Effective season, first match wins:

1. `season` field of the action call.
2. `select.sound_effects_season_override` when not `Auto`.
3. `season_entity` state when it matches a known season.
4. The App calendar evaluated at the current local date (highest priority of
   matching ranges; ties broken by season id).
5. `regular`.

The same calendar logic exists in the App (Python, for the UI "which season
applies on date X" view) and the integration (Python); a shared fixture table
in tests keeps them equal.

### Selection

- Eligible sounds: `enabled`, published, in the category, carrying every
  requested tag, and (`all_seasons` or effective season in `seasons`).
- If none are eligible in the effective season, retry with `regular`
  (`season_fallback: true`). Tags are never relaxed. If still none, raise
  `ServiceValidationError` with translation key `no_eligible_sound`.
- Shuffle bag per key `category|season|sorted_tags`, persisted with `Store`
  (`async_delay_save`, 1 s). State per bag: `remaining`, `played`, `last`.
  On each selection: drop ids no longer eligible; append newly eligible ids not
  yet played this round; when `remaining` is empty start a new round with all
  eligible ids minus `last` (unless it is the only one); pick uniformly at
  random; move it to `played`; set `last`.
- `asyncio.Lock` serializes selections.
- `dry_run: true` returns a pick without mutating any state.

### Actions

`sound_effects.select` (`SupportsResponse.OPTIONAL`)
: fields `category` (id or name, required), `tags` (list), `season`,
  `dry_run`. Response:
  `{sound_id, key, title, category, tags, season, requested_season, season_fallback, url, path, duration, revision, mime_type}`.
  `path` is `/local/sound-effects/<file>`; `url` is `public_base_url + path`.
  Fires event `sound_effects_selected` with the same payload (unless dry run).

`sound_effects.reset_history`
: optional `category`; clears matching bags.

`sound_effects.refresh`
: forces a catalog fetch.

### Entities

- `sensor.sound_effects_active_season` — state is the season id; attributes
  `name`, `source` (`action`/`override`/`entity`/`calendar`/`default`), `color`.
- `select.sound_effects_season_override` — options `Auto` plus season names;
  restores its state across restarts.
- One `sensor.sound_effects_<category_id>_last` per category, added and removed
  as categories change — state is the last selected title; attributes
  `sound_id`, `key`, `url`, `duration`, `season`, `selected_at`,
  `available` (eligible count for the current season).
- `binary_sensor.sound_effects_studio_connected` (connectivity, diagnostic) —
  attributes `catalog_revision`, `last_sync`, `app_version`.
- Diagnostics download redacts the token.

## UI (Vue 3, Tailwind 4, wavesurfer.js 7)

Visual language: dark-first, surfaces separated by luminance (same family as
clips-manager), with its own accent (violet `#8b5cf6`) so the two Apps are
distinguishable. Icons from `@mdi/js` to match Home Assistant. Spanish and
English (auto from browser language, switchable, remembered in
`localStorage` with try/catch). All URLs relative for Ingress.

Navigation: bottom tab bar on phones, left sidebar from `md` up.

1. **Library** (home) — horizontally scrollable category chips with counts,
   season and tag filters, search. Sounds as list rows on phones and cards on
   desktop: large play/pause (browser preview of the published file), title,
   duration, season badges, tags, status pill, integrated loudness (LUFS)
   with a profile marker. A per-category loudness strip shows the spread
   (min…max LUFS) and offers "Level this category" (pick a profile → apply to
   all its sounds). Long-press or checkbox enters
   multi-select with a bulk bar (category, seasons, tags, enable/disable,
   delete with confirmation). Floating "Upload" button on phones.
2. **Editor** — full-screen sheet on phones, side drawer on desktop.
   Waveform with a draggable trim region (touch-sized handles) and numeric
   trim fields; transport (play, loop region, A/B original vs edited); gain
   slider in dB with live WebAudio preview; fade in/out with live preview;
   normalization profile picker (live preview not possible → "Preview
   render" button renders and plays the exact result); loudness and true-peak readout of the
   published revision; metadata (title, category, seasons or "all", tags,
   enabled, notes); "Test on speaker" with target picker showing destination
   and volume; primary "Save & publish". Unsaved-changes guard.
3. **Upload** — drop zone and file picker (multiple), per-batch defaults
   (category, seasons, tags, normalization profile defaulting to the
   category's), per-file progress and
   errors, links to edit each result.
4. **Organize** — categories (with default profile), seasons, and
   normalization profiles CRUD with color/icon pickers; season timeline for
   the year with a date probe ("on Oct 31 the season is…"); profile edits
   offer to re-render affected sounds.
5. **System** — connection (masked token, copy, rotate, discovery status),
   `/config/www` status, import browser for existing folders, audition
   targets, media base URL, storage usage, recent jobs.

Live job progress appears in a persistent bottom drawer/toast stack.
Empty states explain the next action. All destructive actions confirm.

## Error handling

- App down: integration entities stay; connectivity sensor goes off; selection
  continues from the persisted catalog.
- Render failure: sound shows `failed` with the ffmpeg error tail; previous
  revision stays published.
- Upload of unsupported or oversized files: rejected per file with reason.
- Missing `/config/www` at HA startup: banner in the UI.
- Discovery failure: manual setup instructions in the System view.
- No eligible sound: `ServiceValidationError` so automations with
  `continue_on_error: true` can fall back.

## Testing

- **App** (pytest, real ffmpeg; fixtures generated with `lavfi` sine tones):
  recipe → filter graph, identity copy is byte-identical, trim/fade durations,
  normalization lands within ±1 LU of each profile target (two fixtures at
  different loudness end within 1 LU of each other), profile apply/bulk
  queues renders, profile in use cannot be deleted, atomic publish keeps the previous file on
  failure, revision cleanup, chunked upload assembly, import path traversal
  rejection, Ingress-IP vs bearer authorization, catalog ETag, season calendar.
- **Integration** (pytest-homeassistant-custom-component): shuffle bag
  (exhaustion, no immediate repeat across rounds, reconciliation after catalog
  changes, dry run), season precedence, fallback rules, config flow (user and
  hassio), options flow, persisted snapshot used offline, action responses,
  entities, diagnostics redaction.
- **Contract**: shared season-calendar fixture table run against both
  implementations; OpenAPI validated.
- **UI** (vitest): recipe/time math, filters, i18n completeness, upload
  chunking.
- `scripts/verify.sh` runs ruff, pyright, pytest, OpenAPI validation, UI tests
  and build, and the App Docker build when Docker exists. CI runs it plus
  `hassfest` and the HACS action.

## Release

- Integration released with tags `vX.Y.Z` (HACS); App versioned in
  `app/config.yaml`. First release: `v1.0.0` for both.
- README in English with a Spanish quick start; `docs/` covers installation,
  usage, automation examples (including a migration example from a
  hardcoded catalog with a fallback), API, troubleshooting.

## Migration of the existing installation (operational phase)

Done after release, through the Home Assistant MCP, each step confirmed by the
user:

1. Add repositories, install the App and the integration, connect them.
2. Create seasons Regular / Halloween / Christmas from the existing
   `input_datetime` ranges; create categories for entrance intros, lion
   effects, and bathroom announcements.
3. Import the existing files as byte-identical copies (no profile), keeping
   their filenames as `key`; tag bathroom announcements `es`/`en`. Leveling
   with a profile is a later, opt-in step the user takes in the UI.
4. For each flow (bathrooms → intros → lion): create a disabled copy whose
   only change is replacing the hardcoded catalog/history variables with a
   `sound_effects.select` call (with `continue_on_error` and a fallback to
   the old hardcoded catalog); keep every playback, rescue, volume, and delay
   step unchanged; enable the copy and disable the original only after user
   approval; the original remains for one-click rollback.
