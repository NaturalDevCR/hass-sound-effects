import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, audioUrl, messageOf, ui } from "@/api/client";
import { useI18n } from "@/i18n";

const fetchMock = vi.fn();

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

function lastCall() {
  const [url, init] = fetchMock.mock.calls.at(-1) as [string, RequestInit];
  return { url, init, headers: new Headers(init.headers) };
}

beforeEach(() => {
  useI18n().setLocale("en");
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

describe("api()", () => {
  it("keeps the path relative (Ingress safe) and parses JSON", async () => {
    fetchMock.mockResolvedValue(jsonResponse([{ id: "x" }]));
    const out = await api<{ id: string }[]>("api/ui/sounds");
    expect(out).toEqual([{ id: "x" }]);
    expect(lastCall().url).toBe("api/ui/sounds");
    expect(lastCall().headers.get("accept")).toContain("application/json");
  });

  it("strips accidental leading slashes", async () => {
    fetchMock.mockResolvedValue(jsonResponse({}));
    await api("/api/ui/state");
    expect(lastCall().url).toBe("api/ui/state");
  });

  it("serializes `json` with a content-type header", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }));
    await api("api/ui/categories", { method: "POST", json: { name: "Doors" } });
    const { init, headers } = lastCall();
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({ name: "Doors" }));
    expect(headers.get("content-type")).toBe("application/json");
  });

  it("does not force a content-type on raw bodies", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ received: 3 }));
    const blob = new Blob(["abc"]);
    await api("api/ui/uploads/u/chunks/0", { method: "PUT", body: blob });
    expect(lastCall().init.body).toBe(blob);
    expect(lastCall().headers.get("content-type")).toBeNull();
  });

  it("turns {detail} errors into ApiError", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: "Category already exists" }, 409));
    const failure = api("api/ui/categories", { method: "POST", json: {} });
    await expect(failure).rejects.toBeInstanceOf(ApiError);
    await expect(failure).rejects.toMatchObject({
      status: 409,
      detail: "Category already exists",
      message: "Category already exists",
    });
  });

  it("flattens FastAPI validation arrays", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ detail: [{ loc: ["body", "name"], msg: "Field required", type: "missing" }] }, 422),
    );
    await expect(api("api/ui/categories")).rejects.toMatchObject({ status: 422, detail: "name: Field required" });
  });

  it("names the offending field using the last loc element", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        {
          detail: [
            { loc: ["body", "title"], msg: "Field required", type: "missing" },
            { loc: ["body", "tags", 0], msg: "Input should be a valid string", type: "string_type" },
            { loc: ["body"], msg: "Bad body", type: "x" },
          ],
        },
        422,
      ),
    );
    await expect(api("api/ui/sounds/s1", { method: "PATCH", json: {} })).rejects.toMatchObject({
      status: 422,
      detail: "title: Field required; tags: Input should be a valid string; Bad body",
    });
  });

  it("turns a 2xx response that is not JSON into an ApiError, not a SyntaxError", async () => {
    fetchMock.mockResolvedValue(new Response("<html>Ingress login</html>", { status: 200 }));
    const error = await api("api/ui/state").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 200, detail: "Invalid server response" });
  });

  it("treats an empty 2xx body as undefined", async () => {
    fetchMock.mockResolvedValue(new Response("", { status: 200 }));
    await expect(api("api/ui/token/rotate", { method: "POST" })).resolves.toBeUndefined();
  });

  it("falls back to a readable message for non-JSON failures", async () => {
    fetchMock.mockResolvedValue(new Response("<html>bad gateway</html>", { status: 502 }));
    const error = await api("api/ui/state").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(502);
    expect((error as ApiError).detail).toContain("502");
  });

  it("maps network failures to ApiError status 0", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(api("api/ui/state")).rejects.toMatchObject({ status: 0 });
  });

  it("lets aborts through untouched", async () => {
    const abort = new DOMException("aborted", "AbortError");
    fetchMock.mockRejectedValue(abort);
    await expect(api("api/ui/state")).rejects.toBe(abort);
  });

  it("returns undefined for 204", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await expect(api("api/ui/categories/x", { method: "DELETE" })).resolves.toBeUndefined();
  });
});

