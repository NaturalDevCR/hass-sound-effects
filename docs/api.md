# API

The v1 HTTP API is the boundary between the Home Assistant integration and Sound Effects Studio. It is served by the App on port `8099`. Every endpoint requires `Authorization: Bearer <api_token>`; reveal or copy the token in the Studio's **System → Connection** view. The integration handles these requests automatically.

## Endpoints

| Method and path | Purpose | Success |
| --- | --- | --- |
| `GET /api/v1/health` | Check App health and identify the instance. Returns `status`, `version`, `api_version`, `instance_id`. | `200` |
| `GET /api/v1/catalog` | Retrieve the published catalog: revision, generation time, seasons, categories and sounds with a published revision. | `200` or `304` |
| `POST /api/v1/selections` | Report selection events so the App can update counters. Body: `{"events":[{"sound_id":"…","category_id":"…","season_id":"…","selected_at":"…"}]}`. | `204` |

Catalog responses include an `ETag` of the form `"rev-<revision>"`. Send it as `If-None-Match`; the App returns `304 Not Modified` when the catalog has not changed. A sound with a previous published revision remains in the catalog while a newer revision is rendering or has failed. Studio treats a revision as adopted only when the integration presents it back as its `If-None-Match` ETag (a `200` that never reached Home Assistant proves nothing). Superseded and deleted published MP3s are retired; housekeeping removes them only after 7 days and once the integration has acknowledged the catalog change. If the App has never served a catalog (no integration installed), the 7-day grace period alone applies. Current publications are always protected.

Errors use a JSON `detail` message. Invalid or missing bearer credentials return `401`; invalid selection batches can return `422`.

## Supervisor discovery

On startup the App posts discovery data to the Supervisor containing service `sound_effects` and a config object with `host`, `port` (`8099`), `token`, and persistent `instance_id`. Home Assistant asks you to confirm discovery for a new instance. The `instance_id` is the unique identity; rediscovery of the same App updates its existing connection details.

## Events

- `sound_effects_catalog_changed` is fired when the published catalog changes. The integration requests a refresh and also polls periodically (30 seconds by default).
- `sound_effects_selected` is fired for each non-dry-run `sound_effects.select` action. Event data is the returned selection payload. Dry runs do not fire it.

Selection itself is served from the integration's persisted catalog and does not call the App. Reporting the result to the App is asynchronous and only updates Studio statistics.

## Internal UI API

The Studio's `/api/ui/*` endpoints support its web interface and require the Supervisor Ingress proxy context. They are internal implementation details, not a supported public API. See [`contract/openapi-v1.yaml`](../contract/openapi-v1.yaml) for the integration API schema.
