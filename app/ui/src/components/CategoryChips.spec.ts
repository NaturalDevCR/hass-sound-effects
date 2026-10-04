import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it } from "vitest";
import CategoryChips from "@/components/CategoryChips.vue";
import { useI18n } from "@/i18n";
import { makeCategory } from "@/test/factories";

const categories = [
  makeCategory({ id: "doors", name: "Doors", color: "#f97316", icon: "mdi:door-open" }),
  makeCategory({ id: "alerts", name: "Alerts", color: "#f87171", icon: "mdi:bell" }),
];

function mountChips(modelValue: string | null = null) {
  return mount(CategoryChips, {
    props: { categories, modelValue, counts: { doors: 4, alerts: 0 }, total: 4 },
  });
}

beforeEach(() => useI18n().setLocale("en"));

describe("CategoryChips", () => {
  it("renders All plus one chip per category, each with its count", () => {
    const chips = mountChips().findAll("button");
    expect(chips.map((c) => c.text())).toEqual(["All 4", "Doors 4", "Alerts 0"]);
  });

  it("shows the category color dot and icon", () => {
    const doors = mountChips().findAll("button")[1]!;
    expect(doors.get('[data-test="dot"]').attributes("style")).toContain("#f97316");
    expect(doors.find("svg").exists()).toBe(true);
  });

  it("emits update:modelValue with the category id, or null for All", async () => {
    const wrapper = mountChips("doors");
    const [all, , alerts] = wrapper.findAll("button");
    await alerts!.trigger("click");
    await all!.trigger("click");
    expect(wrapper.emitted("update:modelValue")).toEqual([["alerts"], [null]]);
  });

  it("marks the active chip with chip-active and aria-pressed", () => {
    const [all, doors, alerts] = mountChips("doors").findAll("button");
    expect(doors!.classes()).toContain("chip-active");
    expect(doors!.attributes("aria-pressed")).toBe("true");
    for (const idle of [all!, alerts!]) {
      expect(idle.classes()).toContain("chip");
      expect(idle.classes()).not.toContain("chip-active");
      expect(idle.attributes("aria-pressed")).toBe("false");
    }
    expect(mountChips(null).findAll("button")[0]!.classes()).toContain("chip-active");
  });

  it("scrolls horizontally with snapping on phones and is a labelled group", () => {
    const group = mountChips().get('[role="group"]');
    expect(group.attributes("aria-label")).toBe("Categories");
    expect(group.classes()).toEqual(expect.arrayContaining(["overflow-x-auto", "snap-x"]));
  });

  it("treats a missing count as zero", () => {
    const wrapper = mount(CategoryChips, { props: { categories, modelValue: null, counts: {}, total: 0 } });
    expect(wrapper.findAll("button").map((c) => c.text())).toEqual(["All 0", "Doors 0", "Alerts 0"]);
  });
});
