<script setup lang="ts">
import { computed, useId } from "vue";
import type { Recipe } from "@/api/types";
import { useI18n } from "@/i18n";
import { clipLength } from "@/lib/recipe";
import { formatDb } from "@/lib/format";
const props = defineProps<{ recipe: Recipe; duration: number }>();
const emit = defineEmits<{ change: [patch: Partial<Recipe>] }>();
const { t } = useI18n();
const id = useId();
const fadeMax = computed(() => Math.min(5, clipLength(props.recipe, props.duration) / 2));
const fades = ["fade_in", "fade_out"] as const;
</script>
<template>
  <section class="panel space-y-3">
    <h3 class="font-semibold">{{ t("editor.level") }}</h3>
    <div>
      <label :for="`${id}-gain`" class="flex items-center justify-between text-sm"
        ><span>{{ t("editor.gain") }}</span
        ><output class="text-accent tabular-nums">{{ formatDb(recipe.gain_db) }}</output></label
      >
      <input
        :id="`${id}-gain`"
        data-test="gain"
        type="range"
        min="-24"
        max="24"
        step="0.5"
        :value="recipe.gain_db"
        class="h-11 w-full cursor-pointer accent-accent"
        @input="emit('change', { gain_db: Number(($event.target as HTMLInputElement).value) })"
        @dblclick="emit('change', { gain_db: 0 })"
      />
      <p class="text-xs text-muted">{{ t("editor.gainHint") }}</p>
    </div>
    <div v-for="fade in fades" :key="fade">
      <label :for="`${id}-${fade}`" class="flex justify-between text-sm"
        ><span>{{ t(fade === "fade_in" ? "editor.fadeIn" : "editor.fadeOut") }}</span
        ><output class="text-muted tabular-nums">{{
          t("editor.seconds", { n: recipe[fade].toFixed(2) })
        }}</output></label
      >
      <input
        :id="`${id}-${fade}`"
        :data-test="fade"
        type="range"
        min="0"
        :max="fadeMax"
        step="0.01"
        :value="recipe[fade]"
        class="h-11 w-full cursor-pointer accent-accent"
        @input="emit('change', { [fade]: Number(($event.target as HTMLInputElement).value) })"
      />
    </div>
  </section>
</template>
