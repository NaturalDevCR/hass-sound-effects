import { mount } from "@vue/test-utils";
import { afterEach, expect, it, vi } from "vitest";
import AuditionTargets from "./AuditionTargets.vue";
import { useI18n } from "@/i18n";
import { useConfirm } from "@/composables/useConfirm";
useI18n().setLocale("en");
it.each(["media_player", "script"] as const)(
  "validates the %s prefix and emits a valid list",
  async (kind) => {
    const w = mount(AuditionTargets, { props: { targets: [] } });
    await w.get('[data-test="add-target"]').trigger("click");
    await w.get('[data-test="target-label"]').setValue("Kitchen");
    await w.get('[data-test="target-kind"]').setValue(kind);
    await w
      .get('[data-test="target-entity"]')
      .setValue(kind === "script" ? "media_player.kitchen" : "script.kitchen");
    await w.get("form").trigger("submit");
    expect(w.emitted("save")).toBeUndefined();
    expect(w.get('[role="alert"]').text()).toContain(`${kind}.`);
    await w.get('[data-test="target-entity"]').setValue(`${kind}.kitchen`);
    await w.get("form").trigger("submit");
    expect(w.emitted("save")?.[0]?.[0]).toEqual([
      expect.objectContaining({ label: "Kitchen", kind, entity_id: `${kind}.kitchen`, volume: null }),
    ]);
    w.unmount();
  },
);
it("validates volume and removes existing targets", async () => {
  const w = mount(AuditionTargets, {
    props: {
      targets: [{ id: "k", label: "Kitchen", kind: "script", entity_id: "script.kitchen", volume: 0.4 }],
    },
  });
  await w.get('[data-test="target-volume"]').setValue("2");
  await w.get("form").trigger("submit");
  expect(w.emitted("save")).toBeUndefined();
  await w.get('[data-test="remove-target"]').trigger("click");
  expect(useConfirm().request.value?.danger).toBe(true);
  useConfirm().answer(true);
  await w.vm.$nextTick();
  await w.get("form").trigger("submit");
  expect(w.emitted("save")?.[0]).toEqual([[]]);
  w.unmount();
});
it("preserves speaker drafts when another settings panel refreshes the same saved targets", async () => {
  const targets = [
    { id: "k", label: "Kitchen", kind: "script" as const, entity_id: "script.kitchen", volume: null },
  ];
  const w = mount(AuditionTargets, { props: { targets } });
  await w.get('[data-test="target-label"]').setValue("New label");
  await w.setProps({ targets: targets.map((target) => ({ ...target })) });
  expect((w.get('[data-test="target-label"]').element as HTMLInputElement).value).toBe("New label");
  w.unmount();
});

afterEach(() => vi.restoreAllMocks());
it("adds a speaker in an insecure context without randomUUID", async () => {
  vi.spyOn(crypto, "randomUUID").mockImplementation(() => {
    throw new Error("Insecure context");
  });
  const w = mount(AuditionTargets, { props: { targets: [] } });
  await w.get('[data-test="add-target"]').trigger("click");
  await w.get('[data-test="target-label"]').setValue("Kitchen");
  await w.get('[data-test="target-entity"]').setValue("media_player.kitchen");
  await w.get("form").trigger("submit");
  expect(w.emitted("save")?.[0]?.[0]).toEqual([
    expect.objectContaining({ id: expect.any(String), entity_id: "media_player.kitchen" }),
  ]);
  w.unmount();
});
