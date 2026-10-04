import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { defineComponent, h } from "vue";
import { createMemoryHistory, RouterView, type Router } from "vue-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/api/client";
import { useConfirm } from "@/composables/useConfirm";
import { useStudio } from "@/composables/useStudio";
import { useToast } from "@/composables/useToast";
import { useI18n } from "@/i18n";
import { createAppRouter } from "@/router";
import { makeCategory, makeProfile, makeSeason, makeSound } from "@/test/factories";

const mocks = vi.hoisted(() => ({
  ui: {
    state: vi.fn(),
    categories: { list: vi.fn() },
    seasons: { list: vi.fn() },
    profiles: { list: vi.fn(), apply: vi.fn() },
    sounds: { list: vi.fn(), bulk: vi.fn(), bulkDelete: vi.fn() },
    jobs: vi.fn(),
  },
  player: { toggle: vi.fn(), stop: vi.fn() },
}));
vi.mock("@/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/client")>()),
  ui: mocks.ui,
}));
vi.mock("@/composables/usePlayer", async () => {
  const { ref } = await import("vue");
  const currentId = ref<string | null>(null);
  const playing = ref(false);
  return { usePlayer: () => ({ currentId, playing, toggle: mocks.player.toggle, stop: mocks.player.stop }) };
});

import { usePlayer } from "@/composables/usePlayer";

const categories = [
  makeCategory({ id: "doors", name: "Doors", sort_order: 0, default_profile_id: "standard" }),
  makeCategory({ id: "alerts", name: "Alerts", sort_order: 1 }),
];
const seasons = [
  makeSeason({ id: "regular", name: "Regular", builtin: true }),
  makeSeason({ id: "halloween", name: "Halloween", color: "#f97316" }),
];
const profiles = [
  makeProfile({ id: "standard", name: "Standard", target_lufs: -16 }),
  makeProfile({ id: "soft", name: "Soft", target_lufs: -20 }),
];

const withLufs = (sound: ReturnType<typeof makeSound>, lufs: number) => {
  if (sound.published) sound.published.loudness_lufs = lufs;
  return sound;
};

const library = () => [
  withLufs(makeSound({ id: "s3", title: "Zebra crossing", category_id: "alerts", tags: ["kids"] }), -12),
  withLufs(makeSound({ id: "s1", title: "Bell", category_id: "doors", tags: ["es", "bath"] }), -22),
  withLufs(makeSound({ id: "s2", title: "Léon's knock", category_id: "doors", seasons: ["halloween"] }), -16),
  makeSound({
    id: "s4",
    title: "Muted chime",
    category_id: "alerts",
    enabled: false,
    status: "failed",
    error: "boom",
    published: null,
  }),
];

let mounted: VueWrapper | null = null;

async function mountLibrary(path = "/") {
  const router: Router = createAppRouter(createMemoryHistory());
  await router.push(path);
  await router.isReady();
  const Root = defineComponent({ render: () => h(RouterView) });
  mounted = mount(Root, { attachTo: document.body, global: { plugins: [router], stubs: { teleport: true } } });
  await flushPromises();
  return { wrapper: mounted, router };
}

const titles = (wrapper: VueWrapper) => wrapper.findAll('[data-test="title"]').map((t) => t.text());
const query = (router: Router) => router.currentRoute.value.query;
const toasts = () => useToast().toasts.value.map((t) => t.message);

async function enterSelection(wrapper: VueWrapper, ...titlesToPick: string[]) {
  await wrapper.get('[data-test="select-toggle"]').trigger("click");
  for (const title of titlesToPick) {
    const row = wrapper.findAll("li").find((li) => li.get('[data-test="title"]').text() === title)!;
    await row.get('[data-test="select"]').trigger("click");
  }
}

beforeEach(() => {
  useI18n().setLocale("en");
  vi.resetAllMocks();
  const studio = useStudio();
  studio.categories.value = categories;
  studio.seasons.value = seasons;
  studio.profiles.value = profiles;
  studio.sounds.value = library();
  studio.loaded.value = true;
  studio.loading.value = false;
  studio.error.value = null;
  useToast().toasts.value = [];
  const player = usePlayer();
  player.currentId.value = null;
  player.playing.value = false;

  mocks.ui.state.mockResolvedValue({});
  mocks.ui.categories.list.mockResolvedValue(categories);
  mocks.ui.seasons.list.mockResolvedValue(seasons);
  mocks.ui.profiles.list.mockResolvedValue(profiles);
  mocks.ui.sounds.list.mockImplementation(async () => library());
  mocks.ui.sounds.bulk.mockResolvedValue({ updated: 2, queued: 0 });
  mocks.ui.sounds.bulkDelete.mockResolvedValue({ deleted: 2 });
  mocks.ui.profiles.apply.mockResolvedValue({ queued: 2 });
  mocks.ui.jobs.mockResolvedValue([]);
});
afterEach(() => {
  mounted?.unmount();
  mounted = null;
  vi.useRealTimers();
  document.body.innerHTML = "";
});

