<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useRoute, useRouter, type LocationQueryRaw } from "vue-router";
import {
  mdiAlertCircleOutline,
  mdiCheckboxMultipleMarkedOutline,
  mdiFilterVariant,
  mdiFilterVariantRemove,
  mdiMagnify,
  mdiMusicBoxMultiple,
  mdiMusicOff,
  mdiUpload,
} from "@mdi/js";
import { audioUrl, ui } from "@/api/client";
import type { BulkResult, BulkSet, Season, SoundStatus } from "@/api/types";
import BulkBar, { type BulkAction } from "@/components/BulkBar.vue";
import CategoryChips from "@/components/CategoryChips.vue";
import EmptyState from "@/components/EmptyState.vue";
import Icon from "@/components/Icon.vue";
import LibraryDialog, { type LibraryDialogKind, type LibraryDialogResult } from "@/components/LibraryDialog.vue";
import LoudnessStrip from "@/components/LoudnessStrip.vue";
import SoundItem from "@/components/SoundItem.vue";
import { useConfirm } from "@/composables/useConfirm";
import { useJobs } from "@/composables/useJobs";
import { usePlayer } from "@/composables/usePlayer";
import { useStudio } from "@/composables/useStudio";
import { useToast } from "@/composables/useToast";
import { useI18n } from "@/i18n";
import { filterSounds, type LibraryFilter } from "@/lib/filters";

const { t, tp, locale } = useI18n();
const route = useRoute();
const router = useRouter();
const studio = useStudio();
const { sounds, categories, seasons, loaded, loading, categoryById, seasonById, refresh } = studio;
const player = usePlayer();
const toast = useToast();
const { confirm } = useConfirm();

// --- filters: the route query is the source of truth (?c= ?s= ?t= ?q= ?st=) --------------------
const STATUSES: SoundStatus[] = ["processing", "ready", "rendering", "failed"];
const SEARCH_DEBOUNCE_MS = 150;
type FilterKey = "c" | "s" | "t" | "q" | "st";
const FILTER_KEYS: FilterKey[] = ["c", "s", "t", "q", "st"];

function rawParam(key: FilterKey): string | null {
  const value = route.query[key];
  const first = Array.isArray(value) ? value[0] : value;
  return typeof first === "string" && first !== "" ? first : null;
}

const collator = computed(() => new Intl.Collator(locale.value, { sensitivity: "base", numeric: true }));
const sortedSounds = computed(() =>
  [...sounds.value].sort((a, b) => collator.value.compare(a.title, b.title) || a.id.localeCompare(b.id)),
);
const soundsById = computed(() => new Map(sounds.value.map((s) => [s.id, s])));
const allTags = computed(() => [...new Set(sounds.value.flatMap((s) => s.tags))].sort(collator.value.compare));

