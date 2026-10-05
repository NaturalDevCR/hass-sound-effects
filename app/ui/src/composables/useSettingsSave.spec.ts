import { expect, it, vi, afterEach, beforeEach } from "vitest";
import { flushPromises } from "@vue/test-utils";
import type { Settings, State } from "@/api/types";
import { useToast } from "./useToast";
import { ui, ApiError } from "@/api/client";
import { useStudio } from "./useStudio";
import { useSettingsSave } from "./useSettingsSave";
import { makeState } from "@/test/system";
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}
let savedSettings: Settings;
beforeEach(() => {
  savedSettings = makeState().settings;
  useStudio().state.value = makeState();
  vi.spyOn(ui, "state").mockImplementation(async () => ({ ...makeState(), settings: savedSettings }));
  vi.spyOn(ui.categories, "list").mockResolvedValue([]);
  vi.spyOn(ui.seasons, "list").mockResolvedValue([]);
  vi.spyOn(ui.profiles, "list").mockResolvedValue([]);
  vi.spyOn(ui.sounds, "list").mockResolvedValue([]);
});
afterEach(() => {
  vi.restoreAllMocks();
  useToast().toasts.value = [];
});
it("merges queued independent panel saves with the latest settings", async () => {
  useStudio().state.value = makeState();
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  const put = vi
    .spyOn(ui.settings, "put")
    .mockImplementationOnce(async (settings) => {
      await gate;
      savedSettings = settings;
      return settings;
    })
    .mockImplementation(async (settings) => (savedSettings = settings));
  const media = useSettingsSave(),
    limits = useSettingsSave();
  const first = media.save({ media_base_url: "https://ha.local" });
  const second = limits.save({ max_upload_mb: 200 });
  await Promise.resolve();
  expect(put).toHaveBeenCalledOnce();
  expect(limits.pending.value).toBe(true);
  release();
  await Promise.all([first, second]);
  expect(put).toHaveBeenLastCalledWith({
    ...makeState().settings,
    media_base_url: "https://ha.local",
    max_upload_mb: 200,
  });
  expect(media.pending.value).toBe(false);
  expect(limits.pending.value).toBe(false);
});
it("retains server validation details inline", async () => {
  useStudio().state.value = makeState();
  vi.spyOn(ui.settings, "put").mockRejectedValue(new ApiError(422, "entity_id: Unknown entity"));
  const panel = useSettingsSave();
  expect(await panel.save({ audition_targets: [] })).toBe(false);
  expect(panel.error.value).toBe("entity_id: Unknown entity");
  expect(panel.pending.value).toBe(false);
});

it.each([false, true])("preserves PUT settings through an older token-rotation refresh and queued saves (refresh fails: %s)", async (fails) => {
  const studio = useStudio();
  const stale = deferred<State>();
  const fresh = deferred<State>();
  const stateGet = vi.mocked(ui.state)
    .mockReturnValueOnce(stale.promise)
    .mockImplementationOnce(() => fails ? Promise.reject(new Error("offline")) : fresh.promise);
  const put = vi.spyOn(ui.settings, "put").mockImplementation(async (settings) => {
    // The server's canonical response must become the basis of subsequent saves.
    savedSettings = { ...settings, media_base_url: "https://ha.local/" };
    return savedSettings;
  });
  vi.spyOn(ui, "rotateToken").mockResolvedValue({ api_token_masked: "••••rotated" });
  await ui.rotateToken();
  const rotationRefresh = studio.refresh(); // ConnectionPanel refresh after token/rotate
  const media = useSettingsSave(), limits = useSettingsSave();
  const first = media.save({ media_base_url: "https://ha.local" });
  const second = limits.save({ max_upload_mb: 200 });
  await flushPromises();
  expect(studio.state.value?.settings.media_base_url).toBe("https://ha.local/");
  expect(put).toHaveBeenCalledOnce();
  expect(stateGet).toHaveBeenCalledOnce();

  stale.resolve({ ...makeState(), api_token_masked: "••••rotated" });
  await rotationRefresh;
  expect(studio.state.value?.settings.media_base_url).toBe("https://ha.local/");
  expect(studio.state.value?.api_token_masked).toBe("••••rotated");
  if (!fails) {
    await flushPromises();
    expect(stateGet).toHaveBeenCalledTimes(2);
    expect(put).toHaveBeenCalledOnce();
    fresh.resolve({ ...makeState(), settings: savedSettings });
  }
  await expect(Promise.all([first, second])).resolves.toEqual([true, true]);
  expect(stateGet).toHaveBeenCalledTimes(3);
  expect(put).toHaveBeenLastCalledWith({
    ...makeState().settings, media_base_url: "https://ha.local/", max_upload_mb: 200,
  });
  expect(studio.state.value?.settings).toEqual(savedSettings);
});
