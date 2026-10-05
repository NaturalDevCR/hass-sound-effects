import { mount } from "@vue/test-utils";
import { expect, it } from "vitest";
import LevelControls from "./LevelControls.vue";
import { makeSound } from "@/test/factories";
import { useI18n } from "@/i18n";

it("names every editor slider and announces formatted gain and fade values", async () => {
  useI18n().setLocale("en");
  const recipe = { ...makeSound({ id: "s" }).recipe, gain_db: 6, fade_in: 0.5, fade_out: 1.25 };
  const w = mount(LevelControls, { props: { recipe, duration: 10 } });
  const sliders = w.findAll('input[type="range"]');
  expect(sliders).toHaveLength(3);
  for (const slider of sliders) {
    const label = w.get(`label[for="${slider.attributes("id")}"]`);
    expect(label.text()).not.toBe("");
    expect(slider.attributes("aria-label")).toBe(label.get("span").text());
    expect(slider.attributes("aria-valuetext")).toBe(label.get("output").text());
  }
  expect(sliders.map((s) => s.attributes("aria-valuetext"))).toEqual(["+6.0 dB", "0.50 s", "1.25 s"]);
  await w.setProps({ recipe: { ...recipe, gain_db: -3, fade_in: 0.25 } });
  expect(sliders[0]!.attributes("aria-valuetext")).toBe("−3.0 dB");
  expect(sliders[1]!.attributes("aria-valuetext")).toBe("0.25 s");
  w.unmount();
});