describe("loading and empty states", () => {
  it("shows skeleton rows, not the empty state, until the first load finishes", async () => {
    const studio = useStudio();
    studio.loaded.value = false;
    studio.loading.value = true;
    studio.sounds.value = [];
    const { wrapper } = await mountLibrary();
    expect(wrapper.find('[data-test="skeleton"]').exists()).toBe(true);
    expect(wrapper.find('[data-test="empty"]').exists()).toBe(false);
    expect(wrapper.get('[role="status"]').text()).toBe("Loading…");

    studio.sounds.value = library();
    studio.loaded.value = true;
    studio.loading.value = false;
    await flushPromises();
    expect(wrapper.find('[data-test="skeleton"]').exists()).toBe(false);
    expect(titles(wrapper)).toHaveLength(4);
  });

  it("offers a retry when the first load failed", async () => {
    const studio = useStudio();
    studio.loaded.value = false;
    studio.loading.value = false;
    studio.sounds.value = [];
    const { wrapper } = await mountLibrary();
    expect(wrapper.get('[data-test="load-failed"]').text()).toContain("Your library couldn't be loaded");
    await wrapper.get('[data-test="load-failed"] button').trigger("click");
    expect(mocks.ui.state).toHaveBeenCalled();
  });

  it("guides an empty library to uploading or importing", async () => {
    useStudio().sounds.value = [];
    const { wrapper } = await mountLibrary();
    const empty = wrapper.get('[data-test="empty"]');
    expect(empty.get('a[href="/upload"]').text()).toBe("Upload your first sound");
    expect(empty.get('a[href="/system#import"]').text()).toBe("Import existing files");
    expect(wrapper.find('[data-test="search"]').exists()).toBe(false);
  });

  it("keeps rendering the child route outlet and the library landmark", async () => {
    const { wrapper, router } = await mountLibrary();
    expect(wrapper.find('[data-test="library"]').exists()).toBe(true);
    await router.push("/sounds/s1");
    await flushPromises();
    expect(document.querySelector('[role="dialog"]')).not.toBeNull();
    expect(wrapper.find('[data-test="library"]').exists()).toBe(true);
  });
});

describe("listing", () => {
  it("lists every sound alphabetically (accents and numbers aside)", async () => {
    const { wrapper } = await mountLibrary();
    expect(titles(wrapper)).toEqual(["Bell", "Léon's knock", "Muted chime", "Zebra crossing"]);
    expect(wrapper.get('[data-test="result-count"]').text()).toBe("4 sounds");
  });

  it("names each sound's category while no category is selected", async () => {
    const { wrapper } = await mountLibrary();
    expect(wrapper.findAll('[data-test="meta"]')[0]!.text()).toContain("Doors");
  });

  it("resolves season badges", async () => {
    const { wrapper } = await mountLibrary();
    const row = wrapper.findAll("li").find((li) => li.text().includes("Léon"))!;
    expect(row.get('[data-test="chips"]').text()).toContain("Halloween");
  });

  it("shows category chips with counts that follow the other filters", async () => {
    const { wrapper } = await mountLibrary("/?q=bell");
    const chips = wrapper.findAll('[role="group"] button').map((b) => b.text());
    expect(chips).toEqual(["All 1", "Doors 1", "Alerts 0"]);
  });
});

