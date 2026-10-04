<script setup lang="ts">
import { computed, onBeforeUnmount } from "vue";
import { mdiCheckboxBlankCircleOutline, mdiCheckCircle, mdiPlay, mdiStop, mdiVolumeOff } from "@mdi/js";
import type { Category, Season, Sound } from "@/api/types";
import Icon from "@/components/Icon.vue";
import SeasonBadge from "@/components/SeasonBadge.vue";
import StatusPill from "@/components/StatusPill.vue";
import { useI18n } from "@/i18n";
import { formatDuration, formatLufs } from "@/lib/format";

// One library entry: a row on phones, a card in the grid from lg up (same markup, the parent's
// grid and these classes do the rest). Presentational: the parent owns playback and selection.
const props = defineProps<{
  sound: Sound;
  /** The sound's seasons, already resolved to objects (ignored when it plays in all seasons). */
  seasons: Season[];
  playing: boolean;
  selected: boolean;
  /** Selection mode: a body tap toggles the selection instead of opening the editor. */
  selecting: boolean;
  /** Passed only when the list mixes categories; names the sound's category in the meta line. */
  category?: Category;
}>();
const emit = defineEmits<{ open: [id: string]; "toggle-play": [id: string]; select: [id: string] }>();

const { t } = useI18n();

const MAX_SEASONS = 2;
const MAX_TAGS = 3;
const LONG_PRESS_MS = 450;
const MOVE_TOLERANCE_PX = 8;
/** A long press is followed by the click of the same touch: swallow it for this long. */
const CLICK_GUARD_MS = 400;

const ALL_SEASONS = { color: "#9aa1b2", icon: "mdi:calendar" };

const duration = computed(() => {
  const seconds = props.sound.published?.duration ?? props.sound.original?.duration;
  return typeof seconds === "number" ? formatDuration(seconds) : "—";
});
const loudness = computed(() => formatLufs(props.sound.published?.loudness_lufs ?? null));

const shownSeasons = computed(() => props.seasons.slice(0, MAX_SEASONS));
const shownTags = computed(() => props.sound.tags.slice(0, MAX_TAGS));
const hiddenCount = computed(() => {
  const seasons = props.sound.all_seasons ? 0 : Math.max(0, props.seasons.length - MAX_SEASONS);
  return seasons + Math.max(0, props.sound.tags.length - MAX_TAGS);
});

const canPlay = computed(() => props.sound.published !== null);
// Only unusual states get a pill: a column of "Ready" on every row would drown the ones that matter.
const showStatus = computed(() => props.sound.status !== "ready");
const error = computed(() => (props.sound.status === "failed" ? (props.sound.error ?? undefined) : undefined));

const rowTone = computed(() =>
  props.selected
    ? "border-accent bg-accent-soft"
    : props.playing
      ? "border-accent/50 bg-raised"
      : "border-line bg-surface hover:bg-raised",
);

// --- long press (touch and pen only; a mouse uses the hover checkbox) -------------------------
let pressTimer: ReturnType<typeof setTimeout> | undefined;
let guardTimer: ReturnType<typeof setTimeout> | undefined;
let origin: { x: number; y: number } | null = null;
let swallowClick = false;
let lastPointerType = "mouse";

function cancelPress(): void {
  clearTimeout(pressTimer);
  pressTimer = undefined;
  origin = null;
}

function onPointerDown(event: PointerEvent): void {
  clearTimeout(guardTimer);
  swallowClick = false;
  lastPointerType = event.pointerType;
  if (event.pointerType === "mouse" || !event.isPrimary || props.selecting) return;
  origin = { x: event.clientX, y: event.clientY };
  clearTimeout(pressTimer);
  pressTimer = setTimeout(() => {
    pressTimer = undefined;
    swallowClick = true;
    emit("select", props.sound.id);
  }, LONG_PRESS_MS);
}

// Scrolling starts a pointercancel on its own; this also catches a finger that drifts first.
function onPointerMove(event: PointerEvent): void {
  if (!origin) return;
  if (Math.hypot(event.clientX - origin.x, event.clientY - origin.y) > MOVE_TOLERANCE_PX) cancelPress();
}

function onPointerEnd(): void {
  cancelPress();
  if (swallowClick) guardTimer = setTimeout(() => (swallowClick = false), CLICK_GUARD_MS);
}

// The browser's long-press menu (copy, share...) would fight the selection gesture.
function onContextMenu(event: Event): void {
  if (lastPointerType !== "mouse") event.preventDefault();
}

function onBodyClick(): void {
  if (swallowClick) return;
  if (props.selecting) emit("select", props.sound.id);
  else emit("open", props.sound.id);
}

