<script setup lang="ts">
import { mdiCheck } from "@mdi/js";
import Icon from "@/components/Icon.vue";
import { useStudio } from "@/composables/useStudio";
import { useI18n } from "@/i18n";
import { resolveIcon } from "@/lib/icons";

export type SeasonSelection = { seasons: string[]; all_seasons: boolean };

// Generic season chooser (v-model = { seasons, all_seasons }). "All seasons" overrides the chips
// but does not clear them, so switching it off again brings the previous choice back.
const props = defineProps<{ modelValue: SeasonSelection }>();
const emit = defineEmits<{ "update:modelValue": [value: SeasonSelection] }>();

const { t } = useI18n();
const { seasons } = useStudio();

function toggleSeason(id: string): void {
  const chosen = new Set(props.modelValue.seasons);
  if (!chosen.delete(id)) chosen.add(id);
  // Catalog order keeps the stored list stable no matter which chip was tapped first.
  emit("update:modelValue", {
    seasons: seasons.value.map((s) => s.id).filter((seasonId) => chosen.has(seasonId)),
    all_seasons: props.modelValue.all_seasons,
  });
}

function toggleAll(): void {
  emit("update:modelValue", { seasons: props.modelValue.seasons, all_seasons: !props.modelValue.all_seasons });
}
</script>

<template>
  <div role="group" :aria-label="t('picker.season.label')" class="space-y-3">
    <button
      type="button"
      role="switch"
      :aria-checked="modelValue.all_seasons"
      class="flex min-h-11 w-full items-center gap-3 rounded-lg border border-line bg-ground px-3 py-2 text-left transition-colors hover:bg-raised"
      :class="{ 'border-accent bg-accent-soft': modelValue.all_seasons }"
      @click="toggleAll"
    >
      <span class="min-w-0 flex-1">
        <span class="block text-sm font-medium">{{ t("picker.season.all") }}</span>
        <span v-if="modelValue.all_seasons" class="block text-xs text-muted">{{ t("picker.season.allHint") }}</span>
      </span>
      <span
        aria-hidden="true"
        class="relative h-6 w-11 shrink-0 rounded-full transition-colors"
        :class="modelValue.all_seasons ? 'bg-accent-strong' : 'bg-hover'"
      >
        <span
          class="absolute top-0.5 left-0.5 size-5 rounded-full bg-white transition-transform"
          :class="{ 'translate-x-5': modelValue.all_seasons }"
        />
      </span>
    </button>

    <div class="flex flex-wrap gap-2" :class="{ 'opacity-50': modelValue.all_seasons }">
      <button
        v-for="season in seasons"
        :key="season.id"
        data-test="season"
        type="button"
        class="chip"
        :disabled="modelValue.all_seasons"
        :aria-pressed="modelValue.seasons.includes(season.id)"
        :style="
          modelValue.seasons.includes(season.id)
            ? {
                borderColor: season.color,
                backgroundColor: `color-mix(in srgb, ${season.color} 18%, transparent)`,
                color: 'var(--color-ink)',
              }
            : undefined
        "
        @click="toggleSeason(season.id)"
      >
        <span class="inline-flex" :style="{ color: season.color }">
          <Icon :path="resolveIcon(season.icon)" :size="16" />
        </span>
        {{ season.name }}
        <Icon v-if="modelValue.seasons.includes(season.id)" :path="mdiCheck" :size="16" />
      </button>
    </div>
  </div>
</template>
