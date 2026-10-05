import { mount, flushPromises } from "@vue/test-utils";
import { afterEach, beforeEach, it, expect, vi } from "vitest";
import OrganizeView from "./OrganizeView.vue";
import { ApiError, ui } from "@/api/client";
import { useToast } from "@/composables/useToast";
import { useConfirm } from "@/composables/useConfirm";
import { useStudio } from "@/composables/useStudio";
import { useI18n } from "@/i18n";
import { makeCategory, makeSeason } from "@/test/factories";
vi.mock("@/composables/useStudio", async (original) => {
  const actual = await original<typeof import("@/composables/useStudio")>();
  const refresh = vi.fn().mockResolvedValue(undefined);
  return { ...actual, useStudio: () => ({ ...actual.useStudio(), refresh }) };
});
beforeEach(() => {
  vi.mocked(useStudio().refresh).mockReset().mockResolvedValue(undefined);
  useI18n().setLocale("en");
  useToast().toasts.value = [];
  useStudio().loaded.value = true;
  useStudio().categories.value = [makeCategory({ id: "a" }), makeCategory({ id: "b" })];
  useStudio().seasons.value = [makeSeason({ id: "regular", builtin: true })];
  useStudio().profiles.value = [];
});
afterEach(() => {
  useConfirm().answer(false);
  vi.restoreAllMocks();
});
it("confirms deletion and displays the server's 409 detail", async () => {
  const remove = vi
    .spyOn(ui.categories, "remove")
    .mockRejectedValue(new ApiError(409, "Category still contains sounds"));
  const w = mount(OrganizeView);
  await w.get('button[aria-label="Delete a"]').trigger("click");
  expect(useConfirm().request.value?.danger).toBe(true);
  expect(remove).not.toHaveBeenCalled();
  expect(w.find('[role="status"]').exists()).toBe(false);
  expect(w.get('button[aria-label="Delete a"]').attributes("disabled")).toBeUndefined();
  useConfirm().answer(true);
  await flushPromises();
  expect(w.get('[data-test="organize-error"]').text()).toBe("Category still contains sounds");
  expect(w.find('[role="alert"]').exists()).toBe(false);
  expect(w.get('[data-test="organize-error"]').attributes("aria-live")).toBeUndefined();
  expect(useToast().toasts.value.at(-1)).toMatchObject({ kind: "error", message: "Category still contains sounds" });
  expect(w.find('button[aria-label="Delete regular"]').exists()).toBe(false);
});
it("reorders categories with labelled up/down controls and refreshes", async () => {
  const reorder = vi.spyOn(ui.categories, "reorder").mockResolvedValue([]);
  const w = mount(OrganizeView);
  expect(w.get('button[aria-label="Move a up"]').attributes("disabled")).toBeDefined();
  await w.get('button[aria-label="Move a down"]').trigger("click");
  await flushPromises();
  expect(reorder).toHaveBeenCalledWith(["b", "a"]);
  expect(w.get('[aria-live="polite"][aria-atomic="true"]').text()).toBe("a moved to position 2 of 2");
  expect(useStudio().refresh).toHaveBeenCalled();
});
it("supports keyboard tab navigation", async () => {
  const w = mount(OrganizeView);
  await w.get('[role="tablist"]').trigger("keydown", { key: "ArrowRight" });
  expect(w.get("#organize-tab-seasons").attributes("aria-selected")).toBe("true");
  await w.get('[role="tablist"]').trigger("keydown", { key: "End" });
  expect(w.get("#organize-tab-profiles").attributes("tabindex")).toBe("0");
});

it("shows reorder failures inline and as an error toast with a row spinner", async () => {
  let reject!: (cause: Error) => void;
  vi.spyOn(ui.categories, "reorder").mockImplementation(() => new Promise((_, fail) => { reject = fail; }));
  const w = mount(OrganizeView);
  await w.get('button[aria-label="Move a down"]').trigger("click");
  expect(w.get('[role="status"]').element.closest("li")?.textContent).toContain("a");
  reject(new Error("Reorder unavailable"));
  await flushPromises();
  expect(w.get('[data-test="organize-error"]').text()).toBe("Reorder unavailable");
  expect(w.find('[role="alert"]').exists()).toBe(false);
  expect(w.get('[data-test="organize-error"]').attributes("aria-live")).toBeUndefined();
  expect(useToast().toasts.value.at(-1)).toMatchObject({ kind: "error", message: "Reorder unavailable" });
  expect(w.find('[role="status"]').exists()).toBe(false);
});

it.each([
  { index: 0, delta: 1, expected: "down" },
  { index: 2, delta: -1, expected: "up" },
  { index: 1, delta: -1, expected: "down" },
  { index: 1, delta: 1, expected: "up" },
])("restores focus to the moved row after refresh: %s", async ({ index, delta, expected }) => {
  useStudio().categories.value = ["a", "b", "c"].map((id) => makeCategory({ id }));
  const moved = useStudio().categories.value[index]!;
  let reordered: string[] = [];
  vi.spyOn(ui.categories, "reorder").mockImplementation(async (ids) => { reordered = ids; return []; });
  vi.mocked(useStudio().refresh).mockImplementationOnce(async () => {
    const byId = new Map(useStudio().categories.value.map((category) => [category.id, category]));
    useStudio().categories.value = reordered.map((id) => byId.get(id)!);
  });
  const w = mount(OrganizeView, { attachTo: document.body });
  try {
    const button = w.get(`button[aria-label="Move ${moved.name} ${delta === 1 ? "down" : "up"}"]`);
    (button.element as HTMLButtonElement).focus();
    await button.trigger("click");
    await flushPromises();
    const target = w.get(`button[aria-label="Move ${moved.name} ${expected}"]`);
    expect(target.attributes("disabled")).toBeUndefined();
    expect(document.activeElement).toBe(target.element);
  } finally {
    w.unmount();
  }
});
