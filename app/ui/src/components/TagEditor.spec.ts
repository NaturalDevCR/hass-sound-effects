import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it } from "vitest";
import TagEditor from "@/components/TagEditor.vue";
import { useI18n } from "@/i18n";

type Props = InstanceType<typeof TagEditor>["$props"];
const mountEditor = (props: Partial<Props> = {}) =>
  mount(TagEditor, { props: { modelValue: [], ...props } as Props, attachTo: document.body });

async function type(wrapper: ReturnType<typeof mountEditor>, text: string) {
  const input = wrapper.get("input");
  await input.setValue(text);
}

beforeEach(() => {
  useI18n().setLocale("en");
  document.body.innerHTML = "";
});

describe("TagEditor", () => {
  it("renders a removable chip per tag", async () => {
    const wrapper = mountEditor({ modelValue: ["es", "bath"] });
    expect(wrapper.findAll('[data-test="tag"]').map((t) => t.text())).toEqual(["es", "bath"]);
    await wrapper.get('[aria-label="Remove tag es"]').trigger("click");
    expect(wrapper.emitted("update:modelValue")).toEqual([[["bath"]]]);
  });

  it("adds a slugified lowercase tag on Enter and clears the field", async () => {
    const wrapper = mountEditor({ modelValue: ["es"] });
    await type(wrapper, "  León Infinito ");
    await wrapper.get("input").trigger("keydown", { key: "Enter" });
    expect(wrapper.emitted("update:modelValue")).toEqual([[["es", "leon_infinito"]]]);
    expect((wrapper.get("input").element as HTMLInputElement).value).toBe("");
  });

  it("adds on a typed comma, keeping what follows as the next draft", async () => {
    const wrapper = mountEditor();
    await type(wrapper, "Bath,");
    expect(wrapper.emitted("update:modelValue")).toEqual([[["bath"]]]);
    expect((wrapper.get("input").element as HTMLInputElement).value).toBe("");
  });

  it("splits a pasted list on commas", async () => {
    const wrapper = mountEditor();
    await type(wrapper, "es, en ,Kids,pa");
    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([["es", "en", "kids"]]);
    expect((wrapper.get("input").element as HTMLInputElement).value).toBe("pa");
  });

  it("ignores empty and duplicate tags", async () => {
    const wrapper = mountEditor({ modelValue: ["es"] });
    await type(wrapper, "ES");
    await wrapper.get("input").trigger("keydown", { key: "Enter" });
    await type(wrapper, "  ");
    await wrapper.get("input").trigger("keydown", { key: "Enter" });
    await type(wrapper, "!!!");
    await wrapper.get("input").trigger("keydown", { key: "Enter" });
    expect(wrapper.emitted("update:modelValue")).toBeUndefined();
  });

  it("does not submit an enclosing form on Enter", async () => {
    const wrapper = mountEditor();
    await type(wrapper, "es");
    const event = new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true });
    wrapper.get("input").element.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
  });

  it("does not commit while an IME composition is in progress", async () => {
    const wrapper = mountEditor();
    await type(wrapper, "に");
    await wrapper.get("input").trigger("keydown", { key: "Enter", isComposing: true });
    expect(wrapper.emitted("update:modelValue")).toBeUndefined();
  });

  it("has an Add button for touch keyboards without an obvious Enter", async () => {
    const wrapper = mountEditor();
    const add = wrapper.get('[data-test="add"]');
    expect(add.attributes("disabled")).toBeDefined();
    await type(wrapper, "kids");
    expect(add.attributes("disabled")).toBeUndefined();
    await add.trigger("click");
    expect(wrapper.emitted("update:modelValue")).toEqual([[["kids"]]]);
  });

  it("commits a half-typed tag when the field loses focus", async () => {
    const wrapper = mountEditor();
    await type(wrapper, "kids");
    await wrapper.get("input").trigger("blur");
    expect(wrapper.emitted("update:modelValue")).toEqual([[["kids"]]]);
  });

  describe("suggestions", () => {
    const suggestions = ["bath", "es", "en", "kids"];

    it("offers existing tags that are not selected yet, and adds one on click", async () => {
      const wrapper = mountEditor({ modelValue: ["es"], suggestions });
      const chips = wrapper.findAll('[data-test="suggestion"]');
      expect(chips.map((c) => c.text())).toEqual(["bath", "en", "kids"]);
      await chips[2]!.trigger("click");
      expect(wrapper.emitted("update:modelValue")).toEqual([[["es", "kids"]]]);
    });

    it("narrows them as you type", async () => {
      const wrapper = mountEditor({ suggestions });
      await type(wrapper, "K");
      expect(wrapper.findAll('[data-test="suggestion"]').map((c) => c.text())).toEqual(["kids"]);
    });

    it("shows none without suggestions", () => {
      expect(mountEditor().find('[data-test="suggestions"]').exists()).toBe(false);
    });

    it("caps the list so it never takes over the screen", () => {
      const many = Array.from({ length: 40 }, (_, i) => `tag${i}`);
      expect(mountEditor({ suggestions: many }).findAll('[data-test="suggestion"]').length).toBeLessThanOrEqual(12);
    });
  });

  it("labels the field", () => {
    expect(mountEditor().get("label").text()).toBe("Tags");
    expect(mountEditor({ label: "Tags to add" }).get("label").text()).toBe("Tags to add");
  });
});
