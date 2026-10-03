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
  vi.clearAllMocks();
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

  it("clears a previous error when refreshSounds succeeds", async () => {
    const { useStudio } = await load();
    const studio = useStudio();
    mocks.ui.sounds.list.mockRejectedValueOnce(new Error("offline"));
    await studio.refreshSounds();
    expect(studio.error.value).toBe("offline");
    await studio.refreshSounds();
    expect(studio.error.value).toBeNull();
  });

  it("shares one in-flight refreshSounds request and fetches again afterwards", async () => {
    const { useStudio } = await load();
    const studio = useStudio();
    const gate = deferred<Sound[]>();
    mocks.ui.sounds.list.mockReturnValueOnce(gate.promise);
    const first = studio.refreshSounds();
    const second = studio.refreshSounds();
    expect(mocks.ui.sounds.list).toHaveBeenCalledTimes(1);
    gate.resolve([sound]);
    await Promise.all([first, second]);
    expect(studio.sounds.value).toEqual([sound]);

    await studio.refreshSounds();
    expect(mocks.ui.sounds.list).toHaveBeenCalledTimes(2);
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
