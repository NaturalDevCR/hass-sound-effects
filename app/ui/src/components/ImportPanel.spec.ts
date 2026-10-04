import { mount, flushPromises } from "@vue/test-utils";
import { afterEach, expect, it, vi } from "vitest";
import ImportPanel from "./ImportPanel.vue";
import ImportBrowser from "./ImportBrowser.vue";
import ProfilePicker from "./ProfilePicker.vue";
import { ui } from "@/api/client";
import { useStudio } from "@/composables/useStudio";
import { useJobs } from "@/composables/useJobs";
import { useI18n } from "@/i18n";
import { makeCategory, makeProfile, makeSound } from "@/test/factories";
import { CATEGORY_DEFAULT } from "@/lib/profiles";
vi.mock("@/composables/useStudio", async (original) => {
  const actual = await original<typeof import("@/composables/useStudio")>();
  const refreshSounds = vi.fn();
  return { useStudio: () => ({ ...actual.useStudio(), refreshSounds }) };
});
vi.mock("@/composables/useJobs", () => {
  const refresh = vi.fn();
  return { useJobs: () => ({ refresh }) };
});
afterEach(() => vi.restoreAllMocks());
it.each([CATEGORY_DEFAULT, null, "soft"])(
  "maps import profile %s and refreshes sounds after success",
  async (profile) => {
    useI18n().setLocale("en");
    useStudio().categories.value = [makeCategory({ id: "general" })];
    useStudio().profiles.value = [makeProfile({ id: "soft" })];
    const run = vi.spyOn(ui.importer, "run").mockResolvedValue({ sounds: [makeSound({ id: "new" })] });
    vi.spyOn(ui.importer, "browse").mockResolvedValue({ path: "", parent: null, roots: [], entries: [] });
    const w = mount(ImportPanel);
    await flushPromises();
    w.getComponent(ProfilePicker).vm.$emit("update:modelValue", profile);
    await w.vm.$nextTick();
    w.getComponent(ImportBrowser).vm.$emit("import", ["media/a.wav"]);
    await flushPromises();
    const body = run.mock.calls[0]![0];
    expect(body).toMatchObject({
      paths: ["media/a.wav"],
      category_id: "general",
      seasons: ["regular"],
      all_seasons: false,
      tags: [],
    });
    if (profile === CATEGORY_DEFAULT) expect(body).not.toHaveProperty("profile_id");
    else expect(body.profile_id).toBe(profile);
    expect(useStudio().refreshSounds).toHaveBeenCalled();
    expect(useJobs().refresh).toHaveBeenCalled();
    w.unmount();
  },
);
it("keeps selected paths after a failed import, then clears them after success", async () => {
  useI18n().setLocale("en");
  useStudio().categories.value = [makeCategory({ id: "general" })];
  const run = vi
    .spyOn(ui.importer, "run")
    .mockRejectedValueOnce(new Error("Import denied"))
    .mockResolvedValue({ sounds: [makeSound({ id: "new" })] });
  vi.spyOn(ui.importer, "browse").mockResolvedValue({
    path: "media",
    parent: "",
    roots: ["media"],
    entries: [{ path: "media/a.wav", name: "a.wav", kind: "file", size: 100, supported: true }],
  });
  const w = mount(ImportPanel);
  await flushPromises();
  await w.get('input[type="checkbox"]').setValue(true);
  await w.get('[data-test="import-selected"]').trigger("click");
  await flushPromises();
  expect(w.get('[role="alert"]').text()).toBe("Import denied");
  expect(w.get('[data-test="selection-count"]').text()).toBe("1 file selected");
  await w.get('[data-test="import-selected"]').trigger("click");
  await flushPromises();
  expect(run).toHaveBeenCalledTimes(2);
  expect(w.get('[data-test="selection-count"]').text()).toBe("0 files selected");
  w.unmount();
});