describe("filters in the route query", () => {
  it("applies a category chip and writes ?c=", async () => {
    const { wrapper, router } = await mountLibrary();
    await wrapper.findAll('[role="group"] button')[1]!.trigger("click");
    await flushPromises();
    expect(query(router)).toEqual({ c: "doors" });
    expect(titles(wrapper)).toEqual(["Bell", "Léon's knock"]);
    // category label is redundant once a category is selected
    expect(wrapper.findAll('[data-test="meta"]')[0]!.text()).not.toContain("Doors");
  });

  it("debounces the search by 150 ms and ignores accents", async () => {
    const { wrapper, router } = await mountLibrary();
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    await wrapper.get('[data-test="search"]').setValue("leon");
    vi.advanceTimersByTime(149);
    await flushPromises();
    expect(query(router).q).toBeUndefined();
    expect(titles(wrapper)).toHaveLength(4);

    vi.advanceTimersByTime(1);
    await flushPromises();
    expect(query(router)).toEqual({ q: "leon" });
    expect(titles(wrapper)).toEqual(["Léon's knock"]);
  });

  it("does not let a route update overwrite what is still being typed", async () => {
    const { wrapper } = await mountLibrary();
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    const input = wrapper.get('[data-test="search"]');
    await input.setValue("be");
    vi.advanceTimersByTime(150);
    await input.setValue("bell"); // typed again before the route update landed
    await flushPromises();
    expect((input.element as HTMLInputElement).value).toBe("bell");
    vi.advanceTimersByTime(150);
    await flushPromises();
    expect(titles(wrapper)).toEqual(["Bell"]);
  });

  it("filters by season, tag and status through selects", async () => {
    const { wrapper, router } = await mountLibrary();
    await wrapper.get('[data-test="filter-season"]').setValue("halloween");
    await flushPromises();
    expect(query(router)).toEqual({ s: "halloween" });
    // sounds that play in all seasons are not excluded, so Bell/Zebra (regular only) are
    expect(titles(wrapper)).toEqual(["Léon's knock"]);

    await wrapper.get('[data-test="filter-season"]').setValue("");
    await wrapper.get('[data-test="filter-tag"]').setValue("kids");
    await flushPromises();
    expect(query(router)).toEqual({ t: "kids" });
    expect(titles(wrapper)).toEqual(["Zebra crossing"]);

    await wrapper.get('[data-test="filter-tag"]').setValue("");
    await wrapper.get('[data-test="filter-status"]').setValue("failed");
    await flushPromises();
    expect(query(router)).toEqual({ st: "failed" });
    expect(titles(wrapper)).toEqual(["Muted chime"]);
  });

  it("offers the tags of all sounds, sorted", async () => {
    const { wrapper } = await mountLibrary();
    const options = wrapper.get('[data-test="filter-tag"]').findAll("option").map((o) => o.text());
    expect(options).toEqual(["All tags", "bath", "es", "kids"]);
  });

  it("restores the filters from the URL", async () => {
    const { wrapper } = await mountLibrary("/?c=doors&q=bell&t=es&s=regular&st=ready");
    expect((wrapper.get('[data-test="search"]').element as HTMLInputElement).value).toBe("bell");
    expect((wrapper.get('[data-test="filter-tag"]').element as HTMLSelectElement).value).toBe("es");
    expect(titles(wrapper)).toEqual(["Bell"]);
    expect(wrapper.get('[data-test="result-count"]').text()).toBe("1 of 4 sounds");
  });

  it("ignores URL values that match nothing known instead of hiding everything", async () => {
    const { wrapper } = await mountLibrary("/?c=ghost&st=nonsense&s=ghost&t=ghost");
    expect(titles(wrapper)).toHaveLength(4);
    expect(wrapper.get('[data-test="clear-filters"]').attributes("disabled")).toBeDefined();
  });

  it("tucks the season, tag and status selects behind a Filters button on phones", async () => {
    const { wrapper } = await mountLibrary();
    const toggle = wrapper.get('[data-test="filters-toggle"]');
    const panel = wrapper.get("#library-filters");
    expect(toggle.attributes("aria-expanded")).toBe("false");
    expect(toggle.attributes("aria-controls")).toBe("library-filters");
    expect(panel.classes()).toContain("hidden"); // md:grid keeps it visible on desktop
    expect(wrapper.find('[data-test="filters-badge"]').exists()).toBe(false);

    await toggle.trigger("click");
    expect(toggle.attributes("aria-expanded")).toBe("true");
    expect(panel.classes()).not.toContain("hidden");
    await toggle.trigger("click");
    expect(panel.classes()).toContain("hidden");
  });

  it("badges the Filters button with the active select filters and opens itself for a filtered link", async () => {
    const { wrapper } = await mountLibrary("/?t=es&st=ready&c=doors&q=bell");
    expect(wrapper.get('[data-test="filters-toggle"]').attributes("aria-expanded")).toBe("true");
    // category and search are visible on their own, so only the two panel filters count
    expect(wrapper.get('[data-test="filters-badge"]').text()).toBe("2");
  });

  it("keeps the Filters panel closed for links that only carry a category or a search", async () => {
    const { wrapper } = await mountLibrary("/?c=doors&q=bell");
    expect(wrapper.get('[data-test="filters-toggle"]').attributes("aria-expanded")).toBe("false");
  });

  it("clears every filter at once", async () => {
    const { wrapper, router } = await mountLibrary("/?c=doors&q=bell");
    const clear = wrapper.get('[data-test="clear-filters"]');
    expect(clear.attributes("disabled")).toBeUndefined();
    await clear.trigger("click");
    await flushPromises();
    expect(query(router)).toEqual({});
    expect((wrapper.get('[data-test="search"]').element as HTMLInputElement).value).toBe("");
    expect(titles(wrapper)).toHaveLength(4);
  });

  it("explains when nothing matches and offers to clear the filters", async () => {
    const { wrapper, router } = await mountLibrary("/?q=zzzz");
    const none = wrapper.get('[data-test="no-match"]');
    expect(none.text()).toContain("No sounds match");
    await none.get("button").trigger("click");
    await flushPromises();
    expect(query(router)).toEqual({});
    expect(titles(wrapper)).toHaveLength(4);
  });
});

