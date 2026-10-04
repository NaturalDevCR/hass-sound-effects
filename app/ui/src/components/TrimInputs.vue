<script setup lang="ts">
import { computed, nextTick, reactive, ref, useId, watch } from "vue";
import type { Recipe } from "@/api/types";
import { useI18n } from "@/i18n";
const props = defineProps<{ recipe: Recipe; duration: number; disabled: boolean }>();
const emit = defineEmits<{ trim: [start: number, end: number]; invalid: [value: boolean] }>();
const { t } = useI18n();
const id = useId();
type Side = "start" | "end";
const sides: Side[] = ["start", "end"];
const end = computed(() => props.recipe.trim_end ?? props.duration);
const draft = reactive({ start: String(props.recipe.trim_start), end: String(end.value) });
const invalid = reactive({ start: false, end: false });
watch(() => invalid.start || invalid.end, (value) => emit("invalid", value), { flush: "sync" });
const focused = ref<Side | null>(null);
const value = (side: Side) => (side === "start" ? props.recipe.trim_start : end.value);
for (const side of sides) {
  watch(() => value(side), (next) => {
    if (focused.value !== side && !invalid[side]) draft[side] = String(next);
  });
}
function parse(side: Side): number | null {
  const text = draft[side].trim().replace(",", ".");
  return /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(text) && Number.isFinite(Number(text))
    ? Number(text)
    : null;
}
function edited(side: Side) {
  invalid[side] = false;
}
function commit(side: Side, normalize = false) {
  const number = parse(side);
  invalid[side] = number === null;
  if (number === null) return;
  emit(
    "trim",
    side === "start" ? number : props.recipe.trim_start,
    side === "end" ? number : end.value,
  );
  if (normalize) {
    // Wait for the parent's recipe update before normalizing the committed draft.
    const committedDraft = draft[side];
    void nextTick(() => {
      if (draft[side] === committedDraft && !invalid[side]) draft[side] = String(value(side));
    });
  }
}
function keydown(event: KeyboardEvent, side: Side) {
  if (event.key === "Escape") {
    if (draft[side] === String(value(side)) && !invalid[side]) return;
    event.preventDefault();
    event.stopPropagation();
    draft[side] = String(value(side));
    invalid[side] = false;
    return;
  }
  if (event.key === "Enter") {
    event.preventDefault();
    commit(side, true);
    return;
  }
  if (!["ArrowUp", "ArrowDown"].includes(event.key)) return;
  event.preventDefault();
  const step = (event.shiftKey ? 0.1 : 0.01) * (event.key === "ArrowUp" ? 1 : -1);
  const number = parse(side);
  if (number === null) {
    invalid[side] = true;
    return;
  }
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
        :aria-invalid="invalid[side]"
        :aria-describedby="invalid[side] ? `${id}-${side}-error` : undefined"
        :aria-valuemin="side === 'start' ? 0 : recipe.trim_start"
        :aria-valuemax="side === 'start' ? end : duration"
        :disabled="disabled"
        class="field tabular-nums"
        @input="edited(side)"
        @focus="focused = side"
        @change="commit(side)"
        @blur="focused = null; commit(side, true)"
        @keydown="keydown($event, side)"
      />
      <p v-if="invalid[side]" :id="`${id}-${side}-error`" role="alert" class="mt-1 text-xs text-danger">
        {{ t("editor.trimInvalid") }}
      </p>
    </div>
  </div>
</template>
