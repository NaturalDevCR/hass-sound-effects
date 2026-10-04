<script setup lang="ts">
import { useI18n } from "@/i18n";
defineProps<{
  valid: boolean;
  canSave: boolean;
  dirty: boolean;
  saving: boolean;
  deleting: boolean;
  detailsSaving: boolean;
  previewPending: boolean;
  previewReady: boolean;
  previewAvailable: boolean;
  error: string | null;
  busy: boolean;
}>();
const emit = defineEmits<{ preview: []; audition: []; save: []; revert: []; remove: [] }>();
const { t } = useI18n();
</script>
<template>
  <div class="space-y-2">
    <p v-if="error" role="alert" class="text-sm break-words text-danger">{{ error }}</p>
    <p
      v-else-if="previewReady"
      role="status"
      class="text-xs"
      :class="previewAvailable ? 'text-ok' : 'text-muted'"
    >
      {{ t(previewAvailable ? "editor.previewReady" : "editor.previewStale") }}
    </p>
    <p v-if="busy" class="text-xs text-muted">{{ t("editor.busy") }}</p>
    <div class="grid grid-cols-2 gap-2">
      <button
        data-test="preview"
        class="btn min-h-11! px-2"
        :disabled="!valid || previewPending || deleting"
        :aria-busy="previewPending"
        @click="emit('preview')"
      >
        {{ t(previewPending ? "editor.previewPending" : "editor.preview") }}
      </button>
      <button data-test="audition" class="btn min-h-11! px-2" :disabled="deleting" @click="emit('audition')">
        {{ t("editor.audition") }}
      </button>
      <button
        data-test="publish"
        class="btn-primary col-span-2 min-h-11!"
        :disabled="!canSave"
        :aria-busy="saving"
        @click="emit('save')"
      >
        {{ t(saving ? "editor.publishPending" : "editor.publish") }}
      </button>
    </div>
    <div class="flex justify-between gap-2">
      <button
        data-test="revert"
        class="btn-ghost min-h-11!"
        :disabled="!dirty || deleting || saving"
        @click="emit('revert')"
      >
        {{ t("editor.revert") }}
      </button>
      <button
        data-test="delete"
        class="btn-ghost min-h-11! text-danger!"
        :disabled="deleting || saving || detailsSaving"
        :aria-busy="deleting"
        @click="emit('remove')"
      >
        {{ t("editor.delete") }}
      </button>
    </div>
  </div>
</template>
