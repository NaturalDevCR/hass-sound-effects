import { describe, expect, it } from "vitest";
import { filterSounds, loudnessSpread, type LibraryFilter } from "@/lib/filters";
import { IDENTITY } from "@/lib/recipe";
import type { Sound } from "@/api/types";

function sound(patch: Partial<Sound> & { id: string }): Sound {
  return {
    category_id: "general",
    title: patch.id,
    key: `${patch.id}.mp3`,
    tags: [],
    seasons: ["regular"],
    all_seasons: false,
    enabled: true,
    notes: "",
    original: null,
    recipe: { ...IDENTITY },
    published: null,
    status: "ready",
    error: null,
    selection_count: 0,
    last_selected_at: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    has_preview: false,
    ...patch,
  };
}

const none: LibraryFilter = { categoryId: null, seasonId: null, tag: null, query: "", status: null };

const withLufs = (id: string, lufs: number | null) =>
  sound({
    id,
    published: {
      revision: 1,
      filename: `${id}-r1.mp3`,
      duration: 1,
      loudness_lufs: lufs,
      true_peak_db: null,
      size: 10,
      published_at: "2026-01-01T00:00:00Z",
      mime_type: "audio/mpeg",
    },
  });

describe("filterSounds", () => {
  const all = [
    sound({ id: "a", title: "León ruge", category_id: "animals", tags: ["es", "zoo"] }),
    sound({ id: "b", title: "Timbre de la puerta", category_id: "doors", key: "doorbell.wav", tags: ["en"] }),
    sound({ id: "c", title: "Jingle", seasons: ["christmas"], tags: ["holiday"], status: "failed" }),
    sound({ id: "d", title: "Fanfare", all_seasons: true, seasons: ["regular"], status: "rendering" }),
  ];

  it("returns everything for an empty filter without copying order", () => {
    expect(filterSounds(all, none).map((s) => s.id)).toEqual(["a", "b", "c", "d"]);
  });

  it("matches the query accent-insensitively against title", () => {
    expect(filterSounds(all, { ...none, query: "leon" }).map((s) => s.id)).toEqual(["a"]);
    expect(filterSounds(all, { ...none, query: "LEÓN" }).map((s) => s.id)).toEqual(["a"]);
  });

  it("matches key and tags, and requires every word", () => {
    expect(filterSounds(all, { ...none, query: "doorbell" }).map((s) => s.id)).toEqual(["b"]);
    expect(filterSounds(all, { ...none, query: "zoo" }).map((s) => s.id)).toEqual(["a"]);
    expect(filterSounds(all, { ...none, query: "puerta timbre" }).map((s) => s.id)).toEqual(["b"]);
    expect(filterSounds(all, { ...none, query: "puerta zoo" })).toEqual([]);
  });

  it("filters by category", () => {
    expect(filterSounds(all, { ...none, categoryId: "doors" }).map((s) => s.id)).toEqual(["b"]);
  });

  it("filters by season, treating all-seasons sounds as eligible everywhere", () => {
    expect(filterSounds(all, { ...none, seasonId: "christmas" }).map((s) => s.id)).toEqual(["c", "d"]);
    expect(filterSounds(all, { ...none, seasonId: "regular" }).map((s) => s.id)).toEqual(["a", "b", "d"]);
  });

  it("filters by tag and status", () => {
    expect(filterSounds(all, { ...none, tag: "es" }).map((s) => s.id)).toEqual(["a"]);
    expect(filterSounds(all, { ...none, status: "failed" }).map((s) => s.id)).toEqual(["c"]);
  });

  it("combines filters with AND", () => {
    expect(filterSounds(all, { ...none, categoryId: "animals", tag: "en" })).toEqual([]);
  });
});

describe("loudnessSpread", () => {
  it("ignores sounds without published loudness", () => {
    const sounds = [withLufs("a", -16), withLufs("b", null), sound({ id: "c" }), withLufs("d", -12.5)];
    const out = loudnessSpread(sounds);
    expect(out).not.toBeNull();
    expect(out?.min).toBe(-16);
    expect(out?.max).toBe(-12.5);
    expect(out?.spread).toBeCloseTo(3.5);
  });

  it("returns null when nothing is measured and zero spread for one sound", () => {
    expect(loudnessSpread([])).toBeNull();
    expect(loudnessSpread([withLufs("a", null), sound({ id: "b" })])).toBeNull();
    expect(loudnessSpread([withLufs("a", -14)])).toEqual({ min: -14, max: -14, spread: 0 });
  });
});
