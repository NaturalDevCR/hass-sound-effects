import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
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
afterEach(() => {
  delete (Element.prototype as { scrollIntoView?: unknown }).scrollIntoView;
  document.body.innerHTML = "";
});

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

  describe("scrolling the active chip into view", () => {
    function spyOnScroll() {
      const scrollIntoView = vi.fn();
      Element.prototype.scrollIntoView = scrollIntoView;
      return scrollIntoView;
    }
    const names = (spy: ReturnType<typeof vi.fn>) => spy.mock.contexts.map((el) => (el as HTMLElement).textContent?.trim());

    it("does it on mount, for a category restored from the URL", async () => {
      const scrollIntoView = spyOnScroll();
      mount(CategoryChips, {
        props: { categories, modelValue: "alerts", counts: { doors: 4, alerts: 0 }, total: 4 },
        attachTo: document.body,
      });
      await nextTick();
      expect(names(scrollIntoView)).toEqual(["Alerts 0"]);
      expect(scrollIntoView).toHaveBeenCalledWith({ block: "nearest", inline: "center" });
    });

    it("does it again when the selection changes", async () => {
      const scrollIntoView = spyOnScroll();
      const wrapper = mount(CategoryChips, {
        props: { categories, modelValue: null, counts: { doors: 4, alerts: 0 }, total: 4 },
        attachTo: document.body,
      });
      await nextTick();
      await wrapper.setProps({ modelValue: "doors" });
      await nextTick();
      expect(names(scrollIntoView)).toEqual(["All 4", "Doors 4"]);
    });

    it("copes with browsers that lack scrollIntoView", async () => {
      expect(() =>
        mount(CategoryChips, { props: { categories, modelValue: "doors", counts: {}, total: 0 }, attachTo: document.body }),
      ).not.toThrow();
    });
  });
});
