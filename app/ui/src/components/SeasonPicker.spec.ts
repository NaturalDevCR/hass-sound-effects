import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it } from "vitest";
import SeasonPicker from "@/components/SeasonPicker.vue";
import { useStudio } from "@/composables/useStudio";
import { useI18n } from "@/i18n";
import { makeSeason } from "@/test/factories";

type Value = { seasons: string[]; all_seasons: boolean };
const mountPicker = (modelValue: Value) => mount(SeasonPicker, { props: { modelValue } });

beforeEach(() => {
  useI18n().setLocale("en");
  useStudio().seasons.value = [
    makeSeason({ id: "regular", name: "Regular" }),
    makeSeason({ id: "halloween", name: "Halloween", color: "#f97316" }),
    makeSeason({ id: "christmas", name: "Christmas", color: "#34d399" }),
  ];
});

describe("SeasonPicker", () => {
  it("lists every season as a toggle chip and reflects the selection", () => {
    const wrapper = mountPicker({ seasons: ["halloween"], all_seasons: false });
    const chips = wrapper.findAll('[data-test="season"]');
    expect(chips.map((c) => c.text())).toEqual(["Regular", "Halloween", "Christmas"]);
    expect(chips.map((c) => c.attributes("aria-pressed"))).toEqual(["false", "true", "false"]);
  });

  it("adds and removes seasons, keeping the catalog order", async () => {
    const wrapper = mountPicker({ seasons: ["christmas"], all_seasons: false });
    await wrapper.findAll('[data-test="season"]')[0]!.trigger("click"); // + regular
    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([{ seasons: ["regular", "christmas"], all_seasons: false }]);

    await wrapper.findAll('[data-test="season"]')[2]!.trigger("click"); // - christmas
    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([{ seasons: [], all_seasons: false }]);
  });

  it("has an All seasons switch that keeps the chosen seasons for when it is turned off", async () => {
    const wrapper = mountPicker({ seasons: ["halloween"], all_seasons: false });
    const toggle = wrapper.get('[role="switch"]');
    expect(toggle.text()).toContain("All seasons");
    expect(toggle.attributes("aria-checked")).toBe("false");
    await toggle.trigger("click");
    expect(wrapper.emitted("update:modelValue")).toEqual([[{ seasons: ["halloween"], all_seasons: true }]]);
  });

  it("disables the chips while All seasons is on", async () => {
    const wrapper = mountPicker({ seasons: ["halloween"], all_seasons: true });
    expect(wrapper.get('[role="switch"]').attributes("aria-checked")).toBe("true");
    const chips = wrapper.findAll('[data-test="season"]');
    for (const chip of chips) expect(chip.attributes("disabled")).toBeDefined();
    await chips[0]!.trigger("click");
    expect(wrapper.emitted("update:modelValue")).toBeUndefined();
    expect(wrapper.text()).toContain("Plays in every season");
  });

  it("names the group", () => {
    expect(mountPicker({ seasons: [], all_seasons: false }).get('[role="group"]').attributes("aria-label")).toBe("Seasons");
  });
});
