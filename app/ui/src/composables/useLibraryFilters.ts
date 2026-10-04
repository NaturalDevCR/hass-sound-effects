import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useRoute, useRouter, type LocationQueryRaw } from "vue-router";
import type { SoundStatus } from "@/api/types";
import { useStudio } from "@/composables/useStudio";
import { useI18n } from "@/i18n";
import type { LibraryFilter } from "@/lib/filters";

export const STATUSES: readonly SoundStatus[] = ["processing", "ready", "rendering", "failed"];
export type FilterKey = "c" | "s" | "t" | "q" | "st";

const FILTER_KEYS: readonly FilterKey[] = ["c", "s", "t", "q", "st"];
const SEARCH_DEBOUNCE_MS = 150;

/**
 * Library filters. The route query is the source of truth (`?c=` category, `?s=` season,
 * `?t=` tag, `?q=` search, `?st=` status), so a filtered view survives reloads, Back and the
 * round trip through the editor. Per component instance (it reads the current route), unlike
 * the shared `useStudio` store.
 */
export function useLibraryFilters() {
  const route = useRoute();
  const router = useRouter();
  const { sounds, loaded, categoryById, seasonById } = useStudio();
  const { locale } = useI18n();

  function rawParam(key: FilterKey): string | null {
    const value = route.query[key];
    const first = Array.isArray(value) ? value[0] : value;
    return typeof first === "string" && first !== "" ? first : null;
  }

  const collator = computed(() => new Intl.Collator(locale.value, { sensitivity: "base", numeric: true }));
  const allTags = computed(() => [...new Set(sounds.value.flatMap((s) => s.tags))].sort(collator.value.compare));

  // A stale or hand-edited URL must not hide everything: unknown values count as "no filter" once
  // the lists have loaded (before that they cannot be judged, and the list is not shown anyway).
  const filter = computed<LibraryFilter>(() => {
    const known = <T>(value: string | null, exists: (v: string) => T | undefined | boolean) =>
      value !== null && (!loaded.value || exists(value)) ? value : null;
    const status = rawParam("st");
    return {
      categoryId: known(rawParam("c"), categoryById),
      seasonId: known(rawParam("s"), seasonById),
      tag: known(rawParam("t"), (tag) => allTags.value.includes(tag)),
      query: rawParam("q") ?? "",
      status: STATUSES.find((s) => s === status) ?? null,
    };
  });
  const hasFilters = computed(() => Object.values(filter.value).some((v) => v !== null && v !== ""));

  // On phones the three selects hide behind a "Filters" button (a badge counts the active ones) so
  // the list starts near the top of the screen; they are always visible from md up. A link that
  // already carries one of them opens the panel.
  const filtersOpen = ref(Boolean(rawParam("s") || rawParam("t") || rawParam("st")));
  const panelFilterCount = computed(
    () => [filter.value.seasonId, filter.value.tag, filter.value.status].filter(Boolean).length,
  );

  // Navigation is asynchronous: two changes made before the first one lands must build on each
  // other instead of both starting from the stale route.
  let pendingQuery: LocationQueryRaw | null = null;

  function setQuery(patch: Partial<Record<FilterKey, string | null>>): void {
    const next: LocationQueryRaw = { ...(pendingQuery ?? route.query) };
    for (const key of FILTER_KEYS) {
      if (!(key in patch)) continue;
      const value = patch[key];
      if (value) next[key] = value;
      else delete next[key];
    }
    pendingQuery = next;
    // replace, not push: tweaking filters should not bury the editor's Back target
    void router.replace({ query: next }).finally(() => {
      if (pendingQuery === next) pendingQuery = null;
    });
  }

  // The search box keeps what is typed; the route only learns about it 150 ms after the last key.
  const search = ref(rawParam("q") ?? "");
  let searchTimer: ReturnType<typeof setTimeout> | undefined;

  function onSearchInput(): void {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      searchTimer = undefined;
      setQuery({ q: search.value.trim() });
    }, SEARCH_DEBOUNCE_MS);
  }

  // External changes (clear filters, a pasted URL, Back) flow into the box, but never while the
  // user is still typing: a late route update would overwrite newer keystrokes.
  watch(
    () => rawParam("q"),
    (value) => {
      if (searchTimer === undefined && (value ?? "") !== search.value.trim()) search.value = value ?? "";
    },
  );

  function clearFilters(): void {
    clearTimeout(searchTimer);
    searchTimer = undefined;
    search.value = "";
    setQuery({ c: null, s: null, t: null, q: null, st: null });
  }

  onBeforeUnmount(() => clearTimeout(searchTimer));

  return {
    filter,
    hasFilters,
    allTags,
    collator,
    search,
    onSearchInput,
    setQuery,
    clearFilters,
    filtersOpen,
    panelFilterCount,
  };
}
