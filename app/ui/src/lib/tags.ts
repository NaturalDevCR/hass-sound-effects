import { foldText } from "@/lib/filters";

const MAX_TAG_LENGTH = 48;

/**
 * Same shape as the backend's `slugify`: lowercase ASCII, accents stripped, anything that is not
 * [a-z0-9] collapsed to "_", trimmed, at most 48 characters. "" when nothing usable is left.
 */
export function slugifyTag(text: string): string {
  return foldText(text)
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+/, "")
    .slice(0, MAX_TAG_LENGTH)
    .replace(/_+$/, "");
}

/** `tags` plus the slug of `text`, unless that is empty or already there. Returns a new array. */
export function addTag(tags: readonly string[], text: string): string[] {
  const slug = slugifyTag(text);
  return slug && !tags.includes(slug) ? [...tags, slug] : [...tags];
}