describe("opening and playing", () => {
  it("opens the editor keeping the filters in the query", async () => {
    const { wrapper, router } = await mountLibrary("/?c=doors");
    await wrapper.findAll('[data-test="body"]')[0]!.trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.name).toBe("sound");
    expect(router.currentRoute.value.params.id).toBe("s1");
    expect(query(router)).toEqual({ c: "doors" });
  });

  it("plays the published revision through the shared player", async () => {
    const { wrapper } = await mountLibrary();
    await wrapper.findAll('[data-test="play"]')[0]!.trigger("click");
    expect(mocks.player.toggle).toHaveBeenCalledWith("s1", "api/ui/sounds/s1/published?v=1");
  });

  it("marks the sound that is playing", async () => {
    const player = usePlayer();
    player.currentId.value = "s2";
    player.playing.value = true;
    const { wrapper } = await mountLibrary();
    const states = wrapper.findAll('[data-test="play"]').map((p) => p.attributes("aria-pressed"));
    expect(states).toEqual(["false", "true", "false", "false"]);
  });

  it("stops playback when leaving the library", async () => {
    const { wrapper } = await mountLibrary();
    wrapper.unmount();
    mounted = null;
    expect(mocks.player.stop).toHaveBeenCalled();
  });
});

describe("loudness strip", () => {
  it("appears for a category with two measured sounds and levels it through a profile", async () => {
    const { wrapper } = await mountLibrary("/?c=doors");
    expect(wrapper.get('[data-test="spread"]').text()).toBe("Spread 6.0 LU");
    await wrapper.get('[data-test="level"]').trigger("click");
    await flushPromises();
    const dialog = wrapper.get('[role="dialog"]');
    expect(dialog.text()).toContain("Level “Doors”");
    // the category's default profile is preselected
    expect((dialog.findAll('input[type="radio"]')[0]!.element as HTMLInputElement).checked).toBe(true);

    await dialog.get('[data-test="apply"]').trigger("click");
    await flushPromises();
    expect(mocks.ui.profiles.apply).toHaveBeenCalledWith("standard", { category_id: "doors" });
    expect(toasts()).toEqual(["2 sounds queued"]);
    expect(mocks.ui.sounds.list).toHaveBeenCalled();
    expect(mocks.ui.jobs).toHaveBeenCalled();
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false);
  });

  it("is hidden without a category, or with fewer than two measured sounds", async () => {
    const { wrapper } = await mountLibrary();
    expect(wrapper.find('[data-test="strip"]').exists()).toBe(false);
    await wrapper.findAll('[role="group"] button')[2]!.trigger("click"); // Alerts: one measured sound
    await flushPromises();
    expect(wrapper.find('[data-test="strip"]').exists()).toBe(false);
  });

  it("keeps the dialog open and explains a failure inline", async () => {
    mocks.ui.profiles.apply.mockRejectedValueOnce(new ApiError(409, "Profile is busy"));
    const { wrapper } = await mountLibrary("/?c=doors");
    await wrapper.get('[data-test="level"]').trigger("click");
    await flushPromises();
    await wrapper.get('[data-test="apply"]').trigger("click");
    await flushPromises();
    expect(wrapper.get('[role="dialog"] [role="alert"]').text()).toContain("Profile is busy");
    expect(toasts()).toEqual([]);
  });
});

