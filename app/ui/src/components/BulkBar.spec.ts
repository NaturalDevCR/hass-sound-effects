import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it } from "vitest";
import BulkBar from "@/components/BulkBar.vue";
import { useI18n } from "@/i18n";

const ACTIONS = ["category", "seasons", "tags", "normalize", "enable", "disable", "delete"] as const;

type Props = InstanceType<typeof BulkBar>["$props"];
const mountBar = (props: Partial<Props> = {}) =>
  mount(BulkBar, { props: { count: 0, total: 12, ...props } as Props });

beforeEach(() => useI18n().setLocale("en"));

describe("BulkBar", () => {
  it("is a labelled toolbar with the selection count", () => {
    const wrapper = mountBar({ count: 3 });
    expect(wrapper.get('[role="toolbar"]').attributes("aria-label")).toBe("Bulk actions");
    expect(wrapper.get('[data-test="count"]').text()).toBe("3 selected");
  });

  it("disables every action while nothing is selected", async () => {
    const wrapper = mountBar({ count: 0 });
    for (const name of ACTIONS) {
      const button = wrapper.get(`[data-test="action-${name}"]`);
      expect(button.attributes("disabled"), name).toBeDefined();
      await button.trigger("click");
    }
    expect(wrapper.emitted("action")).toBeUndefined();
  });

  it("emits each action by name once something is selected", async () => {
    const wrapper = mountBar({ count: 2 });
    for (const name of ACTIONS) await wrapper.get(`[data-test="action-${name}"]`).trigger("click");
    expect(wrapper.emitted("action")).toEqual(ACTIONS.map((name) => [name]));
  });

  it("labels the actions", () => {
    const wrapper = mountBar({ count: 1 });
    expect(ACTIONS.map((n) => wrapper.get(`[data-test="action-${n}"]`).text())).toEqual([
      "Category",
      "Seasons",
      "Tags",
      "Normalize",
      "Enable",
      "Disable",
      "Delete",
    ]);
  });

  it("offers Select all (filtered) with the filtered total, even with an empty selection", async () => {
    const wrapper = mountBar({ count: 0, total: 12 });
    const button = wrapper.get('[data-test="select-all"]');
    expect(button.text()).toBe("Select all (12)");
    expect(button.attributes("disabled")).toBeUndefined();
    await button.trigger("click");
    expect(wrapper.emitted("select-all")).toHaveLength(1);
  });

  it("disables Select all once everything filtered is selected, or when nothing is listed", () => {
    expect(mountBar({ count: 12, total: 12 }).get('[data-test="select-all"]').attributes("disabled")).toBeDefined();
    expect(mountBar({ count: 0, total: 0 }).get('[data-test="select-all"]').attributes("disabled")).toBeDefined();
  });

  it("emits done from the close button", async () => {
    const wrapper = mountBar({ count: 1 });
    const done = wrapper.get('[data-test="done"]');
    expect(done.attributes("aria-label")).toBe("Done selecting");
    await done.trigger("click");
    expect(wrapper.emitted("done")).toHaveLength(1);
  });

  it("locks the actions and reports busy while a request is running", async () => {
    const wrapper = mountBar({ count: 2, busy: true });
    expect(wrapper.get('[role="toolbar"]').attributes("aria-busy")).toBe("true");
    for (const name of ACTIONS) expect(wrapper.get(`[data-test="action-${name}"]`).attributes("disabled")).toBeDefined();
    await wrapper.get('[data-test="action-enable"]').trigger("click");
    expect(wrapper.emitted("action")).toBeUndefined();
  });

  it("shows an inline error", () => {
    const wrapper = mountBar({ count: 2, error: "Database is locked" });
    expect(wrapper.get('[role="alert"]').text()).toContain("Database is locked");
    expect(mountBar({ count: 2 }).find('[role="alert"]').exists()).toBe(false);
  });

  it("shows a polite note, e.g. when filters deselected sounds", () => {
    const wrapper = mountBar({ count: 1, note: "1 selected sound is hidden by the filters and was deselected." });
    const note = wrapper.get('[data-test="note"]');
    expect(note.attributes("role")).toBe("status");
    expect(note.text()).toBe("1 selected sound is hidden by the filters and was deselected.");
    expect(mountBar({ count: 1 }).find('[data-test="note"]').exists()).toBe(false);
  });

  it("localizes", () => {
    useI18n().setLocale("es");
    const wrapper = mountBar({ count: 3, total: 9 });
    expect(wrapper.get('[data-test="count"]').text()).toBe("3 seleccionados");
    expect(wrapper.get('[data-test="select-all"]').text()).toBe("Seleccionar todos (9)");
  });
});
