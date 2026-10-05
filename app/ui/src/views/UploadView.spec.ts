vi.mock("@/composables/useUpload", async (original) => {
  const actual = await original<typeof import("@/composables/useUpload")>();
  const start = vi.fn().mockResolvedValue(undefined);
  return { ...actual, useUpload: () => ({ ...actual.useUpload(), start }) };
});
vi.mock("@/composables/useStudio", async (original) => {
  const actual = await original<typeof import("@/composables/useStudio")>();
  return { ...actual, useStudio: () => ({ ...actual.useStudio(), refresh: vi.fn(), refreshSounds: vi.fn() }) };
});
import { mount } from "@vue/test-utils";
import { beforeEach, afterEach, expect, it, vi } from "vitest";
import UploadView from "./UploadView.vue";
import { useUpload } from "@/composables/useUpload";
import { useStudio } from "@/composables/useStudio";
import { CATEGORY_DEFAULT } from "@/lib/profiles";
import { useI18n } from "@/i18n";
import { makeCategory, makeSeason, makeProfile } from "@/test/factories";
const wrappers: ReturnType<typeof mount>[] = [];
beforeEach(() => {
  vi.clearAllMocks();
  useUpload().busy.value = false;
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

it.each(["pending", "uploading", "processing", "done", "error"] as const)("shows the upload bar only for active queue status %s", async (status) => {
  const w = mountView();
  useUpload().add([new File(["audio"], "bell.wav")]);
  useUpload().items.value[0]!.status = status;
  await w.vm.$nextTick();
  const active = ["pending", "uploading", "processing"].includes(status);
  expect(w.find('[data-test="upload-bar"]').exists()).toBe(active);
  expect(!!(w.element as HTMLElement).style.paddingBottom).toBe(active);
});
it("keeps the upload bar visible while busy even with no queued rows", async () => {
  const w = mountView();
  useUpload().busy.value = true;
  await w.vm.$nextTick();
  expect(w.find('[data-test="upload-bar"]').exists()).toBe(true);
});
it.each([CATEGORY_DEFAULT, null, "soft"])("upload maps profile choice %s to the start body", async (profile) => {
  const w = mountView();
  useUpload().add([new File(["audio"], "bell.wav")]);
  await w.vm.$nextTick();
  const radioIndex = profile === CATEGORY_DEFAULT ? 0 : profile === null ? 1 : 2;
  await w.findAll('input[type="radio"]')[radioIndex]!.setValue(true);
  await w.get('[data-test="upload-bar"] button').trigger("click");
  expect(useUpload().start).toHaveBeenCalledTimes(1);
  const body = vi.mocked(useUpload().start).mock.calls[0]![0];
  expect(body).toMatchObject({ category_id: "general", seasons: ["regular"], all_seasons: false, tags: [] });
  if (profile === CATEGORY_DEFAULT) expect(body).not.toHaveProperty("profile_id");
  else expect(body.profile_id).toBe(profile);
});
it("labels the sticky bar Processing… when only processing rows remain", async () => {
  const w = mountView();
  useUpload().add([new File(["audio"], "bell.wav")]);
  useUpload().items.value[0]!.status = "processing";
  await w.vm.$nextTick();
  expect(w.get('[data-test="upload-bar"] button').text()).toBe("Processing…");
});