describe("selection", () => {
  it("enters selection mode from the Select button and counts picks", async () => {
    const { wrapper } = await mountLibrary();
    expect(wrapper.find('[role="toolbar"]').exists()).toBe(false);
    await enterSelection(wrapper, "Bell", "Zebra crossing");
    expect(wrapper.get('[role="toolbar"] [data-test="count"]').text()).toBe("2 selected");
    expect(wrapper.get('[data-test="select-toggle"]').attributes("aria-pressed")).toBe("true");
  });

  it("selects every filtered sound at once", async () => {
    const { wrapper } = await mountLibrary("/?c=doors");
    await enterSelection(wrapper);
    expect(wrapper.get('[data-test="select-all"]').text()).toBe("Select all (2)");
    await wrapper.get('[data-test="select-all"]').trigger("click");
    expect(wrapper.get('[role="toolbar"] [data-test="count"]').text()).toBe("2 selected");
  });

  it("toggles a sound off again, and leaves selection mode with Done", async () => {
    const { wrapper } = await mountLibrary();
    await enterSelection(wrapper, "Bell");
    await wrapper.findAll("li")[0]!.get('[data-test="select"]').trigger("click");
    expect(wrapper.get('[role="toolbar"] [data-test="count"]').text()).toBe("0 selected");
    await wrapper.get('[data-test="done"]').trigger("click");
    expect(wrapper.find('[role="toolbar"]').exists()).toBe(false);
  });

  it("taps select instead of opening while selecting", async () => {
    const { wrapper, router } = await mountLibrary();
    await enterSelection(wrapper);
    await wrapper.findAll('[data-test="body"]')[0]!.trigger("click");
    expect(router.currentRoute.value.name).toBe("library");
    expect(wrapper.get('[role="toolbar"] [data-test="count"]').text()).toBe("1 selected");
  });

  it("leaves selection mode with Escape", async () => {
    const { wrapper } = await mountLibrary();
    await enterSelection(wrapper, "Bell");
    await wrapper.get('[data-test="library"]').trigger("keydown", { key: "Escape" });
    expect(wrapper.find('[role="toolbar"]').exists()).toBe(false);
  });

  it("drops selected sounds that a filter change hides", async () => {
    const { wrapper } = await mountLibrary();
    await enterSelection(wrapper, "Bell", "Zebra crossing");
    await wrapper.findAll('[role="group"] button')[1]!.trigger("click"); // Doors only
    await flushPromises();
    expect(wrapper.get('[role="toolbar"] [data-test="count"]').text()).toBe("1 selected");
  });

  it("leaves selection mode when the library becomes empty", async () => {
    const { wrapper } = await mountLibrary();
    await enterSelection(wrapper, "Bell");
    useStudio().sounds.value = [];
    await flushPromises();
    expect(wrapper.find('[role="toolbar"]').exists()).toBe(false);
    expect(wrapper.find('[data-test="empty"]').exists()).toBe(true);
  });

  it("hides the floating upload button while selecting", async () => {
    const { wrapper } = await mountLibrary();
    const fab = wrapper.get('[data-test="fab"]');
    expect(fab.attributes("href")).toBe("/upload");
    expect(fab.classes()).toContain("md:hidden");
    await enterSelection(wrapper);
    expect(wrapper.find('[data-test="fab"]').exists()).toBe(false);
  });
});

