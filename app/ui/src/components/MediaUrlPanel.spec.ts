import { mount, flushPromises } from "@vue/test-utils";
import { afterEach, expect, it, vi } from "vitest";
import MediaUrlPanel from "./MediaUrlPanel.vue";
import { ui } from "@/api/client";
import { useStudio } from "@/composables/useStudio";
import { makeState } from "@/test/system";
vi.mock("@/composables/useStudio", async (original) => {
  const actual = await original<typeof import("@/composables/useStudio")>();
  return { useStudio: () => ({ ...actual.useStudio(), refresh: vi.fn() }) };
});
afterEach(() => vi.restoreAllMocks());
it("rejects non-http URLs, saves an override and allows empty auto detection", async () => {
  useStudio().state.value = makeState();
  const put = vi.spyOn(ui.settings, "put").mockImplementation(async (s) => s);
  const w = mount(MediaUrlPanel);
  await w.get("input").setValue("ftp://host");
  await w.get("form").trigger("submit");
  expect(put).not.toHaveBeenCalled();
  expect(w.find('[role="alert"]').exists()).toBe(true);
  await w.get("input").setValue("https://ha.local:8123");
  await w.get("form").trigger("submit");
  await flushPromises();
  expect(put).toHaveBeenLastCalledWith({ ...makeState().settings, media_base_url: "https://ha.local:8123" });
  await w.get("input").setValue("");
  await w.get("form").trigger("submit");
  await flushPromises();
  expect(put).toHaveBeenLastCalledWith(makeState().settings);
  w.unmount();
});
