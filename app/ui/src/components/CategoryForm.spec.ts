vi.mock("@/composables/useStudio", async (original) => {
  const actual = await original<typeof import("@/composables/useStudio")>();
  const refresh = vi.fn().mockResolvedValue(undefined),
    refreshSounds = vi.fn().mockResolvedValue(undefined);
  return {
    ...actual,
    useStudio: () => ({ ...actual.useStudio(), refresh, refreshSounds }),
  };
});
import { mount, flushPromises } from "@vue/test-utils";
import { describe, it, expect, vi } from "vitest";
import CategoryForm from "./CategoryForm.vue";
import { ui } from "@/api/client";
import { makeCategory } from "@/test/factories";
it("requires a trimmed name and valid color before creating a category", async () => {
  const create = vi.spyOn(ui.categories, "create").mockResolvedValue(makeCategory({ id: "new" }));
  const w = mount(CategoryForm);
  await w.get('[data-test="name"]').setValue("   ");
  await w.get("form").trigger("submit");
  expect(create).not.toHaveBeenCalled();
  expect(w.find('[role="alert"]').exists()).toBe(true);
  await w.get('[data-test="name"]').setValue("  New  ");
  await w.get('[data-test="hex"]').setValue("#oops");
  await w.get("form").trigger("submit");
  expect(create).not.toHaveBeenCalled();
  await w.get('[data-test="hex"]').setValue("#AABBCC");
  await w.get("form").trigger("submit");
  await flushPromises();
  expect(create).toHaveBeenCalledWith(expect.objectContaining({ name: "New", color: "#aabbcc" }));
  create.mockRestore();
});
