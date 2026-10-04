vi.mock("@/composables/useStudio", async (original) => {
  const actual = await original<typeof import("@/composables/useStudio")>();
  return { ...actual, useStudio: () => ({ ...actual.useStudio(), refresh: vi.fn(), refreshSounds: vi.fn() }) };
});
import { mount } from "@vue/test-utils";
import { beforeEach, afterEach, expect, it, vi } from "vitest";
import UploadView from "./UploadView.vue";
import { useUpload } from "@/composables/useUpload";
import { useStudio } from "@/composables/useStudio";
import { useI18n } from "@/i18n";
import { makeCategory, makeSeason, makeProfile } from "@/test/factories";
const wrappers: ReturnType<typeof mount>[] = [];
beforeEach(() => {
  useI18n().setLocale("en");
  useStudio().loaded.value = true;
  useStudio().categories.value = [makeCategory({ id: "general", name: "General" }), makeCategory({ id: "bells", name: "Bells" })];
  useStudio().seasons.value = [makeSeason({ id: "regular", name: "Regular" })];
  useStudio().profiles.value = [makeProfile({ id: "soft", name: "Soft" })];
  useUpload().items.value = [];
});
afterEach(() => { wrappers.splice(0).forEach((w) => w.unmount()); });
function mountView() {
  const w = mount(UploadView, { global: { stubs: { RouterLink: true } } });
  wrappers.push(w);
  return w;
}
it("only displays the sticky bar while files are queued and leaves measured clearance", async () => {
  const w = mountView();
  expect(w.find('[data-test="upload-bar"]').exists()).toBe(false);
  useUpload().add([new File(["audio"], "bell.wav")]);
  await w.vm.$nextTick();
  const bar = w.get('[data-test="upload-bar"]');
  expect(bar.classes()).toContain("bottom-[var(--tabbar-h)]");
  expect(bar.classes()).toContain("pb-3");
  expect(bar.classes()).toContain("md:pb-[max(0.75rem,env(safe-area-inset-bottom))]");
  expect(parseFloat((w.element as HTMLElement).style.paddingBottom)).toBeGreaterThan(0);
  useUpload().remove(useUpload().items.value[0]!.id);
  await w.vm.$nextTick();
  expect(w.find('[data-test="upload-bar"]').exists()).toBe(false);
});
it("summarizes category, seasons and profile in the collapsed defaults toggle", async () => {
  const w = mountView();
  expect(w.get('[data-test="defaults-summary"]').text()).toBe("General · Regular · Category default");
  await w.get('[aria-controls="upload-defaults"]').trigger("click");
  expect(w.find('[data-test="defaults-summary"]').exists()).toBe(false);
  await w.get("#upload-category").setValue("bells");
  await w.get('[role="switch"]').trigger("click");
  await w.findAll('input[type="radio"]').at(-1)!.setValue();
  await w.get('[aria-controls="upload-defaults"]').trigger("click");
  expect(w.get('[data-test="defaults-summary"]').text()).toBe("Bells · All seasons · Soft");
});
it("hides retry for validation failures but keeps it for failed transfers", async () => {
  const w = mountView();
  useStudio().state.value = { settings: { max_upload_mb: 1 } } as never;
  useUpload().add([new File(["x"], "bad.exe"), new File([], "empty.wav"), new File([new Uint8Array(2 * 1024 * 1024)], "large.wav")]);
  await w.vm.$nextTick();
  expect(w.findAll('button[aria-label^="Retry"]')).toHaveLength(0);
  useUpload().add([new File(["x"], "retry.wav")]);
  const item = useUpload().items.value.at(-1)!;
  item.status = "error";
  item.error = "Offline";
  await w.vm.$nextTick();
  expect(w.findAll('button[aria-label^="Retry"]')).toHaveLength(1);
  item.status = "processing";
  item.error = null;
  await w.vm.$nextTick();
  expect(w.find('button[aria-label="Remove retry.wav"]').exists()).toBe(true);
  useStudio().state.value = null;
});
