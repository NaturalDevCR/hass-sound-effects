import type { Sound, SoundStatus } from "@/api/types";

export type LibraryFilter = {
  categoryId: string | null;
  seasonId: string | null;
  tag: string | null;
  query: string;
  status: SoundStatus | null;
};

/** Lowercases and strips diacritics so "León" and "leon" compare equal. */
export function foldText(text: string): string {
  return text.normalize("NFD").replace(/\p{M}+/gu, "").toLowerCase();
}

/**
 * Applies every active filter (AND). The query is split into words that must all
 * appear somewhere in title, key or tags. A sound that plays in all seasons is
 * eligible for any season filter.
 */
export function filterSounds(sounds: Sound[], f: LibraryFilter): Sound[] {
  const words = foldText(f.query).split(/\s+/).filter(Boolean);
  return sounds.filter((s) => {
    if (f.categoryId !== null && s.category_id !== f.categoryId) return false;
    if (f.seasonId !== null && !s.all_seasons && !s.seasons.includes(f.seasonId)) return false;
    if (f.tag !== null && !s.tags.includes(f.tag)) return false;
    if (f.status !== null && s.status !== f.status) return false;
    if (words.length) {
      const haystack = foldText([s.title, s.key, ...s.tags].join(" "));
      if (!words.every((w) => haystack.includes(w))) return false;
    }
    return true;
  });
}

/** Min/max integrated loudness across published sounds; null when none is measured. */
export function loudnessSpread(sounds: Sound[]): { min: number; max: number; spread: number } | null {
  const values = sounds
    .map((s) => s.published?.loudness_lufs)
    .filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  if (!values.length) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  return { min, max, spread: max - min };
}
