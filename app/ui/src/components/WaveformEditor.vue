<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import WaveSurfer from "wavesurfer.js";
import Regions, { type Region } from "wavesurfer.js/dist/plugins/regions.esm.js";
import type { Recipe } from "@/api/types";
import { useI18n } from "@/i18n";
const props = defineProps<{ peaks: number[]; duration: number; recipe: Recipe; position: number }>();
const emit = defineEmits<{
  trim: [start: number, end: number];
  seek: [time: number];
  error: [cause: unknown];
}>();
const { t } = useI18n();
const container = ref<HTMLElement>();
let ws: WaveSurfer | undefined;
let region: Region | undefined;
let resizing = false;
let media: MediaQueryList;
const sync = () =>
  region?.setOptions({ start: props.recipe.trim_start, end: props.recipe.trim_end ?? props.duration });
function height() {
  ws?.setOptions({ height: media.matches ? 120 : 96 });
}
onMounted(() => {
  media = window.matchMedia("(min-width: 768px)");
  const plugin = Regions.create();
  ws = WaveSurfer.create({
    container: container.value!,
    peaks: [props.peaks],
    duration: props.duration,
    height: media.matches ? 120 : 96,
    waveColor: "#6d5b9c",
    progressColor: "#a78bfa",
    cursorColor: "#eceef4",
    cursorWidth: 2,
    barWidth: 2,
    barGap: 2,
    barRadius: 2,
    hideScrollbar: true,
    autoScroll: false,
    media: undefined,
    plugins: [plugin],
  });
  ws.on("error", (cause) => emit("error", cause));
  ws.on("ready", () => {
    region = plugin.addRegion({
      id: "trim",
      start: props.recipe.trim_start,
      end: props.recipe.trim_end ?? props.duration,
      color: "#8b5cf62b",
      drag: true,
      resize: true,
      minLength: Math.min(0.01, props.duration),
    });
    ws?.setTime(props.position);
  });
  plugin.on("region-update", (next) => {
    resizing = true;
    emit("trim", next.start, next.end);
  });
  plugin.on("region-updated", () => {
    resizing = false;
    sync();
  });
  ws.on("interaction", (time) => {
    if (!resizing) emit("seek", time);
  });
  media.addEventListener("change", height);
});
watch(
  () => [props.recipe.trim_start, props.recipe.trim_end],
  () => {
    if (!resizing) sync();
  },
);
watch(
  () => props.position,
  (time) => ws?.setTime(time),
);
onBeforeUnmount(() => {
  media?.removeEventListener("change", height);
  ws?.destroy();
});
</script>
<template>
  <div
    ref="container"
    data-test="waveform"
    class="editor-waveform min-w-0 rounded-lg bg-ground"
    :aria-label="t('editor.waveform')"
  />
</template>
<style>
.editor-waveform ::part(region) {
  border-inline: 2px solid #a78bfa;
  touch-action: none;
}
.editor-waveform ::part(region-handle) {
  width: 24px !important;
  border: 0 !important;
  touch-action: none;
  background:
    linear-gradient(#ddd6fe, #ddd6fe) center / 3px 28px no-repeat,
    #8b5cf640;
}
.editor-waveform ::part(region-handle-left) {
  left: 0 !important;
}
.editor-waveform ::part(region-handle-right) {
  right: 0 !important;
}
</style>
