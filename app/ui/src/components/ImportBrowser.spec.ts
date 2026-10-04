import { mount, flushPromises } from "@vue/test-utils";
import { beforeEach, afterEach, expect, it, vi } from "vitest";
import ImportBrowser from "./ImportBrowser.vue";
import { ui } from "@/api/client";
import { useI18n } from "@/i18n";
vi.mock("@/api/client", async (original) => ({
  ...(await original<typeof import("@/api/client")>()),
  ui: { importer: { browse: vi.fn() } },
}));
let w: ReturnType<typeof mount>;
beforeEach(() => {
  useI18n().setLocale("en");
  vi.clearAllMocks();
  vi.mocked(ui.importer.browse).mockImplementation(async (path) => ({
    path,
    parent: path ? "" : null,
    roots: ["config/www", "media", "share"],
    entries: path
      ? [
          { name: "a.wav", path: `${path}/a.wav`, kind: "file", size: 1024, supported: true },
          { name: "bad.txt", path: `${path}/bad.txt`, kind: "file", size: 100, supported: false },
          { name: "folder", path: `${path}/folder`, kind: "dir", size: 0, supported: false },
        ]
      : [],
  }));
});
afterEach(() => w?.unmount());
async function open() {
  w = mount(ImportBrowser);
  await flushPromises();
}
it("navigates roots, folders, parent and breadcrumbs with folders first", async () => {
  await open();
  await w.get('[data-path="media"]').trigger("click");
  await flushPromises();
  expect(ui.importer.browse).toHaveBeenLastCalledWith("media");
  expect(w.findAll('[data-test="entry"]')[0]!.text()).toContain("folder");
  await w.get('[data-path="media/folder"]').trigger("click");
  await flushPromises();
  expect(ui.importer.browse).toHaveBeenLastCalledWith("media/folder");
  await w.get('[data-test="parent"]').trigger("click");
  await flushPromises();
  expect(ui.importer.browse).toHaveBeenLastCalledWith("");
});
it("selects only supported files, retains selection across folders and emits selected paths", async () => {
  await open();
  await w.get('[data-path="media"]').trigger("click");
  await flushPromises();
  expect(w.findAll('input[type="checkbox"]')).toHaveLength(1);
  await w.get('[data-test="select-supported"]').trigger("click");
  await w.get('[data-path="share"]').trigger("click");
  await flushPromises();
  await w.get('input[type="checkbox"]').setValue(true);
  expect(w.get('[data-test="selection-count"]').text()).toContain("2");
  await w.get('[data-test="import-selected"]').trigger("click");
  expect(w.emitted("import")?.[0]).toEqual([["media/a.wav", "share/a.wav"]]);
});
it("shows browse failure inline and retries", async () => {
  vi.mocked(ui.importer.browse).mockRejectedValueOnce(new Error("No access"));
  await open();
  expect(w.get('[role="alert"]').text()).toBe("No access");
  await w.get('[data-test="browse-retry"]').trigger("click");
  await flushPromises();
  expect(w.find('[role="alert"]').exists()).toBe(false);
});
