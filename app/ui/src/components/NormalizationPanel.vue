<script setup lang="ts">
import type { Published } from "@/api/types";
import ProfilePicker from "./ProfilePicker.vue";
import { useI18n } from "@/i18n";
import { formatDb, formatDuration, formatLufs } from "@/lib/format";
defineProps<{ modelValue: string | null; published: Published | null }>();
const emit = defineEmits<{ "update:modelValue": [value: string | null] }>();
const { t } = useI18n();
</script>
<template>
  <section class="panel space-y-3">
    <h3 class="font-semibold">{{ t("editor.normalization") }}</h3>
    <p class="text-sm text-muted">{{ t("editor.normalizeHint") }}</p>
    <ProfilePicker
      :model-value="modelValue"
      allow-none
      @update:model-value="emit('update:modelValue', $event)"
    />
    <div v-if="published" class="rounded-lg bg-ground p-3 text-xs text-muted">
      <p class="flex flex-wrap justify-between gap-2">
        <span>{{ t("editor.published") }} · {{ t("editor.revision", { n: published.revision }) }}</span
        ><span>{{ formatDuration(published.duration) }}</span>
      </p>
      <p class="mt-2 flex flex-wrap gap-x-4 gap-y-1 tabular-nums">
        <span>{{ formatLufs(published.loudness_lufs) }}</span
        ><span>{{
          t("editor.truePeak", {
            n: published.true_peak_db === null ? "—" : formatDb(published.true_peak_db),
          })
        }}</span>
      </p>
    </div>
  </section>
</template>
