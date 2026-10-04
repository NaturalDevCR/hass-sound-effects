vi.mock("@/composables/useJobs", () => {
  const refresh = vi.fn().mockResolvedValue(undefined);
  return { useJobs: () => ({ refresh }) };
});
vi.mock("@/composables/useStudio", async (original) => {
  const actual = await original<typeof import("@/composables/useStudio")>();
  const refresh = vi.fn().mockResolvedValue(undefined),
    refreshSounds = vi.fn().mockResolvedValue(undefined);
  return {
    ...actual,
    useStudio: () => ({ ...actual.useStudio(), refresh, refreshSounds }),
  };
});
import { mount, flushPromises } from "@vue/test-utils";
import { it, expect, vi } from "vitest";
import ProfileForm from "./ProfileForm.vue";
import { useConfirm } from "@/composables/useConfirm";
import { ui } from "@/api/client";
import { makeProfile } from "@/test/factories";
it.each([true, false])("confirms re-render after PATCH (answer %s)", async (answer) => {
  const profile = makeProfile({ id: "soft" });
  const update = vi.spyOn(ui.profiles, "update").mockResolvedValue({ profile, affected_sound_ids: ["a", "b"] });
  const apply = vi.spyOn(ui.profiles, "apply").mockResolvedValue({ queued: 2 });
  const w = mount(ProfileForm, { props: { profile } });
  await w.get("form").trigger("submit");
  await flushPromises();
  expect(update).toHaveBeenCalledWith("soft", expect.objectContaining({ target_lufs: -16 }));
  expect(useConfirm().request.value?.title).toContain("2");
  expect(apply).not.toHaveBeenCalled();
  useConfirm().answer(answer);
  await flushPromises();
  if (answer) expect(apply).toHaveBeenCalledWith("soft", { sound_ids: ["a", "b"] });
  else expect(apply).not.toHaveBeenCalled();
  expect(w.emitted("saved")).toHaveLength(1);
  update.mockRestore();
  apply.mockRestore();
});
it("rejects blank names and out-of-range loudness", async () => {
  const create = vi.spyOn(ui.profiles, "create");
  const w = mount(ProfileForm);
  await w.get("form").trigger("submit");
  expect(create).not.toHaveBeenCalled();
  await w.get('[data-test="name"]').setValue("Test");
  await w.get('[data-test="target_lufs"]').setValue("-31");
  await w.get("form").trigger("submit");
  expect(create).not.toHaveBeenCalled();
  create.mockRestore();
});
it("shows apply failure inline and retries without PATCHing the saved profile again", async () => {
  const profile = makeProfile({ id: "soft" });
  const update = vi.spyOn(ui.profiles, "update").mockResolvedValue({ profile, affected_sound_ids: ["a"] });
  const apply = vi
    .spyOn(ui.profiles, "apply")
    .mockRejectedValueOnce(new Error("render unavailable"))
    .mockResolvedValue({ queued: 1 });
  const w = mount(ProfileForm, { props: { profile } });
  await w.get("form").trigger("submit");
  await flushPromises();
  useConfirm().answer(true);
  await flushPromises();
  expect(w.get('[role="alert"]').text()).toBe("render unavailable");
  expect(w.emitted("saved")).toBeUndefined();
  await w.get("form").trigger("submit");
  await flushPromises();
  useConfirm().answer(true);
  await flushPromises();
  expect(update).toHaveBeenCalledTimes(1);
  expect(apply).toHaveBeenCalledTimes(2);
  expect(w.emitted("saved")).toHaveLength(1);
  update.mockRestore();
  apply.mockRestore();
});
