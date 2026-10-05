import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Category, Profile, Season, Sound, State } from "@/api/types";

const mocks = vi.hoisted(() => ({
  ui: {
    state: vi.fn(),
    categories: { list: vi.fn() },
    seasons: { list: vi.fn() },
    profiles: { list: vi.fn() },
    sounds: { list: vi.fn() },
  },
}));

vi.mock("@/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/client")>()),
  ui: mocks.ui,
}));

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const category = { id: "general", name: "General" } as Category;
const season = { id: "regular", name: "Regular" } as Season;
const profile = { id: "standard", name: "Standard" } as Profile;
const sound = { id: "s1", title: "Bell" } as Sound;
const state = { version: "1.0.0" } as State;

async function load() {
  vi.resetModules();
  const { ApiError } = await import("@/api/client");
  const { useStudio } = await import("@/composables/useStudio");
  return { ApiError, useStudio };
}

beforeEach(() => {
  vi.resetAllMocks(); // also drops queued mock*Once values a failing test left behind
  mocks.ui.state.mockResolvedValue(state);
  mocks.ui.categories.list.mockResolvedValue([category]);
  mocks.ui.seasons.list.mockResolvedValue([season]);
  mocks.ui.profiles.list.mockResolvedValue([profile]);
  mocks.ui.sounds.list.mockResolvedValue([sound]);
});

