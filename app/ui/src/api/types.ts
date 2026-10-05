// Mirrors the "Shared API Reference" types verbatim (snake_case on the wire).
// Anything below the "UI API shapes" divider is derived from the endpoint table.

export type Season = {
  id: string;
  name: string;
  color: string;
  icon: string;
  start: string | null; // "MM-DD", inclusive; null only for regular
  end: string | null;
  priority: number;
  builtin: boolean;
};

export type Category = {
  id: string;
  name: string;
  icon: string;
  color: string;
  description: string;
  sort_order: number;
  default_profile_id: string | null;
};

export type Profile = { id: string; name: string; target_lufs: number; true_peak: number; lra: number };

export type Recipe = {
  trim_start: number;
  trim_end: number | null;
  gain_db: number;
  fade_in: number;
  fade_out: number;
  profile_id: string | null;
};

export type OriginalInfo = {
  filename: string;
  size: number;
  format: string;
  codec: string;
  duration: number;
  sample_rate: number;
  channels: number;
};

export type Published = {
  revision: number;
  filename: string;
  duration: number;
  loudness_lufs: number | null;
  true_peak_db: number | null;
  size: number;
  published_at: string;
  mime_type: "audio/mpeg";
};

export type SoundStatus = "processing" | "ready" | "rendering" | "failed";

export type Sound = {
  id: string;
  category_id: string;
  title: string;
  key: string;
  tags: string[];
  seasons: string[];
  all_seasons: boolean;
  enabled: boolean;
  notes: string;
  original: OriginalInfo | null;
  recipe: Recipe;
  published: Published | null;
  status: SoundStatus;
  error: string | null;
  selection_count: number;
  last_selected_at: string | null;
  created_at: string;
  updated_at: string;
  has_preview: boolean;
};

export type JobKind = "import" | "publish" | "preview";
export type JobStatus = "queued" | "running" | "done" | "failed";

export type Job = {
  id: string;
  kind: JobKind;
  sound_id: string;
  sound_title: string;
  status: JobStatus;
  progress: number; // fraction 0..1
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type AuditionTarget = {
  id: string;
  label: string;
  kind: "media_player" | "script";
  entity_id: string;
  volume: number | null;
};

export type Settings = {
  max_upload_mb: number;
  max_duration_s: number;
  audition_targets: AuditionTarget[];
  media_base_url: string; // "" = auto-detect
};

export type State = {
  hostname: string | null;
  version: string;
  api_token_masked: string;
  catalog_revision: number;
  discovery: { status: "ok" | "failed" | "unavailable"; message: string | null };
  www: { exists: boolean; served: boolean | null; created_by_app: boolean };
  media_base_url_effective: string;
  storage: { originals_bytes: number; published_bytes: number; previews_bytes: number };
  settings: Settings;
};

// Integration API v1 catalog (bearer auth). The UI never calls it; kept for parity.
export type Catalog = {
  revision: number;
  generated_at: string;
  seasons: Omit<Season, "builtin">[];
  categories: Omit<Category, "default_profile_id">[];
  sounds: {
    id: string;
    category_id: string;
    title: string;
    key: string;
    tags: string[];
    seasons: string[];
    all_seasons: boolean;
    enabled: boolean;
    published: { revision: number; filename: string; duration: number; mime_type: string };
  }[];
};

// ---------------------------------------------------------------------------
// UI API shapes (request/response bodies from the endpoint table)
// ---------------------------------------------------------------------------

export type CategoryInput = {
  id?: string;
  name: string;
  icon?: string;
  color?: string;
  description?: string;
  default_profile_id?: string | null;
};
export type CategoryPatch = Partial<Omit<Category, "id">>;

export type SeasonInput = {
  id?: string;
  name: string;
  color?: string;
  icon?: string;
  start: string | null;
  end: string | null;
  priority?: number;
};
export type SeasonPatch = Partial<Omit<Season, "id" | "builtin">>;

export type ProfileInput = { id?: string; name: string; target_lufs: number; true_peak: number; lra: number };
export type ProfilePatch = Partial<Omit<Profile, "id">>;
export type ProfileUpdateResult = { profile: Profile; affected_sound_ids: string[] };
export type ProfileApplyBody = { sound_ids: string[] } | { category_id: string };

export type SoundPatch = Partial<
  Pick<Sound, "title" | "category_id" | "key" | "tags" | "seasons" | "all_seasons" | "enabled" | "notes">
>;

export type BulkSet = {
  category_id?: string;
  seasons?: string[];
  all_seasons?: boolean;
  add_tags?: string[];
  remove_tags?: string[];
  enabled?: boolean;
  /** Key present => set recipe profile and queue publish; `null` clears the profile. */
  profile_id?: string | null;
};
export type BulkBody = { ids: string[]; set: BulkSet };
export type BulkResult = { updated: number; queued: number };

export type AuditionBody = { target_id: string; use_preview: boolean };

export type UploadInit = { upload_id: string; chunk_size: number };
export type UploadComplete = {
  category_id: string;
  seasons: string[];
  all_seasons: boolean;
  tags: string[];
  title?: string;
  /** Absent => category default; `null` => no normalization. */
  profile_id?: string | null;
};

export type BrowseEntry = { name: string; path: string; kind: "dir" | "file"; size: number; supported: boolean };
export type BrowseResult = { path: string; parent: string | null; roots: string[]; entries: BrowseEntry[] };
export type ImportBody = {
  paths: string[];
  category_id: string;
  seasons: string[];
  all_seasons: boolean;
  tags: string[];
  profile_id?: string | null;
};

export type AudioKind = "original" | "preview" | "published";