describe("bulk actions", () => {
  const ids = (...list: string[]) => expect.arrayContaining(list);

  async function bulk(wrapper: VueWrapper, action: string) {
    await wrapper.get(`[data-test="action-${action}"]`).trigger("click");
    await flushPromises();
  }
  const dialog = (wrapper: VueWrapper) => wrapper.get('[role="dialog"]');
  const apply = async (wrapper: VueWrapper) => {
    await dialog(wrapper).get('[data-test="apply"]').trigger("click");
    await flushPromises();
  };

  it("enables and disables the selection, then toasts and refreshes sounds and jobs", async () => {
    const { wrapper } = await mountLibrary();
    await enterSelection(wrapper, "Bell", "Muted chime");
    await bulk(wrapper, "enable");
    expect(mocks.ui.sounds.bulk).toHaveBeenCalledWith({ ids: ids("s1", "s4"), set: { enabled: true } });
    expect(mocks.ui.sounds.bulk.mock.calls[0]![0].ids).toHaveLength(2);
    expect(toasts()).toEqual(["2 sounds updated"]);
    expect(mocks.ui.sounds.list).toHaveBeenCalledTimes(1);
    expect(mocks.ui.jobs).toHaveBeenCalledTimes(1);

    await bulk(wrapper, "disable");
    expect(mocks.ui.sounds.bulk).toHaveBeenLastCalledWith({ ids: ids("s1", "s4"), set: { enabled: false } });
    // the selection survives so several changes can be chained
    expect(wrapper.get('[role="toolbar"] [data-test="count"]').text()).toBe("2 selected");
  });

  it("shows the singular when one sound changed", async () => {
    mocks.ui.sounds.bulk.mockResolvedValueOnce({ updated: 1, queued: 0 });
    const { wrapper } = await mountLibrary();
    await enterSelection(wrapper, "Bell");
    await bulk(wrapper, "enable");
    expect(toasts()).toEqual(["1 sound updated"]);
  });

  it("moves the selection to another category", async () => {
    const { wrapper } = await mountLibrary();
    await enterSelection(wrapper, "Bell", "Zebra crossing");
    await bulk(wrapper, "category");
    expect(dialog(wrapper).text()).toContain("Move to category");
    expect(dialog(wrapper).get('[data-test="apply"]').attributes("disabled")).toBeDefined();
    await dialog(wrapper).get('[data-test="dialog-category"]').setValue("alerts");
    await apply(wrapper);
    expect(mocks.ui.sounds.bulk).toHaveBeenCalledWith({ ids: ids("s1", "s3"), set: { category_id: "alerts" } });
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false);
    expect(toasts()).toEqual(["2 sounds updated"]);
  });

  it("sets specific seasons, or all seasons", async () => {
    const { wrapper } = await mountLibrary();
    await enterSelection(wrapper, "Bell", "Zebra crossing");
    await bulk(wrapper, "seasons");
    expect(dialog(wrapper).get('[data-test="apply"]').attributes("disabled")).toBeDefined();
    expect(dialog(wrapper).text()).toContain("Pick at least one season");
    await dialog(wrapper).findAll('[data-test="season"]')[1]!.trigger("click");
    await apply(wrapper);
    expect(mocks.ui.sounds.bulk).toHaveBeenLastCalledWith({
      ids: ids("s1", "s3"),
      set: { seasons: ["halloween"], all_seasons: false },
    });

    await bulk(wrapper, "seasons");
    await dialog(wrapper).get('[role="switch"]').trigger("click");
    await apply(wrapper);
    expect(mocks.ui.sounds.bulk).toHaveBeenLastCalledWith({ ids: ids("s1", "s3"), set: { seasons: [], all_seasons: true } });
  });

  it("adds and removes tags in one go", async () => {
    const { wrapper } = await mountLibrary();
    await enterSelection(wrapper, "Bell", "Zebra crossing");
    await bulk(wrapper, "tags");
    const editors = dialog(wrapper).findAll("input[type='text']");
    expect(editors).toHaveLength(2);
    expect(dialog(wrapper).get('[data-test="apply"]').attributes("disabled")).toBeDefined();

    await editors[0]!.setValue("Kids Room");
    await editors[0]!.trigger("keydown", { key: "Enter" });
    await editors[1]!.setValue("bath");
    await editors[1]!.trigger("keydown", { key: "Enter" });
    await apply(wrapper);
    expect(mocks.ui.sounds.bulk).toHaveBeenCalledWith({
      ids: ids("s1", "s3"),
      set: { add_tags: ["kids_room"], remove_tags: ["bath"] },
    });
  });

  it("only sends the tag lists that were filled in, and refuses a tag both added and removed", async () => {
    const { wrapper } = await mountLibrary();
    await enterSelection(wrapper, "Bell");
    await bulk(wrapper, "tags");
    const editors = dialog(wrapper).findAll("input[type='text']");
    await editors[0]!.setValue("es");
    await editors[0]!.trigger("keydown", { key: "Enter" });
    await editors[1]!.setValue("es");
    await editors[1]!.trigger("keydown", { key: "Enter" });
    expect(dialog(wrapper).text()).toContain("can't be added and removed at the same time");
    expect(dialog(wrapper).get('[data-test="apply"]').attributes("disabled")).toBeDefined();

    const remove = dialog(wrapper).findAll('[data-test="tag"] button').at(-1)!;
    await remove.trigger("click"); // un-remove "es"
    await apply(wrapper);
    expect(mocks.ui.sounds.bulk).toHaveBeenCalledWith({ ids: ["s1"], set: { add_tags: ["es"] } });
  });

  it("normalizes with a profile, or removes normalization with None", async () => {
    mocks.ui.sounds.bulk.mockResolvedValue({ updated: 2, queued: 2 });
    const { wrapper } = await mountLibrary();
    await enterSelection(wrapper, "Bell", "Zebra crossing");
    await bulk(wrapper, "normalize");
    expect(dialog(wrapper).get('[data-test="apply"]').attributes("disabled")).toBeDefined();
    const radios = () => dialog(wrapper).findAll('input[type="radio"]');
    expect(radios()).toHaveLength(3); // None, Standard, Soft
    await radios()[2]!.setValue(true);
    await apply(wrapper);
    expect(mocks.ui.sounds.bulk).toHaveBeenLastCalledWith({ ids: ids("s1", "s3"), set: { profile_id: "soft" } });
    expect(toasts()).toEqual(["2 sounds queued"]);

    await bulk(wrapper, "normalize");
    await radios()[0]!.setValue(true);
    await apply(wrapper);
    expect(mocks.ui.sounds.bulk).toHaveBeenLastCalledWith({ ids: ids("s1", "s3"), set: { profile_id: null } });
  });

  it("deletes only after confirmation", async () => {
    const { wrapper } = await mountLibrary();
    await enterSelection(wrapper, "Bell", "Zebra crossing");
    const confirm = useConfirm();

    await wrapper.get('[data-test="action-delete"]').trigger("click");
    await flushPromises();
    expect(confirm.request.value?.danger).toBe(true);
    expect(confirm.request.value?.title).toBe("Delete 2 sounds?");
    confirm.answer(false);
    await flushPromises();
    expect(mocks.ui.sounds.bulkDelete).not.toHaveBeenCalled();

    await wrapper.get('[data-test="action-delete"]').trigger("click");
    await flushPromises();
    confirm.answer(true);
    await flushPromises();
    expect(mocks.ui.sounds.bulkDelete).toHaveBeenCalledWith(ids("s1", "s3"));
    expect(toasts()).toEqual(["2 sounds deleted"]);
    expect(mocks.ui.sounds.list).toHaveBeenCalled();
    expect(wrapper.find('[role="toolbar"]').exists()).toBe(false);
  });

  it("reports a failed direct action inline in the bar and keeps the selection", async () => {
    mocks.ui.sounds.bulk.mockRejectedValueOnce(new ApiError(500, "Database is locked"));
    const { wrapper } = await mountLibrary();
    await enterSelection(wrapper, "Bell");
    await bulk(wrapper, "enable");
    expect(wrapper.get('[role="toolbar"] [role="alert"]').text()).toContain("Database is locked");
    expect(toasts()).toEqual([]);
    expect(wrapper.get('[role="toolbar"] [data-test="count"]').text()).toBe("1 selected");

    await bulk(wrapper, "enable"); // retry succeeds and clears the message
    expect(wrapper.find('[role="toolbar"] [role="alert"]').exists()).toBe(false);
  });

  it("keeps a bulk dialog open and shows the failure in it", async () => {
    mocks.ui.sounds.bulk.mockRejectedValueOnce(new ApiError(422, "Unknown category"));
    const { wrapper } = await mountLibrary();
    await enterSelection(wrapper, "Bell");
    await bulk(wrapper, "category");
    await dialog(wrapper).get('[data-test="dialog-category"]').setValue("alerts");
    await apply(wrapper);
    expect(dialog(wrapper).get('[role="alert"]').text()).toContain("Unknown category");
    expect(wrapper.find('[role="toolbar"] [role="alert"]').exists()).toBe(false);
  });

  it("closes a dialog without calling the API", async () => {
    const { wrapper } = await mountLibrary();
    await enterSelection(wrapper, "Bell");
    await bulk(wrapper, "category");
    await dialog(wrapper).get('[data-test="cancel"]').trigger("click");
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false);
    expect(mocks.ui.sounds.bulk).not.toHaveBeenCalled();
  });
});
