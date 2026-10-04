<script setup lang="ts">
import { ref, watch } from "vue";
import { useStudio } from "@/composables/useStudio";
import { useSettingsSave } from "@/composables/useSettingsSave";
import { useI18n } from "@/i18n";
const { t } = useI18n();
const { state } = useStudio();
const { pending, error, save } = useSettingsSave();
const upload = ref(state.value?.settings.max_upload_mb ?? 100);
const duration = ref(state.value?.settings.max_duration_s ?? 600);
watch(
  () => state.value?.settings.max_upload_mb,
  (value) => {
    if (value !== undefined) upload.value = value;
  },
);
watch(
  () => state.value?.settings.max_duration_s,
  (value) => {
    if (value !== undefined) duration.value = value;
  },
);
async function submit() {
  if (
    !Number.isInteger(upload.value) ||
    upload.value < 1 ||
    upload.value > 1000 ||
    !Number.isInteger(duration.value) ||
    duration.value < 1 ||
    duration.value > 3600
  ) {
    error.value = t("system.limitsInvalid");
    return;
  }
  await save({ max_upload_mb: upload.value, max_duration_s: duration.value });
}
</script>
<template>
  <section class="panel min-w-0 space-y-4" aria-labelledby="limits-heading">
    <h3 id="limits-heading" class="font-semibold">{{ t("system.limits") }}</h3>
    <form class="space-y-4" :aria-busy="pending" novalidate @submit.prevent="submit">
      <div>
        <label for="limit-upload" class="mb-1 block text-sm">{{ t("system.uploadLimit") }}</label
        ><input
          id="limit-upload"
          v-model.number="upload"
          class="field"
          type="number"
          min="1"
          max="1000"
          step="1"
          :disabled="pending"
          @input="error = null"
        />
      </div>
      <div>
        <label for="limit-duration" class="mb-1 block text-sm">{{ t("system.durationLimit") }}</label
        ><input
          id="limit-duration"
          v-model.number="duration"
          class="field"
          type="number"
          min="1"
          max="3600"
          step="1"
          :disabled="pending"
          @input="error = null"
        />
      </div>
      <p v-if="error" role="alert" class="text-sm break-words text-danger">{{ error }}</p>
      <button class="btn-primary min-h-11!" :disabled="pending">
        {{ pending ? t("editor.publishPending") : t("common.save") }}
      </button>
    </form>
  </section>
</template>
