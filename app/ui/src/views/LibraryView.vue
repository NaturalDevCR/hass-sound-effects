<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
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
import { audioUrl } from "@/api/client";
import type { Season } from "@/api/types";
import BulkBar from "@/components/BulkBar.vue";
import CategoryChips from "@/components/CategoryChips.vue";
import EmptyState from "@/components/EmptyState.vue";
import Icon from "@/components/Icon.vue";
import LibraryDialog from "@/components/LibraryDialog.vue";
import LoudnessStrip from "@/components/LoudnessStrip.vue";
import SoundItem from "@/components/SoundItem.vue";
import { STATUSES, useLibraryFilters, type FilterKey } from "@/composables/useLibraryFilters";
import { usePlayer } from "@/composables/usePlayer";
import { useSelection } from "@/composables/useSelection";
import { useStudio } from "@/composables/useStudio";
import { useI18n } from "@/i18n";
import { filterSounds } from "@/lib/filters";

const { t, tp } = useI18n();
const route = useRoute();
const router = useRouter();
const { sounds, categories, seasons, loaded, loading, categoryById, seasonById, refresh } = useStudio();
const player = usePlayer();

// --- filters (query state lives in the composable) ------------------------------------------
const {
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
} = useLibraryFilters();

function onSelect(key: FilterKey, event: Event): void {
  setQuery({ [key]: (event.target as HTMLSelectElement).value });
}

// --- derived lists ---------------------------------------------------------------------------
const sortedSounds = computed(() =>
  [...sounds.value].sort((a, b) => collator.value.compare(a.title, b.title) || a.id.localeCompare(b.id)),
);
const soundsById = computed(() => new Map(sounds.value.map((s) => [s.id, s])));
const visible = computed(() => filterSounds(sortedSounds.value, filter.value));

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

// One array per sound, rebuilt only when sounds or seasons change. Building it in the template
// would hand every row a fresh array on each render of this view (every keystroke in the search
// box) and make all of them re-render for nothing.
const NO_SEASONS: Season[] = [];
const seasonsBySound = computed(
  () =>
    new Map(
      sounds.value.map((sound) => [
        sound.id,
        sound.seasons.map((id) => seasonById(id)).filter((s): s is Season => s !== undefined),
      ]),
    ),
);

// --- open and play ---------------------------------------------------------------------------
function openSound(id: string): void {
  // The query rides along so closing the editor lands on the same filtered list.
  void router.push({ name: "sound", params: { id }, query: route.query });
}

function togglePlay(id: string): void {
  const published = soundsById.value.get(id)?.published;
  if (published) player.toggle(id, audioUrl(id, "published", published.revision));
}

onBeforeUnmount(() => player.stop());

// --- selection and bulk actions (state lives in the composable) -----------------------------
const selectToggle = ref<HTMLButtonElement | null>(null);
const {
  selectMode,
  selected,
  note,
  busy,
  actionError,
  dialog,
  dialogCount,
  selectedTags,
  levelCategory,
  toggleSelect,
  selectAll,
  exitSelection,
  toggleSelectMode,
  onEscape,
  onBulkAction,
  openLevel,
  closeDialog,
  onDialogSubmit,
} = useSelection({ visible, activeCategory, returnFocusTo: selectToggle });
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
          <RouterLink :to="{ name: 'system', query: { section: 'import' } }" class="btn">
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
            ref="selectToggle"
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
             lg and up: the selects fill the row and the count sits at its end (from md the selects take
             the full row, otherwise Spanish labels get clipped next to the sidebar). -->
        <div class="flex flex-wrap items-center gap-x-2 gap-y-3 lg:flex-nowrap">
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
            class="min-w-0 basis-full grid-cols-1 gap-2 min-[28rem]:grid-cols-2 md:order-first lg:flex-1 lg:basis-0 xl:grid-cols-4"
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
            :seasons="seasonsBySound.get(sound.id) ?? NO_SEASONS"
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
        :note="note"
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
