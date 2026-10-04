// Plain builders for spec files (never imported by app code). Every field has a sensible default
// so a spec only states what it cares about.
import type { Category, Profile, Season, Sound } from "@/api/types";

export function makeSound(patch: Partial<Sound> & { id: string }): Sound {
  return {
    category_id: "general",
    title: patch.id,
    key: patch.id,
    tags: [],
    seasons: ["regular"],
    all_seasons: false,
    enabled: true,
    notes: "",
    original: null,
    recipe: { trim_start: 0, trim_end: null, gain_db: 0, fade_in: 0, fade_out: 0, profile_id: null },
    published: {
      revision: 1,
      filename: `${patch.id}-r1.mp3`,
      duration: 2.5,
      loudness_lufs: -16,
      true_peak_db: -1.5,
      size: 40_000,
      published_at: "2026-10-03T10:00:00Z",
      mime_type: "audio/mpeg",
    },
    status: "ready",
    error: null,
    selection_count: 0,
    last_selected_at: null,
    created_at: "2026-10-03T10:00:00Z",
    updated_at: "2026-10-03T10:00:00Z",
    has_preview: false,
    ...patch,
  };
}

export function makeCategory(patch: Partial<Category> & { id: string }): Category {
  return {
    name: patch.id,
    icon: "mdi:music-note",
    color: "#8b5cf6",
    description: "",
    sort_order: 0,
    default_profile_id: null,
    ...patch,
  };
}

export function makeSeason(patch: Partial<Season> & { id: string }): Season {
  return {
    name: patch.id,
    color: "#34d399",
    icon: "mdi:calendar-blank",
    start: null,
    end: null,
    priority: 0,
    builtin: false,
    ...patch,
  };
}

export function makeProfile(patch: Partial<Profile> & { id: string }): Profile {
  return { name: patch.id, target_lufs: -16, true_peak: -1.5, lra: 11, ...patch };
}
