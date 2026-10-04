<script setup lang="ts">
import { mdiPlay, mdiPause, mdiRepeat, mdiCompare } from "@mdi/js";
import Icon from "./Icon.vue";
import { useI18n } from "@/i18n";
import { formatDuration } from "@/lib/format";
defineProps<{
  playing: boolean;
  loop: boolean;
  bypass: boolean;
  position: number;
  length: number;
  disabled: boolean;
}>();
const emit = defineEmits<{ play: []; loop: []; bypass: [] }>();
const { t } = useI18n();
</script>
<template>
  <div class="sticky top-0 z-10 -mx-1 rounded-lg border border-line bg-surface/95 px-2 py-2 backdrop-blur">
    <div class="flex flex-wrap items-center gap-2">
      <button
        data-test="play"
        class="btn-primary min-h-11! min-w-11 px-3"
        :disabled="disabled"
        :aria-label="t(playing ? 'editor.pause' : 'editor.play')"
        @click="emit('play')"
      >
        <Icon :path="playing ? mdiPause : mdiPlay" />
      </button>
      <button
        data-test="loop"
        class="btn min-h-11! px-3"
        :class="{ 'border-accent! bg-accent-soft!': loop }"
        :aria-pressed="loop"
        @click="emit('loop')"
      >
        <Icon :path="mdiRepeat" :size="18" />{{ t("editor.loop") }}
      </button>
      <button
        data-test="bypass"
        class="btn min-h-11! px-3"
        :class="{ 'border-accent! bg-accent-soft!': bypass }"
        :aria-pressed="bypass"
        @click="emit('bypass')"
      >
        <Icon :path="mdiCompare" :size="18" />{{ t("editor.bypass") }}
      </button>
      <output class="ml-auto text-xs text-muted tabular-nums"
        >{{ formatDuration(position) }} / {{ formatDuration(length) }}</output
      >
    </div>
    <p class="mt-2 hidden text-xs text-muted md:block">{{ t("editor.shortcuts") }}</p>
  </div>
</template>
