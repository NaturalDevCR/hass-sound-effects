import { mount } from "@vue/test-utils";
import { afterEach, expect, it, vi } from "vitest";
import type { AuditionTarget } from "@/api/types";
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

const validTarget: AuditionTarget = {
  id: "k", label: "Kitchen", kind: "script", entity_id: "script.kitchen", volume: null,
};
it.each([
  "script.door-chime", "script.Kitchen", "script.kitchén", "script.kitchen room",
  "script._kitchen", "script.kitchen_", "script.kitchen__room", "script.",
  "_script.kitchen", "script_.kitchen", "scr__ipt.kitchen", "light.kitchen",
  "script.kitchen.extra",
])("rejects invalid Home Assistant entity id %s with a clear explanation", async (entity_id) => {
  const w = mount(AuditionTargets, { props: { targets: [{ ...validTarget, entity_id }] } });
  await w.get("form").trigger("submit");
  expect(w.emitted("save")).toBeUndefined();
  expect(w.get('[role="alert"]').text()).toContain("lowercase letters, digits and underscores");
  expect(w.get('[role="alert"]').text()).toContain("script.");
  w.unmount();
});
it.each(["", "   "])("rejects blank target id %j", async (id) => {
  const w = mount(AuditionTargets, { props: { targets: [{ ...validTarget, id }] } });
  await w.get("form").trigger("submit");
  expect(w.emitted("save")).toBeUndefined();
  expect(w.get('[role="alert"]').text()).toContain("non-blank, unique ID");
  w.unmount();
});
it.each(["k", " k "])("rejects duplicate target ids, including surrounding whitespace (%j)", async (id) => {
  const w = mount(AuditionTargets, { props: { targets: [validTarget, { ...validTarget, id, label: "Other" }] } });
  await w.get("form").trigger("submit");
  expect(w.emitted("save")).toBeUndefined();
  expect(w.get('[role="alert"]').text()).toContain("non-blank, unique ID");
  w.unmount();
});
it.each(["", "   "])("rejects blank labels %j", async (label) => {
  const w = mount(AuditionTargets, { props: { targets: [{ ...validTarget, label }] } });
  await w.get("form").trigger("submit");
  expect(w.emitted("save")).toBeUndefined();
  expect(w.get('[role="alert"]').text()).toContain("label");
  w.unmount();
});
it.each([-0.01, 1.01, NaN, Infinity, "0.5" as unknown as number, undefined as unknown as number])(
  "rejects invalid volume %s", async (volume) => {
    const w = mount(AuditionTargets, { props: { targets: [{ ...validTarget, volume }] } });
    await w.get("form").trigger("submit");
    expect(w.emitted("save")).toBeUndefined();
    expect(w.get('[role="alert"]').text()).toContain("between 0 and 1");
    w.unmount();
  },
);
it.each([null, 0, 0.5, 1])("emits normalized targets with valid HA ids and volume %s", async (volume) => {
  const w = mount(AuditionTargets, { props: { targets: [
    { ...validTarget, id: " k ", label: " Kitchen ", entity_id: " script.door_chime_2 ", volume },
    { ...validTarget, id: "p", kind: "media_player", entity_id: "media_player.123", volume },
  ] } });
  await w.get("form").trigger("submit");
  expect(w.emitted("save")?.[0]?.[0]).toEqual([
    { ...validTarget, entity_id: "script.door_chime_2", volume },
    { ...validTarget, id: "p", kind: "media_player", entity_id: "media_player.123", volume },
  ]);
  w.unmount();
});
it("names the speaker volume slider and announces its formatted value", async () => {
  const w = mount(AuditionTargets, { props: { targets: [{ ...validTarget, volume: 0.5 }] } });
  const slider = w.get('input[type="range"]');
  expect(slider.attributes("aria-label")).toBe("Volume (0–1)");
  expect(slider.attributes("aria-valuetext")).toBe("0.50");
  await w.get('[data-test="target-volume"]').setValue("0.75");
  expect(slider.attributes("aria-valuetext")).toBe("0.75");
  w.unmount();
});
