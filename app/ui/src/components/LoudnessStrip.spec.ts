import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it } from "vitest";
import LoudnessStrip from "@/components/LoudnessStrip.vue";
import { useI18n } from "@/i18n";
import { makeSound } from "@/test/factories";

const withLufs = (id: string, lufs: number | null) => {
  const sound = makeSound({ id, title: `Sound ${id}` });
  if (sound.published) sound.published.loudness_lufs = lufs;
  return sound;
};

const mountStrip = (sounds = [withLufs("a", -22), withLufs("b", -16), withLufs("c", -12)]) =>
  mount(LoudnessStrip, { props: { sounds, categoryName: "Doors" } });

beforeEach(() => useI18n().setLocale("en"));

describe("LoudnessStrip", () => {
  it("renders nothing until two sounds have a measured loudness", () => {
    expect(mountStrip([withLufs("a", -16)]).find('[data-test="strip"]').exists()).toBe(false);
    expect(mountStrip([withLufs("a", -16), withLufs("b", null)]).find('[data-test="strip"]').exists()).toBe(false);
    expect(mountStrip([]).find('[data-test="strip"]').exists()).toBe(false);
    expect(mountStrip([withLufs("a", -16), makeSound({ id: "b", published: null })]).find('[data-test="strip"]').exists()).toBe(false);
  });

  it("shows the min and max loudness and the spread", () => {
    const wrapper = mountStrip();
    expect(wrapper.get('[data-test="min"]').text()).toBe("−22.0 LUFS");
    expect(wrapper.get('[data-test="max"]').text()).toBe("−12.0 LUFS");
    expect(wrapper.get('[data-test="spread"]').text()).toBe("Spread 10.0 LU");
  });

  it("draws one tick per measured sound at its position between min and max", () => {
    const wrapper = mountStrip([withLufs("a", -22), withLufs("b", -16), withLufs("c", -12), withLufs("d", null)]);
    const ticks = wrapper.findAll('[data-test="tick"]');
    expect(ticks).toHaveLength(3);
    expect(ticks.map((t) => t.attributes("style"))).toEqual([
      expect.stringContaining("left: 0%"),
      expect.stringContaining("left: 60%"),
      expect.stringContaining("left: 100%"),
    ]);
    expect(ticks[1]!.attributes("title")).toBe("Sound b: −16.0 LUFS");
  });

  it("centres the ticks when every sound has the same loudness", () => {
    const wrapper = mountStrip([withLufs("a", -16), withLufs("b", -16)]);
    for (const tick of wrapper.findAll('[data-test="tick"]')) expect(tick.attributes("style")).toContain("left: 50%");
    expect(wrapper.get('[data-test="spread"]').text()).toBe("Spread 0.0 LU");
    expect(wrapper.text()).toContain("Well balanced");
  });

  it("flags an uneven category", () => {
    expect(mountStrip().text()).toContain("Uneven: leveling recommended");
  });

  it("summarises the strip for screen readers", () => {
    const strip = mountStrip().get('[role="img"]');
    expect(strip.attributes("aria-label")).toBe("Loudness of 3 sounds in Doors: −22.0 LUFS to −12.0 LUFS, spread 10.0 LU");
  });

  it("emits level from the button", async () => {
    const wrapper = mountStrip();
    const button = wrapper.get('[data-test="level"]');
    expect(button.text()).toBe("Level this category");
    await button.trigger("click");
    expect(wrapper.emitted("level")).toHaveLength(1);
  });

  it("can disable the button while a request runs", () => {
    const wrapper = mount(LoudnessStrip, { props: { sounds: [withLufs("a", -22), withLufs("b", -12)], categoryName: "Doors", busy: true } });
    expect(wrapper.get('[data-test="level"]').attributes("disabled")).toBeDefined();
  });
});
