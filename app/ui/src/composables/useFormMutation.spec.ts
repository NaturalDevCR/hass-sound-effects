import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { makeCategory } from "@/test/factories";
import { makeState } from "@/test/system";
import type { State } from "@/api/types";

const mocks = vi.hoisted(() => ({
  ui: {
    state: vi.fn(),
    categories: { list: vi.fn(), create: vi.fn() },
    seasons: { list: vi.fn() },
    profiles: { list: vi.fn() },
    sounds: { list: vi.fn() },
  },
}));

vi.mock("@/api/client", async (original) => ({
  ...(await original<typeof import("@/api/client")>()),
  ui: mocks.ui,
}));

beforeEach(() => {
  vi.resetModules();
  vi.resetAllMocks();
  vi.useFakeTimers();
  mocks.ui.state.mockResolvedValue(makeState());
  mocks.ui.categories.list.mockResolvedValue([makeCategory({ id: "general" })]);
  mocks.ui.seasons.list.mockResolvedValue([]);
  mocks.ui.profiles.list.mockResolvedValue([]);
  mocks.ui.sounds.list.mockResolvedValue([]);
});

afterEach(() => vi.useRealTimers());

it("shows the saved category even when a refresh began before the mutation", async () => {
  const { useStudio } = await import("./useStudio");
  const { useFormMutation } = await import("./useFormMutation");
  const studio = useStudio();
  await studio.refresh();

  let finishStale!: (state: State) => void;
  mocks.ui.state.mockReturnValueOnce(new Promise<State>((resolve) => { finishStale = resolve; }));
  const staleRefresh = studio.refresh();
  const created = makeCategory({ id: "doors", name: "Doors" });
  mocks.ui.categories.create.mockResolvedValue(created);
  mocks.ui.categories.list.mockResolvedValue([makeCategory({ id: "general" }), created]);

  const saved = vi.fn();
  const form = useFormMutation();
  const save = form.save(() => mocks.ui.categories.create({ name: "Doors" }), saved);
  await Promise.resolve();
  expect(saved).not.toHaveBeenCalled();
  finishStale(makeState());
  await Promise.all([staleRefresh, save]);

  expect(form.error.value).toBeNull();
  expect(form.pending.value).toBe(false);
  expect(saved).toHaveBeenCalledWith(created);
  expect(studio.categoryById("doors")).toEqual(created);
});
