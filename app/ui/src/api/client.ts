import { translate } from "@/i18n";
import type {
  AudioKind,
  AuditionBody,
  BrowseResult,
  BulkBody,
  BulkResult,
  Category,
  CategoryInput,
  CategoryPatch,
  ImportBody,
  Job,
  Profile,
  ProfileApplyBody,
  ProfileInput,
  ProfilePatch,
  ProfileUpdateResult,
  Recipe,
  Season,
  SeasonInput,
  SeasonPatch,
  Settings,
  Sound,
  SoundPatch,
  State,
  UploadComplete,
  UploadInit,
} from "./types";

/** Failure reported by the Studio API (or `status: 0` when it could not be reached at all). */
export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

type ApiInit = RequestInit & { json?: unknown };

/** FastAPI sends `{detail: "text"}` or, for 422s, `{detail: [{msg, loc, ...}]}`. */
async function readDetail(response: Response): Promise<string> {
  const fallback = response.statusText || translate("error.http", { status: response.status });
  try {
    const body: unknown = await response.json();
    const detail = (body as { detail?: unknown } | null)?.detail;
    if (typeof detail === "string" && detail) return detail;
    if (Array.isArray(detail)) {
      const messages = detail
        .map((item) => (typeof item === "string" ? item : (item as { msg?: unknown })?.msg))
        .filter((msg): msg is string => typeof msg === "string" && msg !== "");
      if (messages.length) return messages.join("; ");
    }
  } catch {
    // body was not JSON (proxy error page, empty body)
  }
  return fallback;
}

/**
 * Calls the Studio API. `path` is relative on purpose ("api/ui/sounds"): behind
 * Home Assistant Ingress the app lives under an unknown prefix, so a leading
 * slash would escape it.
 */
export async function api<T>(path: string, init: ApiInit = {}): Promise<T> {
  const { json, headers: initHeaders, body, ...rest } = init;
  const headers = new Headers(initHeaders);
  if (!headers.has("accept")) headers.set("accept", "application/json");
  let payload = body;
  if (json !== undefined) {
    payload = JSON.stringify(json);
    if (!headers.has("content-type")) headers.set("content-type", "application/json");
  }

  let response: Response;
  try {
    response = await fetch(path.replace(/^\/+/, ""), { ...rest, headers, body: payload });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw new ApiError(0, translate("error.network"));
  }

  if (!response.ok) throw new ApiError(response.status, await readDetail(response));
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

const seg = encodeURIComponent;
const send = (method: string, json?: unknown): ApiInit => (json === undefined ? { method } : { method, json });

/** Every endpoint the UI uses, grouped like the API reference. */
export const ui = {
  state: () => api<State>("api/ui/state"),
  token: () => api<{ token: string }>("api/ui/token"),
  rotateToken: () => api<{ api_token_masked: string }>("api/ui/token/rotate", send("POST")),

  settings: {
    get: () => api<Settings>("api/ui/settings"),
    put: (settings: Settings) => api<Settings>("api/ui/settings", send("PUT", settings)),
  },

  categories: {
    list: () => api<Category[]>("api/ui/categories"),
    create: (body: CategoryInput) => api<Category>("api/ui/categories", send("POST", body)),
    update: (id: string, patch: CategoryPatch) =>
      api<Category>(`api/ui/categories/${seg(id)}`, send("PATCH", patch)),
    remove: (id: string) => api<void>(`api/ui/categories/${seg(id)}`, send("DELETE")),
    reorder: (ids: string[]) => api<Category[]>("api/ui/categories/order", send("PUT", { ids })),
  },

  seasons: {
    list: () => api<Season[]>("api/ui/seasons"),
    create: (body: SeasonInput) => api<Season>("api/ui/seasons", send("POST", body)),
    update: (id: string, patch: SeasonPatch) => api<Season>(`api/ui/seasons/${seg(id)}`, send("PATCH", patch)),
    remove: (id: string) => api<void>(`api/ui/seasons/${seg(id)}`, send("DELETE")),
    resolve: (date: string) =>
      api<{ date: string; season_id: string }>(`api/ui/seasons/resolve?date=${seg(date)}`),
  },

  profiles: {
    list: () => api<Profile[]>("api/ui/profiles"),
    create: (body: ProfileInput) => api<Profile>("api/ui/profiles", send("POST", body)),
    update: (id: string, patch: ProfilePatch) =>
      api<ProfileUpdateResult>(`api/ui/profiles/${seg(id)}`, send("PATCH", patch)),
    remove: (id: string) => api<void>(`api/ui/profiles/${seg(id)}`, send("DELETE")),
    apply: (id: string, body: ProfileApplyBody) =>
      api<{ queued: number }>(`api/ui/profiles/${seg(id)}/apply`, send("POST", body)),
  },

  sounds: {
    list: () => api<Sound[]>("api/ui/sounds"),
    get: (id: string) => api<Sound>(`api/ui/sounds/${seg(id)}`),
    update: (id: string, patch: SoundPatch) => api<Sound>(`api/ui/sounds/${seg(id)}`, send("PATCH", patch)),
    putRecipe: (id: string, recipe: Recipe) =>
      api<{ sound: Sound; job: Job }>(`api/ui/sounds/${seg(id)}/recipe`, send("PUT", recipe)),
    preview: (id: string, recipe: Recipe) =>
      api<{ job: Job }>(`api/ui/sounds/${seg(id)}/preview`, send("POST", recipe)),
    remove: (id: string) => api<void>(`api/ui/sounds/${seg(id)}`, send("DELETE")),
    bulk: (body: BulkBody) => api<BulkResult>("api/ui/sounds/bulk", send("POST", body)),
    bulkDelete: (ids: string[]) =>
      api<{ deleted: number }>("api/ui/sounds/bulk-delete", send("POST", { ids })),
    audition: (id: string, body: AuditionBody) =>
      api<{ ok: true; url: string }>(`api/ui/sounds/${seg(id)}/audition`, send("POST", body)),
  },

  uploads: {
    create: (filename: string, size: number) =>
      api<UploadInit>("api/ui/uploads", send("POST", { filename, size })),
    chunk: (id: string, index: number, blob: Blob) =>
      api<{ received: number }>(`api/ui/uploads/${seg(id)}/chunks/${index}`, {
        method: "PUT",
        body: blob,
        headers: { "content-type": "application/octet-stream" },
      }),
    complete: (id: string, body: UploadComplete) =>
      api<Sound>(`api/ui/uploads/${seg(id)}/complete`, send("POST", body)),
  },

  importer: {
    browse: (path: string) => api<BrowseResult>(`api/ui/import/browse?path=${seg(path)}`),
    run: (body: ImportBody) => api<{ sounds: Sound[] }>("api/ui/import", send("POST", body)),
  },

  jobs: () => api<Job[]>("api/ui/jobs"),
};

/** Relative URL of a sound's audio. `bust` (e.g. the published revision) defeats stale browser caches. */
export function audioUrl(id: string, kind: AudioKind, bust?: string | number): string {
  const base = `api/ui/sounds/${seg(id)}/${kind}`;
  return bust === undefined || bust === "" ? base : `${base}?v=${seg(String(bust))}`;
}
