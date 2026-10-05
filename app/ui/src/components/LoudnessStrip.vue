<script setup lang="ts">
import { computed } from "vue";
import { mdiTune } from "@mdi/js";
import type { Sound } from "@/api/types";
import Icon from "@/components/Icon.vue";
import { useI18n } from "@/i18n";
import { loudnessSpread } from "@/lib/filters";
import { formatLufs } from "@/lib/format";

// Per-category loudness overview: one tick per sound between the quietest and the loudest, and
// the spread between them. Renders nothing until two sounds have a measured loudness.
const props = defineProps<{ sounds: Sound[]; categoryName: string; busy?: boolean }>();
const emit = defineEmits<{ level: [] }>();

const { t } = useI18n();

/** Spread (in LU) up to which a category counts as evenly leveled. */
const EVEN_SPREAD = 3;

const ticks = computed(() =>
  props.sounds.flatMap((sound) => {
    const lufs = sound.published?.loudness_lufs;
    return typeof lufs === "number" && Number.isFinite(lufs) ? [{ id: sound.id, title: sound.title, lufs }] : [];
  }),
);
const range = computed(() => (ticks.value.length >= 2 ? loudnessSpread(props.sounds) : null));

function position(lufs: number): string {
  const r = range.value;
  if (!r || r.spread === 0) return "50%";
  return `${Number((((lufs - r.min) / r.spread) * 100).toFixed(2))}%`;
}

const spreadText = computed(() => (range.value ? range.value.spread.toFixed(1) : ""));
const even = computed(() => (range.value ? range.value.spread <= EVEN_SPREAD : true));
const summary = computed(() =>
  range.value
    ? t("library.strip.label", {
        n: ticks.value.length,
        category: props.categoryName,
        min: formatLufs(range.value.min),
        max: formatLufs(range.value.max),
        spread: spreadText.value,
      })
    : "",
);
</script>

<template>
  <section
    v-if="range"
    data-test="strip"
    class="panel flex flex-col gap-3 p-3 md:flex-row md:items-center md:gap-5 md:p-4"
  >
    <div class="min-w-0 flex-1">
      <div class="mb-1 flex items-baseline justify-between gap-2 text-xs text-muted tabular-nums">
        <span data-test="min">{{ formatLufs(range.min) }}</span>
        <span data-test="spread" class="font-medium" :class="even ? 'text-ok' : 'text-warn'">
          {{ t("library.strip.spread", { n: spreadText }) }}
        </span>
        <span data-test="max">{{ formatLufs(range.max) }}</span>
      </div>
      <div role="img" :aria-label="summary" class="relative h-6">
        <div class="absolute inset-x-1 top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-hover" />
        <div class="absolute inset-x-1 inset-y-0">
          <span
            v-for="tick in ticks"
            :key="tick.id"
            data-test="tick"
            class="absolute top-1/2 h-5 w-1 -translate-x-1/2 -translate-y-1/2 rounded-full bg-accent/70"
            :style="{ left: position(tick.lufs) }"
            :title="`${tick.title}: ${formatLufs(tick.lufs)}`"
          />
        </div>
      </div>
      <p class="mt-1 text-xs text-muted">{{ even ? t("library.strip.even") : t("library.strip.uneven") }}</p>
    </div>
    <button data-test="level" type="button" class="btn shrink-0" :disabled="busy" @click="emit('level')">
      <Icon :path="mdiTune" :size="18" />
      {{ t("library.strip.level") }}
    </button>
  </section>
</template>