// A stale or hand-edited URL must not hide everything: unknown values count as "no filter" once
// the lists have loaded (before that they cannot be judged, and the list is not shown anyway).
const filter = computed<LibraryFilter>(() => {
  const known = <T,>(value: string | null, exists: (v: string) => T | undefined | boolean) =>
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
const panelFilterCount = computed(() => [filter.value.seasonId, filter.value.tag, filter.value.status].filter(Boolean).length);

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

function onSelect(key: FilterKey, event: Event): void {
  setQuery({ [key]: (event.target as HTMLSelectElement).value });
}

// --- derived lists ---------------------------------------------------------------------------
const visible = computed(() => filterSounds(sortedSounds.value, filter.value));
const visibleIds = computed(() => new Set(visible.value.map((s) => s.id)));

// Chip counts answer "how many would I see?": every filter applies except the category itself.
const facet = computed(() => filterSounds(sortedSounds.value, { ...filter.value, categoryId: null }));
const counts = computed(() => {
  const result: Record<string, number> = {};
  for (const sound of facet.value) result[sound.category_id] = (result[sound.category_id] ?? 0) + 1;
  return result;
});

const activeCategory = computed(() => (filter.value.categoryId ? categoryById(filter.value.categoryId) : undefined));
const categorySounds = computed(() => sounds.value.filter((s) => s.category_id === filter.value.categoryId));

const showSkeleton = computed(() => !loaded.value && loading.value);
const loadFailed = computed(() => !loaded.value && !loading.value);

const resultCount = computed(() =>
  hasFilters.value
    ? t("library.count.filtered", { n: visible.value.length, total: sounds.value.length })
    : tp("library.count", sounds.value.length),
);

function seasonsOf(sound: { seasons: string[] }): Season[] {
  return sound.seasons.map((id) => seasonById(id)).filter((s): s is Season => s !== undefined);
}

// --- open and play ---------------------------------------------------------------------------
function openSound(id: string): void {
  // The query rides along so closing the editor lands on the same filtered list.
  void router.push({ name: "sound", params: { id }, query: route.query });
}

function togglePlay(id: string): void {
  const published = soundsById.value.get(id)?.published;
  if (published) player.toggle(id, audioUrl(id, "published", published.revision));
}

onBeforeUnmount(() => {
  clearTimeout(searchTimer);
  player.stop();
});

// --- selection -------------------------------------------------------------------------------
const selectMode = ref(false);
const selected = ref<Set<string>>(new Set());

function toggleSelect(id: string): void {
  selectMode.value = true;
  const next = new Set(selected.value);
  if (!next.delete(id)) next.add(id);
  selected.value = next;
}

function selectAll(): void {
  selected.value = new Set(visibleIds.value);
}

function exitSelection(): void {
  selectMode.value = false;
  selected.value = new Set();
  actionError.value = null;
}

function toggleSelectMode(): void {
  if (selectMode.value) exitSelection();
  else selectMode.value = true;
}

// Bulk actions only ever touch what is on screen: narrowing the list narrows the selection.
watch(visibleIds, (ids) => {
  if (!selected.value.size) return;
  const kept = [...selected.value].filter((id) => ids.has(id));
  if (kept.length !== selected.value.size) selected.value = new Set(kept);
});

// Nothing left to act on (everything was deleted, here or elsewhere): no empty bulk bar.
watch(
  () => sounds.value.length,
  (count) => {
    if (count === 0) exitSelection();
  },
);

function onEscape(): void {
  if (selectMode.value && dialog.value === null) exitSelection();
}

// --- bulk actions ----------------------------------------------------------------------------
const busy = ref(false);
const actionError = ref<string | null>(null);
const dialog = ref<LibraryDialogKind | null>(null);
const levelCategoryId = ref<string | null>(null);

const messageOf = (cause: unknown) => (cause instanceof Error ? cause.message : String(cause));

const bulkMessage = (result: BulkResult) =>
  result.queued > 0 ? tp("toast.bulk.queued", result.queued) : tp("toast.bulk.updated", result.updated);

/** Runs one request: pending state, inline error, success toast, then fresh sounds and jobs. */
async function perform(work: () => Promise<string>): Promise<boolean> {
  if (busy.value) return false;
  busy.value = true;
  actionError.value = null;
  try {
    toast.push(await work(), "success");
    // Renders may have been queued: refresh both lists (neither refresh throws).
    await Promise.all([studio.refreshSounds(), useJobs().refresh()]);
    return true;
  } catch (cause) {
    actionError.value = messageOf(cause);
    return false;
  } finally {
    busy.value = false;
  }
}

const bulk = (set: BulkSet) => perform(async () => bulkMessage(await ui.sounds.bulk({ ids: [...selected.value], set })));

async function onBulkAction(action: BulkAction): Promise<void> {
  actionError.value = null;
  switch (action) {
    case "enable":
    case "disable":
      await bulk({ enabled: action === "enable" });
      return;
    case "delete": {
      const ids = [...selected.value];
      const confirmed = await confirm({
        title: tp("library.confirm.delete.title", ids.length),
        message: t("library.confirm.delete.message"),
        confirmLabel: t("common.delete"),
        danger: true,
      });
      if (!confirmed) return;
      const done = await perform(async () => tp("toast.bulk.deleted", (await ui.sounds.bulkDelete(ids)).deleted));
      if (done) exitSelection();
      return;
    }
    default:
      dialog.value = action;
  }
}

function openLevel(): void {
  if (!activeCategory.value) return;
  levelCategoryId.value = activeCategory.value.id;
  actionError.value = null;
  dialog.value = "level";
}

function closeDialog(): void {
  if (busy.value) return;
  dialog.value = null;
  actionError.value = null;
}

async function onDialogSubmit(result: LibraryDialogResult): Promise<void> {
  let done: boolean;
  switch (result.kind) {
    case "category":
      done = await bulk({ category_id: result.categoryId });
      break;
    case "seasons":
      done = await bulk({ seasons: result.seasons, all_seasons: result.allSeasons });
      break;
    case "tags":
      done = await bulk({
        ...(result.add.length ? { add_tags: result.add } : {}),
        ...(result.remove.length ? { remove_tags: result.remove } : {}),
      });
      break;
    case "normalize":
      done = await bulk({ profile_id: result.profileId });
      break;
    case "level": {
      const categoryId = levelCategoryId.value;
      if (!categoryId) return;
      done = await perform(async () =>
        tp("toast.bulk.queued", (await ui.profiles.apply(result.profileId, { category_id: categoryId })).queued),
      );
      break;
    }
  }
  if (done) dialog.value = null;
}

const selectedTags = computed(() => [
  ...new Set([...selected.value].flatMap((id) => soundsById.value.get(id)?.tags ?? [])),
]);
const levelCategory = computed(() => (levelCategoryId.value ? categoryById(levelCategoryId.value) : undefined));
const dialogCount = computed(() => selected.value.size);
</script>

<template>
  <div @keydown.esc="onEscape">
    <section data-test="library" aria-labelledby="library-heading">
      <h2 id="library-heading" class="sr-only">{{ t("library.heading") }}</h2>

      <!-- First load: rows that look like the list, never a flash of "no sounds". -->
      <div v-if="showSkeleton" data-test="skeleton" aria-busy="true">
        <p role="status" class="sr-only">{{ t("common.loading") }}</p>
        <ul aria-hidden="true" class="grid grid-cols-1 gap-2 lg:grid-cols-2 xl:grid-cols-3">
          <li v-for="n in 6" :key="n" class="flex animate-pulse items-center gap-3 rounded-panel border border-line bg-surface p-2.5">
            <span class="size-12 shrink-0 rounded-full bg-raised" />
            <span class="flex-1 space-y-2">
              <span class="block h-4 w-2/3 rounded bg-raised" />
              <span class="block h-3 w-1/3 rounded bg-raised" />
            </span>
          </li>
        </ul>
      </div>

      <div v-else-if="loadFailed" data-test="load-failed">
        <EmptyState
          :icon="mdiAlertCircleOutline"
          :title="t('library.loadFailed.title')"
          :description="t('library.loadFailed.body')"
        >
          <button type="button" class="btn-primary" @click="refresh">{{ t("common.retry") }}</button>
        </EmptyState>
      </div>

      <div v-else-if="!sounds.length" data-test="empty">
        <EmptyState
          :icon="mdiMusicBoxMultiple"
          :title="t('library.empty.title')"
          :description="t('library.empty.body')"
        >
          <RouterLink :to="{ name: 'upload' }" class="btn-primary">
            <Icon :path="mdiUpload" />
            {{ t("library.empty.action") }}
          </RouterLink>
          <RouterLink :to="{ name: 'system', hash: '#import' }" class="btn">
            {{ t("library.empty.import") }}
          </RouterLink>
        </EmptyState>
      </div>

      <div v-else class="space-y-3">
        <!-- Toolbar: search + select (+ upload on desktop), then the three filters. -->
        <div class="flex gap-2">
          <div class="relative min-w-0 flex-1">
            <Icon :path="mdiMagnify" class="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-muted" />
            <input
              v-model="search"
              data-test="search"
              type="search"
              class="field pl-10"
              :placeholder="t('library.search.placeholder')"
              :aria-label="t('library.search.label')"
              enterkeyhint="search"
              autocomplete="off"
              spellcheck="false"
              @input="onSearchInput"
            />
          </div>
          <button
            data-test="select-toggle"
            type="button"
            class="btn shrink-0"
            :aria-pressed="selectMode"
            :class="{ 'border-accent! bg-accent-soft!': selectMode }"
            @click="toggleSelectMode"
          >
            <Icon :path="mdiCheckboxMultipleMarkedOutline" :size="18" />
            {{ t("library.select") }}
          </button>
          <RouterLink :to="{ name: 'upload' }" data-test="upload" class="btn-primary hidden shrink-0 md:inline-flex">
            <Icon :path="mdiUpload" :size="18" />
            {{ t("library.upload") }}
          </RouterLink>
        </div>

        <CategoryChips
          v-if="categories.length"
          :categories="categories"
          :model-value="filter.categoryId"
          :counts="counts"
          :total="facet.length"
          @update:model-value="(value) => setQuery({ c: value })"
        />

        <!-- Phones: [Filters] ... [count], with the selects opening on their own line below.
             md and up: the selects fill the row and the count sits at its end. -->
        <div class="flex flex-wrap items-center gap-x-2 gap-y-3 md:flex-nowrap">
          <button
            data-test="filters-toggle"
            type="button"
            class="btn md:hidden"
            :aria-expanded="filtersOpen"
            aria-controls="library-filters"
            @click="filtersOpen = !filtersOpen"
          >
            <Icon :path="mdiFilterVariant" :size="18" />
            {{ t("library.filters.toggle") }}
            <span
              v-if="panelFilterCount"
              data-test="filters-badge"
              class="grid h-5 min-w-5 place-items-center rounded-full bg-accent-strong px-1 text-xs leading-none font-bold text-accent-ink"
            >
              {{ panelFilterCount }}
            </span>
          </button>
          <p
            data-test="result-count"
            aria-live="polite"
            class="ml-auto text-sm whitespace-nowrap text-muted tabular-nums md:order-last md:shrink-0"
          >
            {{ resultCount }}
          </p>
          <div
            id="library-filters"
            class="min-w-0 basis-full grid-cols-2 gap-2 sm:grid-cols-4 md:order-first md:flex-1 md:basis-0"
            :class="filtersOpen ? 'grid' : 'hidden md:grid'"
          >
            <select
              data-test="filter-season"
              class="field"
              :aria-label="t('library.filter.season')"
              :value="filter.seasonId ?? ''"
              @change="onSelect('s', $event)"
            >
              <option value="">{{ t("library.filter.season.all") }}</option>
              <option v-for="season in seasons" :key="season.id" :value="season.id">{{ season.name }}</option>
            </select>
            <select
              data-test="filter-tag"
              class="field"
              :aria-label="t('library.filter.tag')"
              :value="filter.tag ?? ''"
              @change="onSelect('t', $event)"
            >
              <option value="">{{ t("library.filter.tag.all") }}</option>
              <option v-for="tag in allTags" :key="tag" :value="tag">{{ tag }}</option>
            </select>
            <select
              data-test="filter-status"
              class="field"
              :aria-label="t('library.filter.status')"
              :value="filter.status ?? ''"
              @change="onSelect('st', $event)"
            >
              <option value="">{{ t("library.filter.status.all") }}</option>
              <option v-for="status in STATUSES" :key="status" :value="status">{{ t(`status.${status}`) }}</option>
            </select>
            <button data-test="clear-filters" type="button" class="btn" :disabled="!hasFilters" @click="clearFilters">
              <Icon :path="mdiFilterVariantRemove" :size="18" />
              {{ t("library.filters.clear") }}
            </button>
          </div>
        </div>

        <LoudnessStrip
          v-if="activeCategory"
          :sounds="categorySounds"
          :category-name="activeCategory.name"
          :busy="busy"
          @level="openLevel"
        />

        <ul
          v-if="visible.length"
          data-test="list"
          class="grid grid-cols-1 gap-2 pb-20 md:pb-0 lg:grid-cols-2 lg:gap-3 xl:grid-cols-3"
          :class="{ 'pb-44! md:pb-44!': selectMode }"
        >
          <SoundItem
            v-for="sound in visible"
            :key="sound.id"
            :sound="sound"
            :seasons="seasonsOf(sound)"
            :category="filter.categoryId ? undefined : categoryById(sound.category_id)"
            :playing="player.playing.value && player.currentId.value === sound.id"
            :selected="selected.has(sound.id)"
            :selecting="selectMode"
            @open="openSound"
            @toggle-play="togglePlay"
            @select="toggleSelect"
          />
        </ul>
        <div v-else data-test="no-match">
          <EmptyState :icon="mdiMusicOff" :title="t('library.noMatch.title')" :description="t('library.noMatch.body')">
            <button type="button" class="btn-primary" @click="clearFilters">{{ t("library.filters.clear") }}</button>
          </EmptyState>
        </div>
      </div>

      <RouterLink
        v-if="loaded && sounds.length && !selectMode"
        :to="{ name: 'upload' }"
        data-test="fab"
        class="btn-primary fixed right-4 bottom-[calc(var(--tabbar-h)+1rem)] z-30 size-14 rounded-full p-0! shadow-lg shadow-black/50 md:hidden"
        :aria-label="t('library.upload')"
      >
        <Icon :path="mdiUpload" :size="26" />
      </RouterLink>

      <BulkBar
        v-if="selectMode"
        :count="selected.size"
        :total="visible.length"
        :busy="busy"
        :error="dialog === null ? actionError : null"
        @action="onBulkAction"
        @select-all="selectAll"
        @done="exitSelection"
      />

      <LibraryDialog
        :kind="dialog"
        :count="dialogCount"
        :pending="busy"
        :error="dialog === null ? null : actionError"
        :category-name="levelCategory?.name"
        :default-profile-id="levelCategory?.default_profile_id"
        :all-tags="allTags"
        :selected-tags="selectedTags"
        @close="closeDialog"
        @submit="onDialogSubmit"
      />
    </section>
    <!-- Child route: the editor renders in a Sheet above this view, which stays mounted. -->
    <RouterView />
  </div>
</template>