onBeforeUnmount(() => {
  cancelPress();
  clearTimeout(guardTimer);
});
</script>

<template>
  <li :data-selected="selected" class="group relative min-w-0">
    <div
      class="flex items-center gap-2 rounded-panel border p-2.5 transition-colors lg:gap-3 lg:p-3.5"
      :class="rowTone"
    >
      <!-- Hover checkbox on desktop; an inline, always visible one once selecting. -->
      <button
        data-test="select"
        type="button"
        role="checkbox"
        :aria-checked="selected"
        :aria-label="t('library.item.select', { title: sound.title })"
        class="grid shrink-0 place-items-center rounded-full transition-opacity"
        :class="
          selecting
            ? 'size-11'
            : 'absolute -top-2 -left-2 z-10 size-7 border border-line bg-raised opacity-0 shadow-md group-hover:opacity-100 focus-visible:opacity-100 [@media(pointer:coarse)]:hidden'
        "
        @click.stop="emit('select', sound.id)"
      >
        <Icon
          :path="selected ? mdiCheckCircle : mdiCheckboxBlankCircleOutline"
          :size="selecting ? 26 : 20"
          :class="selected ? 'text-accent' : 'text-muted'"
        />
      </button>

      <button
        data-test="play"
        type="button"
        class="grid size-12 shrink-0 place-items-center rounded-full border transition-colors disabled:cursor-not-allowed disabled:opacity-40"
        :class="
          playing
            ? 'border-accent-strong bg-accent-strong text-accent-ink'
            : 'border-line bg-raised text-ink enabled:hover:bg-hover'
        "
        :disabled="!canPlay"
        :aria-pressed="playing"
        :aria-label="t(playing ? 'library.item.stop' : 'library.item.play', { title: sound.title })"
        @click="emit('toggle-play', sound.id)"
      >
        <Icon :path="playing ? mdiStop : mdiPlay" :size="26" />
      </button>

      <button
        data-test="body"
        type="button"
        class="min-h-12 min-w-0 flex-1 rounded-lg text-left [-webkit-touch-callout:none] select-none"
        @click="onBodyClick"
        @pointerdown="onPointerDown"
        @pointermove="onPointerMove"
        @pointerup="onPointerEnd"
        @pointercancel="onPointerEnd"
        @contextmenu="onContextMenu"
      >
        <span data-test="content" class="flex min-w-0 flex-col gap-1" :class="{ 'opacity-60': !sound.enabled }">
          <span class="flex min-w-0 items-center gap-2">
            <span data-test="title" class="truncate text-base leading-tight font-medium">{{ sound.title }}</span>
            <span v-if="showStatus" data-test="status" class="shrink-0" :title="error">
              <StatusPill :status="sound.status" />
              <span v-if="error" class="sr-only">{{ error }}</span>
            </span>
            <span
              v-if="!sound.enabled"
              data-test="disabled-badge"
              class="inline-flex shrink-0 items-center gap-1 rounded-full border border-line bg-hover px-2 py-0.5 text-xs font-medium text-ink"
            >
              <Icon :path="mdiVolumeOff" :size="14" />
              {{ t("library.item.disabled") }}
            </span>
          </span>
          <span data-test="meta" class="flex min-w-0 items-center gap-1.5 text-sm text-muted tabular-nums">
            <template v-if="category">
              <span
                aria-hidden="true"
                class="size-2 shrink-0 rounded-full"
                :style="{ backgroundColor: category.color }"
              />
              <span class="truncate">{{ category.name }}</span>
              <span aria-hidden="true">·</span>
            </template>
            <span class="shrink-0">{{ duration }}</span>
            <span aria-hidden="true">·</span>
            <span class="shrink-0">{{ loudness }}</span>
          </span>
          <span data-test="chips" class="flex flex-wrap items-center gap-1">
            <SeasonBadge
              v-if="sound.all_seasons"
              :season="{ ...ALL_SEASONS, name: t('library.item.allSeasons') }"
            />
            <template v-else>
              <SeasonBadge v-for="season in shownSeasons" :key="season.id" :season="season" />
            </template>
            <span
              v-for="tag in shownTags"
              :key="tag"
              class="max-w-28 truncate rounded-full bg-hover px-2 py-0.5 text-xs text-muted"
            >
              #{{ tag }}
            </span>
            <span v-if="hiddenCount > 0" class="px-1 text-xs text-muted tabular-nums">
              {{ t("library.item.more", { n: hiddenCount }) }}
            </span>
          </span>
        </span>
      </button>
    </div>
  </li>
</template>
