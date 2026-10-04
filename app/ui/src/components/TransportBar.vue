<script setup lang="ts">
import { computed, ref, watch, type Ref } from "vue";
import { mdiPlay, mdiPause, mdiRepeat, mdiCompare } from "@mdi/js";
import Icon from "./Icon.vue";
import { useI18n } from "@/i18n";
import { formatDuration } from "@/lib/format";
const props = defineProps<{
  playing: boolean;
  loop: boolean;
  bypass: boolean;
  position: Readonly<Ref<number>>;
  trimStart: number;
  length: number;
  disabled: boolean;
}>();
const emit = defineEmits<{ play: []; loop: []; bypass: [] }>();
const { t } = useI18n();
const readout = computed(() =>
  props.bypass ? props.position.value : Math.max(0, props.position.value - props.trimStart),
);
const announcement = ref("");
watch(() => props.playing, (playing) => {
  announcement.value = t(playing ? "editor.playing" : "editor.stopped");
});
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
      <span data-test="position" class="ml-auto text-xs text-muted tabular-nums"
        >{{ formatDuration(readout) }} / {{ formatDuration(length) }}</span
      >
    </div>
    <span aria-live="polite" class="sr-only">{{ announcement }}</span>
    <p v-if="loop" class="mt-2 text-xs text-muted">{{ t("editor.loopHint") }}</p>
    <p class="mt-2 hidden text-xs text-muted md:block">{{ t("editor.shortcuts") }}</p>
  </div>
</template>
