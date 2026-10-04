import type { State } from "@/api/types";
export const makeState = (): State => ({
  hostname: "studio.local",
  version: "1",
  api_token_masked: "••••abcd",
  catalog_revision: 1,
  discovery: { status: "ok", message: null },
  www: { exists: true, served: false, created_by_app: true },
  media_base_url_effective: "http://homeassistant.local:8123",
  storage: { originals_bytes: 2048, published_bytes: 1024, previews_bytes: 512 },
  settings: { max_upload_mb: 100, max_duration_s: 600, audition_targets: [], media_base_url: "" },
});
