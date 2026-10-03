import type { Recipe } from "@/api/types";
import type { MessageKey } from "@/i18n";

export const GAIN_MIN = -24;
export const GAIN_MAX = 24;

/** The recipe that leaves a file untouched: whole clip, no gain, no fades, no normalization. */
export const IDENTITY: Recipe = Object.freeze({
  trim_start: 0,
  trim_end: null,
  gain_db: 0,
  fade_in: 0,
  fade_out: 0,
  profile_id: null,
});

const EPSILON = 1e-6;
const near = (a: number, b: number) => Math.abs(a - b) <= EPSILON;
const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));
const finite = (value: number) => (Number.isFinite(value) ? value : 0);

export function recipesEqual(a: Recipe, b: Recipe): boolean {
  const sameEnd =
    a.trim_end === null || b.trim_end === null ? a.trim_end === b.trim_end : near(a.trim_end, b.trim_end);
  return (
    sameEnd &&
    near(a.trim_start, b.trim_start) &&
    near(a.gain_db, b.gain_db) &&
    near(a.fade_in, b.fade_in) &&
    near(a.fade_out, b.fade_out) &&
    a.profile_id === b.profile_id
  );
}

export function isIdentity(r: Recipe): boolean {
  return recipesEqual(r, IDENTITY);
}

/** Seconds of audio that survive the trim. Never negative, never longer than the file. */
export function clipLength(r: Recipe, duration: number): number {
  const end = Math.min(r.trim_end ?? duration, duration);
  return Math.max(0, end - Math.max(0, r.trim_start));
}

/** i18n keys (`recipe.error.*`) describing everything wrong with the recipe; empty when valid. */
export function validateRecipe(r: Recipe, duration: number): MessageKey[] {
  const numbers = [r.trim_start, r.trim_end ?? 0, r.gain_db, r.fade_in, r.fade_out];
  if (!numbers.every(Number.isFinite)) return ["recipe.error.number"];

  const problems: MessageKey[] = [];
  const end = r.trim_end ?? duration;
  const trimOk = r.trim_start < end;
  if (r.trim_start < 0) problems.push("recipe.error.trimStart");
  if (r.trim_end !== null && r.trim_end > duration + EPSILON) problems.push("recipe.error.trimEnd");
  if (!trimOk) problems.push("recipe.error.trimOrder");
  if (r.fade_in < 0 || r.fade_out < 0) problems.push("recipe.error.fadeNegative");
  if (trimOk && r.fade_in + r.fade_out > clipLength(r, duration) + EPSILON) {
    problems.push("recipe.error.fadeLong");
  }
  if (r.gain_db < GAIN_MIN || r.gain_db > GAIN_MAX) problems.push("recipe.error.gainRange");
  return problems;
}

/** Pulls every value back into range (new object; the input is untouched). */
export function clampRecipe(r: Recipe, duration: number): Recipe {
  const total = Math.max(0, finite(duration));
  const trim_start = clamp(finite(r.trim_start), 0, total);
  const trim_end = r.trim_end === null ? null : clamp(finite(r.trim_end), trim_start, total);
  const length = clipLength({ ...r, trim_start, trim_end }, total);
  const fade_in = clamp(finite(r.fade_in), 0, length);
  const fade_out = clamp(finite(r.fade_out), 0, length - fade_in);
  return { ...r, trim_start, trim_end, gain_db: clamp(finite(r.gain_db), GAIN_MIN, GAIN_MAX), fade_in, fade_out };
}
