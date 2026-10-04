import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it } from "vitest";
import ProfilePicker from "@/components/ProfilePicker.vue";
import { CATEGORY_DEFAULT } from "@/lib/profiles";
import { useStudio } from "@/composables/useStudio";
import { useI18n } from "@/i18n";
import { makeProfile } from "@/test/factories";

type Props = InstanceType<typeof ProfilePicker>["$props"];
const mountPicker = (props: Partial<Props> = {}) =>
  mount(ProfilePicker, { props: { modelValue: undefined, ...props } as Props, attachTo: document.body });

beforeEach(() => {
  useI18n().setLocale("en");
  document.body.innerHTML = "";
  useStudio().profiles.value = [
    makeProfile({ id: "standard", name: "Standard", target_lufs: -16 }),
    makeProfile({ id: "soft", name: "Soft", target_lufs: -20 }),
  ];
});

const options = (wrapper: ReturnType<typeof mountPicker>) => wrapper.findAll('input[type="radio"]');

describe("ProfilePicker", () => {
  it("exports the category-default sentinel", () => {
    expect(CATEGORY_DEFAULT).toBe("__category_default__");
  });

  it("lists the profiles with their target loudness", () => {
    const wrapper = mountPicker();
    const rows = wrapper.findAll('[data-test="option"]');
    expect(rows.map((r) => r.text())).toEqual(["Standard−16.0 LUFS", "Soft−20.0 LUFS"]);
    expect(wrapper.get('[role="radiogroup"]').attributes("aria-label")).toBe("Normalization profile");
  });

  it("emits the chosen profile id", async () => {
    const wrapper = mountPicker({ modelValue: "standard" });
    await options(wrapper)[1]!.setValue(true);
    expect(wrapper.emitted("update:modelValue")).toEqual([["soft"]]);
  });

  it("reflects the current value, and nothing when there is none yet", () => {
    expect(options(mountPicker({ modelValue: "soft" })).map((o) => (o.element as HTMLInputElement).checked)).toEqual([false, true]);
    expect(options(mountPicker({ modelValue: undefined })).every((o) => !(o.element as HTMLInputElement).checked)).toBe(true);
  });

  it("offers No normalization (null) with allowNone, listed first", async () => {
    const wrapper = mountPicker({ allowNone: true, modelValue: null });
    const rows = wrapper.findAll('[data-test="option"]');
    expect(rows[0]!.text()).toContain("No normalization");
    expect((options(wrapper)[0]!.element as HTMLInputElement).checked).toBe(true);
    await options(wrapper)[1]!.setValue(true);
    await options(wrapper)[0]!.setValue(true);
    expect(wrapper.emitted("update:modelValue")).toEqual([["standard"], [null]]);
  });

  it("offers the category default sentinel with allowCategoryDefault", async () => {
    const wrapper = mountPicker({ allowCategoryDefault: true, allowNone: true, modelValue: CATEGORY_DEFAULT });
    const rows = wrapper.findAll('[data-test="option"]');
    expect(rows[0]!.text()).toContain("Category default");
    expect(rows[1]!.text()).toContain("No normalization");
    expect((options(wrapper)[0]!.element as HTMLInputElement).checked).toBe(true);
    await options(wrapper)[2]!.setValue(true);
    await options(wrapper)[0]!.setValue(true);
    expect(wrapper.emitted("update:modelValue")).toEqual([["standard"], [CATEGORY_DEFAULT]]);
  });

  it("does not offer the extras unless asked", () => {
    const text = mountPicker().text();
    expect(text).not.toContain("No normalization");
    expect(text).not.toContain("Category default");
  });

  it("points to Organize when there are no profiles at all", () => {
    useStudio().profiles.value = [];
    expect(mountPicker().text()).toContain("No profiles yet");
  });

  it("gives every radio a 44 px row and one shared name", () => {
    const wrapper = mountPicker();
    const names = new Set(options(wrapper).map((o) => o.attributes("name")));
    expect(names.size).toBe(1);
    for (const row of wrapper.findAll('[data-test="option"]')) expect(row.classes()).toContain("min-h-11");
  });
});
