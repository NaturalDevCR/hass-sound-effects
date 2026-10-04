<script setup lang="ts">
import { ref, watch } from "vue";
import { useI18n } from "@/i18n";
import { useStudio } from "@/composables/useStudio";
import { useSettingsSave } from "@/composables/useSettingsSave";
const { t } = useI18n();
const { state } = useStudio();
const { pending, error, save } = useSettingsSave();
const url = ref(state.value?.settings.media_base_url ?? "");
watch(
  () => state.value?.settings.media_base_url,
  (value) => {
    url.value = value ?? "";
  },
);
function validUrl(value: string) {
  if (!value) return true;
  try {
    const parsed = new URL(value);
    return /^https?:\/\//i.test(value) && !!parsed.hostname;
  } catch {
    return false;
  }
}
async function submit() {
  const value = url.value.trim();
  if (!validUrl(value)) {
    error.value = t("system.urlInvalid");
    return;
  }
  await save({ media_base_url: value });
}
</script>
<template>
  <section class="panel min-w-0 space-y-4" aria-labelledby="media-heading">
    <h3 id="media-heading" class="font-semibold">{{ t("system.media") }}</h3>
    <div>
      <p class="text-xs text-muted">{{ t("system.effective") }}</p>
      <p class="mt-1 break-all font-mono text-sm">{{ state?.media_base_url_effective }}</p>
    </div>
    <form class="space-y-3" :aria-busy="pending" novalidate @submit.prevent="submit">
      <label for="media-url" class="block text-sm">{{ t("system.override") }}</label>
      <input
        id="media-url"
        v-model="url"
        type="url"
        class="field"
        :disabled="pending"
        :aria-invalid="!!error"
        aria-describedby="media-url-hint"
        @input="error = null"
      />
      <p id="media-url-hint" class="text-sm text-muted">{{ t("system.autoHint") }}</p>
      <p v-if="error" role="alert" class="text-sm break-words text-danger">{{ error }}</p>
      <button class="btn-primary min-h-11!" :disabled="pending">
        {{ pending ? t("editor.publishPending") : t("common.save") }}
      </button>
    </form>
  </section>
</template>