describe("useStudio", () => {
  it("starts out loading and not loaded so views can skip their empty state", async () => {
    const { useStudio } = await load();
    const studio = useStudio();
    expect(studio.loading.value).toBe(true);
    expect(studio.loaded.value).toBe(false);
    await studio.refresh();
    expect(studio.loading.value).toBe(false);
    expect(studio.loaded.value).toBe(true);
  });

  it("settles loading but stays not loaded when the first refresh fails; later success loads", async () => {
    const { useStudio } = await load();
    mocks.ui.state.mockRejectedValueOnce(new Error("offline"));
    const studio = useStudio();
    await studio.refresh();
    expect(studio.loading.value).toBe(false);
    expect(studio.loaded.value).toBe(false);
    await studio.refresh();
    expect(studio.loaded.value).toBe(true);
  });

  it("keeps loaded true (and the old data) when a later refresh fails", async () => {
    const { useStudio } = await load();
    const studio = useStudio();
    await studio.refresh();
    mocks.ui.sounds.list.mockRejectedValueOnce(new Error("blip"));
    await studio.refresh();
    expect(studio.loaded.value).toBe(true);
    expect(studio.sounds.value).toEqual([sound]);
    expect(studio.error.value).toBe("blip");
  });

  it("loads everything in parallel", async () => {
    const { useStudio } = await load();
    const gates = Object.fromEntries(
      ["state", "categories", "seasons", "profiles", "sounds"].map((k) => [k, deferred<unknown>()]),
    );
    mocks.ui.state.mockReturnValue(gates.state.promise);
    mocks.ui.categories.list.mockReturnValue(gates.categories.promise);
    mocks.ui.seasons.list.mockReturnValue(gates.seasons.promise);
    mocks.ui.profiles.list.mockReturnValue(gates.profiles.promise);
    mocks.ui.sounds.list.mockReturnValue(gates.sounds.promise);

    const studio = useStudio();
    const pending = studio.refresh();
    expect(studio.loading.value).toBe(true);
    // every request is in flight before any of them resolved
    expect(mocks.ui.state).toHaveBeenCalledTimes(1);
    expect(mocks.ui.categories.list).toHaveBeenCalledTimes(1);
    expect(mocks.ui.seasons.list).toHaveBeenCalledTimes(1);
    expect(mocks.ui.profiles.list).toHaveBeenCalledTimes(1);
    expect(mocks.ui.sounds.list).toHaveBeenCalledTimes(1);

    gates.state.resolve(state);
    gates.categories.resolve([category]);
    gates.seasons.resolve([season]);
    gates.profiles.resolve([profile]);
    gates.sounds.resolve([sound]);
    await pending;

    expect(studio.loading.value).toBe(false);
    expect(studio.error.value).toBeNull();
    expect(studio.state.value).toEqual(state);
    expect(studio.categories.value).toEqual([category]);
    expect(studio.seasons.value).toEqual([season]);
    expect(studio.profiles.value).toEqual([profile]);
    expect(studio.sounds.value).toEqual([sound]);
  });

  it("shares one store between callers", async () => {
    const { useStudio } = await load();
    await useStudio().refresh();
    expect(useStudio().sounds.value).toEqual([sound]);
  });

  it("deduplicates overlapping refreshes", async () => {
    const { useStudio } = await load();
    const studio = useStudio();
    await Promise.all([studio.refresh(), studio.refresh()]);
    expect(mocks.ui.state).toHaveBeenCalledTimes(1);
  });

  it.each([false, true])("forced refresh waits for an in-flight refresh then fetches again (first fails: %s)", async (fails) => {
    const { useStudio } = await load();
    const studio = useStudio();
    const first = deferred<State>();
    const second = deferred<State>();
    mocks.ui.state.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    const a = studio.refresh();
    const b = studio.refresh({ force: true });
    const c = studio.refresh({ force: true });
    expect(mocks.ui.state).toHaveBeenCalledTimes(1);
    let settled = false;
    void b.then(() => (settled = true));
    if (fails) first.reject(new Error("offline"));
    else first.resolve(state);
    await a;
    await Promise.resolve();
    expect(mocks.ui.state).toHaveBeenCalledTimes(2);
    expect(settled).toBe(false);
    const fresh = { ...state, version: "2.0.0" };
    second.resolve(fresh);
    await Promise.all([b, c]);
    expect(studio.state.value).toEqual(fresh);
    expect(studio.error.value).toBeNull();
    expect(studio.loading.value).toBe(false);
    await studio.refresh({ force: true });
    expect(mocks.ui.state).toHaveBeenCalledTimes(3);
  });

  it("records the error message instead of throwing, then recovers", async () => {
    const { useStudio, ApiError } = await load();
    mocks.ui.sounds.list.mockRejectedValueOnce(new ApiError(500, "Database is locked"));
    const studio = useStudio();
    await expect(studio.refresh()).resolves.toBeUndefined();
    expect(studio.error.value).toBe("Database is locked");
    expect(studio.loading.value).toBe(false);

    await studio.refresh();
    expect(studio.error.value).toBeNull();
    expect(studio.sounds.value).toEqual([sound]);
  });

  it("refreshSounds only reloads the sound list", async () => {
    const { useStudio } = await load();
    const studio = useStudio();
    mocks.ui.sounds.list.mockResolvedValueOnce([sound, { id: "s2" } as Sound]);
    await studio.refreshSounds();
    expect(studio.sounds.value).toHaveLength(2);
    expect(mocks.ui.state).not.toHaveBeenCalled();
    expect(mocks.ui.categories.list).not.toHaveBeenCalled();
  });

  it("clears a previous error when refreshSounds succeeds once the studio has loaded", async () => {
    const { useStudio } = await load();
    const studio = useStudio();
    await studio.refresh();
    mocks.ui.sounds.list.mockRejectedValueOnce(new Error("offline"));
    await studio.refreshSounds();
    expect(studio.error.value).toBe("offline");
    await studio.refreshSounds();
    expect(studio.error.value).toBeNull();
  });

  it("keeps the error of a failed first load when a lightweight refreshSounds succeeds", async () => {
    const { useStudio } = await load();
    const studio = useStudio();
    mocks.ui.state.mockRejectedValueOnce(new Error("Studio is unreachable"));
    await studio.refresh();
    expect(studio.loaded.value).toBe(false);
    expect(studio.error.value).toBe("Studio is unreachable");

    // e.g. a job-completion poll succeeds while the categories/state are still missing
    await studio.refreshSounds();
    expect(studio.sounds.value).toEqual([sound]);
    expect(studio.error.value).toBe("Studio is unreachable");
    expect(studio.loaded.value).toBe(false);

    await studio.refresh(); // Retry
    expect(studio.error.value).toBeNull();
    expect(studio.loaded.value).toBe(true);
  });

  it("makes a refreshSounds call that arrives mid-flight wait, then fetch once more", async () => {
    const { useStudio } = await load();
    const studio = useStudio();
    await studio.refresh();
    mocks.ui.sounds.list.mockClear();
    const first = deferred<Sound[]>();
    const second = deferred<Sound[]>();
    mocks.ui.sounds.list.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);

    const a = studio.refreshSounds();
    const b = studio.refreshSounds();
    expect(mocks.ui.sounds.list).toHaveBeenCalledTimes(1);
    let bSettled = false;
    void b.then(() => (bSettled = true));

    // the request that was already in flight may predate the caller's mutation: it must not satisfy b
    first.resolve([sound]);
    await a;
    await Promise.resolve();
    expect(mocks.ui.sounds.list).toHaveBeenCalledTimes(2);
    expect(bSettled).toBe(false);

    second.resolve([sound, { id: "s2" } as Sound]);
    await b;
    expect(studio.sounds.value).toHaveLength(2);
  });

  it("coalesces many concurrent refreshSounds callers into one trailing request", async () => {
    const { useStudio } = await load();
    const studio = useStudio();
    await studio.refresh();
    mocks.ui.sounds.list.mockClear();
    const first = deferred<Sound[]>();
    mocks.ui.sounds.list.mockReturnValueOnce(first.promise);

    const calls = [studio.refreshSounds(), studio.refreshSounds(), studio.refreshSounds(), studio.refreshSounds()];
    expect(mocks.ui.sounds.list).toHaveBeenCalledTimes(1);
    first.resolve([sound]);
    await Promise.all(calls);
    expect(mocks.ui.sounds.list).toHaveBeenCalledTimes(2);

    // everything settled: the next call starts a fresh request
    await studio.refreshSounds();
    expect(mocks.ui.sounds.list).toHaveBeenCalledTimes(3);
  });

  it("still settles every caller (and keeps the error) when the trailing refreshSounds fails", async () => {
    const { useStudio } = await load();
    const studio = useStudio();
    await studio.refresh();
    const first = deferred<Sound[]>();
    mocks.ui.sounds.list.mockReturnValueOnce(first.promise).mockRejectedValueOnce(new Error("blip"));
    const a = studio.refreshSounds();
    const b = studio.refreshSounds();
    first.resolve([sound]);
    await expect(Promise.all([a, b])).resolves.toBeDefined();
    expect(studio.error.value).toBe("blip");
  });

  it("reports refreshSounds failures through error", async () => {
    const { useStudio } = await load();
    mocks.ui.sounds.list.mockRejectedValueOnce(new Error("offline"));
    const studio = useStudio();
    await studio.refreshSounds();
    expect(studio.error.value).toBe("offline");
  });

  it("looks entities up by id", async () => {
    const { useStudio } = await load();
    const studio = useStudio();
    await studio.refresh();
    expect(studio.categoryById("general")).toEqual(category);
    expect(studio.seasonById("regular")).toEqual(season);
    expect(studio.profileById("standard")).toEqual(profile);
    expect(studio.categoryById("nope")).toBeUndefined();
    expect(studio.profileById(null)).toBeUndefined();
  });
});
