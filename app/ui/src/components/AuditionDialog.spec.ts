import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import AuditionDialog from "./AuditionDialog.vue";
import { useStudio } from "@/composables/useStudio";
import { useI18n } from "@/i18n";
const audition = vi.hoisted(() => vi.fn());
vi.mock("@/api/client", async (original) => ({
  ...(await original<typeof import("@/api/client")>()),
  ui: { sounds: { audition } },
}));
let wrapper: VueWrapper;
beforeEach(() => {
  useI18n().setLocale("en");
  audition.mockReset();
  useStudio().state.value = null;
});
afterEach(() => {
  wrapper?.unmount();
  document.body.innerHTML = "";
});
function open(previewAvailable = false) {
  wrapper = mount(AuditionDialog, {
    props: { open: true, soundId: "roar", previewAvailable },
    attachTo: document.body,
    global: { stubs: { teleport: true } },
  });
  return wrapper;
}
it("explains how to configure speakers when none exist", () => {
  open();
  expect(wrapper.text()).toContain("No speakers configured");
  expect(wrapper.get("a").attributes("href")).toBe("#/system");
  expect(wrapper.find('[data-test="send-audition"]').exists()).toBe(false);
});
it.each(["script", "media_player"])("lists %s details and only displays script volume", async (kind) => {
  useStudio().state.value = {
    settings: {
      audition_targets: [
        { id: "bar", label: "Bar speaker", entity_id: `${kind}.bar`, kind, volume: 0.4 },
      ],
    },
  } as any;
  audition.mockResolvedValue({ ok: true, url: "http://ha/local/roar.mp3" });
  open(true);
  expect(wrapper.get('input[type="radio"]').attributes("name")).toBeTruthy();
  expect(wrapper.text()).toContain(`${kind}.bar`);
  expect(wrapper.text().includes("40%")).toBe(kind === "script");
  await wrapper.get('[data-test="use-preview"]').setValue(true);
  await wrapper.get('[data-test="send-audition"]').trigger("click");
  await flushPromises();
  expect(audition).toHaveBeenCalledWith("roar", { target_id: "bar", use_preview: true });
  expect(wrapper.text()).toContain("http://ha/local/roar.mp3");
});
it("shows errors inline and keeps the target available for retry", async () => {
  useStudio().state.value = {
    settings: {
      audition_targets: [
        { id: "lion", label: "Lion button", entity_id: "script.roar", kind: "script", volume: null },
      ],
    },
  } as any;
  audition.mockRejectedValue(new Error("Speaker offline"));
  open();
  await wrapper.get('[data-test="send-audition"]').trigger("click");
  await flushPromises();
  expect(wrapper.get('[role="alert"]').text()).toBe("Speaker offline");
  expect(wrapper.get('[data-test="send-audition"]').attributes("disabled")).toBeUndefined();
  expect(wrapper.find('[data-test="use-preview"]').exists()).toBe(false);
});
