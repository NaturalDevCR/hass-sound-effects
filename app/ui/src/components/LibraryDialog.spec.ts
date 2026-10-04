import { mount } from "@vue/test-utils";
import { defineComponent, h } from "vue";
import { beforeEach, describe, expect, it } from "vitest";
import LibraryDialog, { type LibraryDialogKind } from "@/components/LibraryDialog.vue";
import { useStudio } from "@/composables/useStudio";
import { useI18n } from "@/i18n";
import { makeCategory, makeProfile, makeSeason } from "@/test/factories";

// A Sheet that always renders its slots, so what stays on screen while the real Sheet fades out
// can be asserted.
const SheetStub = defineComponent({
  props: { open: Boolean, title: String },
  render() {
    return h("div", { "data-open": String(this.open) }, [
      h("h2", this.title),
      this.$slots.default?.(),
      this.$slots.footer?.(),
    ]);
  },
});

type Props = InstanceType<typeof LibraryDialog>["$props"];
function mountDialog(props: Partial<Props> = {}) {
  return mount(LibraryDialog, {
    props: {
      kind: "tags" as LibraryDialogKind | null,
      count: 3,
      pending: false,
      error: null,
      allTags: ["kids", "es"],
      selectedTags: ["es"],
      ...props,
    } as Props,
    global: { stubs: { Sheet: SheetStub } },
  });
}

beforeEach(() => {
  useI18n().setLocale("en");
  const studio = useStudio();
  studio.categories.value = [makeCategory({ id: "doors", name: "Doors" })];
  studio.seasons.value = [makeSeason({ id: "regular", name: "Regular" })];
  studio.profiles.value = [makeProfile({ id: "standard", name: "Standard" })];
});

describe("LibraryDialog tags", () => {
  const editors = (wrapper: ReturnType<typeof mountDialog>) => wrapper.findAll("input[type='text']");

  it("includes text that was typed but not committed when Apply is pressed", async () => {
    const wrapper = mountDialog();
    const apply = wrapper.get('[data-test="apply"]');
    expect(apply.attributes("disabled")).toBeDefined();

    await editors(wrapper)[0]!.setValue("Kids Room"); // no Enter, no Add
    expect(apply.attributes("disabled")).toBeUndefined();
    await apply.trigger("click");
    expect(wrapper.emitted("submit")).toEqual([[{ kind: "tags", add: ["kids_room"], remove: [] }]]);
  });

  it("adds the draft to the chips already committed, on both lists", async () => {
    const wrapper = mountDialog();
    await editors(wrapper)[0]!.setValue("kids");
    await editors(wrapper)[0]!.trigger("keydown", { key: "Enter" });
    await editors(wrapper)[0]!.setValue("Night");
    await editors(wrapper)[1]!.setValue("es");
    await wrapper.get('[data-test="apply"]').trigger("click");
    expect(wrapper.emitted("submit")).toEqual([[{ kind: "tags", add: ["kids", "night"], remove: ["es"] }]]);
  });

  it("flags a tag that is added (even as a draft) and removed at once", async () => {
    const wrapper = mountDialog();
    await editors(wrapper)[0]!.setValue("es");
    await editors(wrapper)[1]!.setValue("es");
    expect(wrapper.text()).toContain("can't be added and removed at the same time");
    expect(wrapper.get('[data-test="apply"]').attributes("disabled")).toBeDefined();
  });

  it("explains what a pending draft will become", async () => {
    const wrapper = mountDialog();
    await editors(wrapper)[0]!.setValue("Kids Room");
    expect(wrapper.text()).toContain("Will be added as “kids_room”");
  });

  it("starts clean every time it opens", async () => {
    const wrapper = mountDialog();
    await editors(wrapper)[0]!.setValue("leftover");
    await wrapper.setProps({ kind: null });
    await wrapper.setProps({ kind: "tags" });
    expect((editors(wrapper)[0]!.element as HTMLInputElement).value).toBe("");
    expect(wrapper.get('[data-test="apply"]').attributes("disabled")).toBeDefined();
  });
});

describe("LibraryDialog while it fades out", () => {
  it("keeps its title, content and wording until it opens again", async () => {
    const wrapper = mountDialog({ kind: "level", categoryName: "Doors", defaultProfileId: "standard", count: 0 });
    expect(wrapper.get("h2").text()).toBe("Level “Doors”");
    expect(wrapper.get('[data-test="apply"]').text()).toBe("Level category");

    await wrapper.setProps({ kind: null, categoryName: undefined, defaultProfileId: undefined });
    expect(wrapper.get("div").attributes("data-open")).toBe("false");
    expect(wrapper.get("h2").text()).toBe("Level “Doors”");
    expect(wrapper.get('[data-test="apply"]').text()).toBe("Level category");
    expect(wrapper.findAll('input[type="radio"]')).toHaveLength(1);

    await wrapper.setProps({ kind: "category" });
    expect(wrapper.get("h2").text()).toBe("Move to category");
  });

  it("keeps the selection count it opened with, even if the selection changes under it", async () => {
    const wrapper = mountDialog({ kind: "seasons", count: 3 });
    expect(wrapper.text()).toContain("This changes the 3 selected sounds.");
    await wrapper.setProps({ kind: null, count: 0 });
    expect(wrapper.text()).toContain("This changes the 3 selected sounds.");
  });
});
