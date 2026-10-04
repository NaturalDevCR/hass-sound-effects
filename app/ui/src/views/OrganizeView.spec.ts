import { mount, flushPromises } from "@vue/test-utils";
import { afterEach, beforeEach, it, expect, vi } from "vitest";
import OrganizeView from "./OrganizeView.vue";
import { ApiError, ui } from "@/api/client";
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
  useI18n().setLocale("en");
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
  useConfirm().answer(true);
  await flushPromises();
  expect(w.get('[role="alert"]').text()).toBe("Category still contains sounds");
  expect(w.find('button[aria-label="Delete regular"]').exists()).toBe(false);
});
it("reorders categories with labelled up/down controls and refreshes", async () => {
  const reorder = vi.spyOn(ui.categories, "reorder").mockResolvedValue([]);
  const w = mount(OrganizeView);
  expect(w.get('button[aria-label="Move a up"]').attributes("disabled")).toBeDefined();
  await w.get('button[aria-label="Move a down"]').trigger("click");
  await flushPromises();
  expect(reorder).toHaveBeenCalledWith(["b", "a"]);
  expect(useStudio().refresh).toHaveBeenCalled();
});
it("supports keyboard tab navigation", async () => {
  const w = mount(OrganizeView);
  await w.get('[role="tablist"]').trigger("keydown", { key: "ArrowRight" });
  expect(w.get("#organize-tab-seasons").attributes("aria-selected")).toBe("true");
  await w.get('[role="tablist"]').trigger("keydown", { key: "End" });
  expect(w.get("#organize-tab-profiles").attributes("tabindex")).toBe("0");
});
