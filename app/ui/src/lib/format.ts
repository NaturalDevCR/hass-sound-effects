import type { Locale } from "@/i18n";

const MINUS = "−";
const DASH = "—";

/** One-decimal number with a typographic minus and no negative zero. */
function fixed(value: number, decimals = 1): string {
  const rounded = Number(value.toFixed(decimals));
  if (rounded === 0) return (0).toFixed(decimals);
  const text = Math.abs(rounded).toFixed(decimals);
  return rounded < 0 ? MINUS + text : text;
}

/** 2.5 -> "0:02.5", 75.04 -> "1:15.0". Minutes keep counting past an hour. */
export function formatDuration(seconds: number): string {
  const tenths = Number.isFinite(seconds) ? Math.round(Math.max(0, seconds) * 10) : 0;
  const minutes = Math.floor(tenths / 600);
  const secs = Math.floor((tenths % 600) / 10);
  return `${minutes}:${String(secs).padStart(2, "0")}.${tenths % 10}`;
}

/** -16.04 -> "−16.0 LUFS"; null -> "—". */
export function formatLufs(value: number | null): string {
  return value === null || !Number.isFinite(value) ? DASH : `${fixed(value)} LUFS`;
}

/** 2 -> "+2.0 dB", -3 -> "−3.0 dB", 0 -> "0 dB". */
export function formatDb(value: number): string {
  const rounded = Number(value.toFixed(1));
  if (!Number.isFinite(rounded) || rounded === 0) return "0 dB";
  return `${rounded > 0 ? "+" : MINUS}${Math.abs(rounded).toFixed(1)} dB`;
}

const UNITS = ["B", "KB", "MB", "GB", "TB"] as const;

/** 1536 -> "1.5 KB". Binary multiples (1 KB = 1024 B), the way file managers show them. */
export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  let unit = 0;
  let value = bytes;
  while (value >= 1024 && unit < UNITS.length - 1) {
    value /= 1024;
    unit += 1;
  }
  if (unit === 0) return `${Math.round(value)} B`;
  if (Number(value.toFixed(1)) >= 1024 && unit < UNITS.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(1)} ${UNITS[unit]}`;
}

/** Locale-aware "Oct 31, 2026, 6:30 PM"; "—" for null or unparsable input. */
export function formatDateTime(iso: string | null, locale: Locale): string {
  if (!iso) return DASH;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return DASH;
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(date);
}
