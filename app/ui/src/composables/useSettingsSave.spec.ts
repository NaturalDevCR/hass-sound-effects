import { expect, it, vi, afterEach } from "vitest";
import { ui, ApiError } from "@/api/client";
import { useStudio } from "./useStudio";
import { useSettingsSave } from "./useSettingsSave";
import { makeState } from "@/test/system";
vi.mock("./useStudio", async (original) => {
  const actual = await original<typeof import("./useStudio")>();
  return { useStudio: () => ({ ...actual.useStudio(), refresh: vi.fn() }) };
});
afterEach(() => vi.restoreAllMocks());
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
      return settings;
    })
    .mockImplementation(async (settings) => settings);
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