describe("audioUrl()", () => {
  it("builds relative stream URLs with an optional cache buster", () => {
    expect(audioUrl("abc", "original")).toBe("api/ui/sounds/abc/original");
    expect(audioUrl("abc", "published", 3)).toBe("api/ui/sounds/abc/published?v=3");
    expect(audioUrl("abc", "preview", "t1")).toBe("api/ui/sounds/abc/preview?v=t1");
  });
});

describe("ui endpoints", () => {
  beforeEach(() => fetchMock.mockImplementation(async () => jsonResponse({})));

  const call = async (run: () => Promise<unknown>) => {
    await run();
    const { url, init, headers } = lastCall();
    return {
      url,
      method: init.method ?? "GET",
      body: typeof init.body === "string" ? JSON.parse(init.body) : init.body,
      contentType: headers.get("content-type"),
    };
  };

  it("covers state, token and settings", async () => {
    expect(await call(() => ui.state())).toMatchObject({ url: "api/ui/state", method: "GET" });
    expect(await call(() => ui.token())).toMatchObject({ url: "api/ui/token", method: "GET" });
    expect(await call(() => ui.rotateToken())).toMatchObject({ url: "api/ui/token/rotate", method: "POST" });
    expect(await call(() => ui.settings.get())).toMatchObject({ url: "api/ui/settings", method: "GET" });
    const settings = { max_upload_mb: 50, max_duration_s: 60, audition_targets: [], media_base_url: "" };
    expect(await call(() => ui.settings.put(settings))).toMatchObject({
      url: "api/ui/settings",
      method: "PUT",
      body: settings,
    });
  });

  it("covers categories", async () => {
    expect(await call(() => ui.categories.list())).toMatchObject({ url: "api/ui/categories" });
    expect(await call(() => ui.categories.create({ name: "Doors" }))).toMatchObject({
      url: "api/ui/categories",
      method: "POST",
      body: { name: "Doors" },
    });
    expect(await call(() => ui.categories.update("doors", { color: "#fff" }))).toMatchObject({
      url: "api/ui/categories/doors",
      method: "PATCH",
      body: { color: "#fff" },
    });
    expect(await call(() => ui.categories.remove("doors"))).toMatchObject({
      url: "api/ui/categories/doors",
      method: "DELETE",
    });
    expect(await call(() => ui.categories.reorder(["b", "a"]))).toMatchObject({
      url: "api/ui/categories/order",
      method: "PUT",
      body: { ids: ["b", "a"] },
    });
  });

  it("covers seasons", async () => {
    expect(await call(() => ui.seasons.list())).toMatchObject({ url: "api/ui/seasons" });
    expect(await call(() => ui.seasons.create({ name: "Halloween", start: "10-01", end: "10-31" }))).toMatchObject({
      method: "POST",
      url: "api/ui/seasons",
    });
    expect(await call(() => ui.seasons.update("halloween", { priority: 5 }))).toMatchObject({
      url: "api/ui/seasons/halloween",
      method: "PATCH",
    });
    expect(await call(() => ui.seasons.remove("halloween"))).toMatchObject({ method: "DELETE" });
    expect(await call(() => ui.seasons.resolve("2026-10-31"))).toMatchObject({
      url: "api/ui/seasons/resolve?date=2026-10-31",
      method: "GET",
    });
  });

  it("covers profiles", async () => {
    expect(await call(() => ui.profiles.list())).toMatchObject({ url: "api/ui/profiles" });
    expect(
      await call(() => ui.profiles.create({ name: "Mine", target_lufs: -16, true_peak: -1.5, lra: 11 })),
    ).toMatchObject({ method: "POST" });
    expect(await call(() => ui.profiles.update("loud", { target_lufs: -12 }))).toMatchObject({
      url: "api/ui/profiles/loud",
      method: "PATCH",
    });
    expect(await call(() => ui.profiles.remove("loud"))).toMatchObject({ method: "DELETE" });
    expect(await call(() => ui.profiles.apply("loud", { category_id: "doors" }))).toMatchObject({
      url: "api/ui/profiles/loud/apply",
      method: "POST",
      body: { category_id: "doors" },
    });
  });

  it("covers sounds", async () => {
    const recipe = { trim_start: 0, trim_end: null, gain_db: 0, fade_in: 0, fade_out: 0, profile_id: null };
    expect(await call(() => ui.sounds.list())).toMatchObject({ url: "api/ui/sounds" });
    expect(await call(() => ui.sounds.get("s1"))).toMatchObject({ url: "api/ui/sounds/s1" });
    expect(await call(() => ui.sounds.update("s1", { title: "New" }))).toMatchObject({
      url: "api/ui/sounds/s1",
      method: "PATCH",
      body: { title: "New" },
    });
    expect(await call(() => ui.sounds.putRecipe("s1", recipe))).toMatchObject({
      url: "api/ui/sounds/s1/recipe",
      method: "PUT",
      body: recipe,
    });
    expect(await call(() => ui.sounds.preview("s1", recipe))).toMatchObject({
      url: "api/ui/sounds/s1/preview",
      method: "POST",
      body: recipe,
    });
    expect(await call(() => ui.sounds.remove("s1"))).toMatchObject({ method: "DELETE" });
    expect(await call(() => ui.sounds.bulk({ ids: ["s1"], set: { enabled: false } }))).toMatchObject({
      url: "api/ui/sounds/bulk",
      method: "POST",
      body: { ids: ["s1"], set: { enabled: false } },
    });
    expect(await call(() => ui.sounds.bulkDelete(["s1", "s2"]))).toMatchObject({
      url: "api/ui/sounds/bulk-delete",
      method: "POST",
      body: { ids: ["s1", "s2"] },
    });
    expect(await call(() => ui.sounds.audition("s1", { target_id: "t", use_preview: true }))).toMatchObject({
      url: "api/ui/sounds/s1/audition",
      method: "POST",
      body: { target_id: "t", use_preview: true },
    });
  });

  it("covers chunked uploads", async () => {
    expect(await call(() => ui.uploads.create("a.wav", 12))).toMatchObject({
      url: "api/ui/uploads",
      method: "POST",
      body: { filename: "a.wav", size: 12 },
    });
    const blob = new Blob(["xyz"]);
    const chunk = await call(() => ui.uploads.chunk("u1", 2, blob));
    expect(chunk).toMatchObject({ url: "api/ui/uploads/u1/chunks/2", method: "PUT", body: blob });
    expect(chunk.contentType).toBe("application/octet-stream");
    const done = { category_id: "general", seasons: ["regular"], all_seasons: false, tags: [] };
    expect(await call(() => ui.uploads.complete("u1", done))).toMatchObject({
      url: "api/ui/uploads/u1/complete",
      method: "POST",
      body: done,
    });
  });

  it("covers import and jobs", async () => {
    expect(await call(() => ui.importer.browse(""))).toMatchObject({ url: "api/ui/import/browse?path=" });
    expect(await call(() => ui.importer.browse("media/sfx dir"))).toMatchObject({
      url: "api/ui/import/browse?path=media%2Fsfx%20dir",
    });
    const body = { paths: ["media/a.wav"], category_id: "general", seasons: ["regular"], all_seasons: false, tags: [] };
    expect(await call(() => ui.importer.run(body))).toMatchObject({ url: "api/ui/import", method: "POST", body });
    expect(await call(() => ui.jobs())).toMatchObject({ url: "api/ui/jobs", method: "GET" });
  });

  it("encodes path segments", async () => {
    expect(await call(() => ui.sounds.get("a/b"))).toMatchObject({ url: "api/ui/sounds/a%2Fb" });
  });
});

describe("messageOf()", () => {
  it("uses the API detail, the message of any other Error, or the stringified value", () => {
    expect(messageOf(new ApiError(409, "Category already exists"))).toBe("Category already exists");
    expect(messageOf(new Error("offline"))).toBe("offline");
    expect(messageOf("plain text")).toBe("plain text");
    expect(messageOf(42)).toBe("42");
    expect(messageOf(undefined)).toBe("undefined");
  });
});
