<script setup lang="ts">
import { computed, reactive, ref, useId, watch } from "vue";
import type { Recipe } from "@/api/types";
import { useI18n } from "@/i18n";
const props = defineProps<{ recipe: Recipe; duration: number; disabled: boolean }>();
const emit = defineEmits<{ trim: [start: number, end: number] }>();
const { t } = useI18n();
const id = useId();
type Side = "start" | "end";
const sides: Side[] = ["start", "end"];
const end = computed(() => props.recipe.trim_end ?? props.duration);
const draft = reactive({ start: String(props.recipe.trim_start), end: String(end.value) });
const focused = ref<Side | null>(null);
const value = (side: Side) => (side === "start" ? props.recipe.trim_start : end.value);
for (const side of sides) {
  watch(() => value(side), (next) => {
    if (focused.value !== side) draft[side] = String(next);
  });
}
function commit(side: Side, normalize = false) {
  const text = draft[side].trim();
  const number = Number(text);
  if (text && Number.isFinite(number)) {
    emit(
      "trim",
      side === "start" ? number : props.recipe.trim_start,
      side === "end" ? number : end.value,
    );
  }
  if (normalize) {
    // Props update after the emitted change has reached the parent.
    queueMicrotask(() => {
      draft[side] = String(value(side));
    });
  }
}
function keydown(event: KeyboardEvent, side: Side) {
  if (event.key === "Enter") {
    event.preventDefault();
    commit(side, true);
    return;
  }
  if (!["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(event.key)) return;
  event.preventDefault();
  const step = (event.shiftKey ? 0.1 : 0.01) * (["ArrowUp", "ArrowRight"].includes(event.key) ? 1 : -1);
  const number = draft[side].trim() && Number.isFinite(Number(draft[side]))
    ? Number(draft[side])
    : value(side);
  draft[side] = String(Number((number + step).toFixed(2)));
  commit(side, true);
}
</script>
<template>
  <div class="grid grid-cols-2 gap-3">
    <div v-for="side in sides" :key="side">
      <label :for="`${id}-${side}`" class="mb-1 block text-xs text-muted">{{
        t(side === "start" ? "editor.start" : "editor.end")
      }}</label>
      <!-- type=number sanitizes intermediate decimals (e.g. '8.') in Safari/Chrome. -->
      <input
        :id="`${id}-${side}`"
        :data-test="`trim-${side}`"
        v-model="draft[side]"
        type="text"
        inputmode="decimal"
        role="spinbutton"
        :aria-valuenow="value(side)"
        :aria-valuemin="side === 'start' ? 0 : recipe.trim_start"
        :aria-valuemax="side === 'start' ? end : duration"
        :disabled="disabled"
        class="field tabular-nums"
        @focus="focused = side"
        @change="commit(side)"
        @blur="focused = null; commit(side, true)"
        @keydown="keydown($event, side)"
      />
    </div>
  </div>
</template>
