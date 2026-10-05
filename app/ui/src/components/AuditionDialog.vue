<script setup lang="ts">
import { computed, ref, useId, watch } from "vue";
import { mdiSpeaker } from "@mdi/js";
import { messageOf, ui } from "@/api/client";
import { useStudio } from "@/composables/useStudio";
import { useI18n } from "@/i18n";
import EmptyState from "./EmptyState.vue";
import Sheet from "./Sheet.vue";
const props = defineProps<{ open: boolean; soundId: string; previewAvailable: boolean }>();
const emit = defineEmits<{ close: [] }>();
const { t } = useI18n();
const radioName = useId();
const { state } = useStudio();
const targets = computed(() => state.value?.settings?.audition_targets ?? []);
const targetId = ref("");
const usePreview = ref(false);
const pending = ref(false);
const error = ref<string | null>(null);
const url = ref("");
watch(
  () => props.open,
  (open) => {
    if (!open) return;
    targetId.value = targets.value[0]?.id ?? "";
    usePreview.value = false;
    error.value = null;
    url.value = "";
  },
  { immediate: true },
);
watch(
  () => props.previewAvailable,
  (available) => {
    if (!available) usePreview.value = false;
  },
);
watch(targets, (list) => {
  if (!list.some((target) => target.id === targetId.value)) targetId.value = list[0]?.id ?? "";
});
async function send() {
  if (pending.value || !targetId.value) return;
  pending.value = true;
  error.value = null;
  url.value = "";
  try {
    url.value = (
      await ui.sounds.audition(props.soundId, {
        target_id: targetId.value,
        use_preview: props.previewAvailable && usePreview.value,
      })
    ).url;
  } catch (cause) {
    error.value = messageOf(cause);
  } finally {
    pending.value = false;
  }
}
</script>
<template>
  <Sheet :open="open" :title="t('editor.audition')" @close="!pending && emit('close')">
    <div v-if="!targets.length" class="space-y-4">
      <EmptyState
        :icon="mdiSpeaker"
        :title="t('editor.noTargets')"
        :description="t('editor.noTargetsBody')"
      />
      <a href="#/system" class="btn-primary min-h-11! w-full">{{ t("editor.configure") }}</a>
    </div>
    <div v-else class="space-y-4">
      <div role="radiogroup" :aria-label="t('editor.audition')" class="space-y-2">
        <label
          v-for="target in targets"
          :key="target.id"
          class="flex min-h-11 cursor-pointer items-center gap-3 rounded-lg border border-line bg-ground p-3 has-checked:border-accent has-checked:bg-accent-soft"
        >
          <input
            v-model="targetId"
            :value="target.id"
            type="radio"
            :name="radioName"
            :disabled="pending"
            class="size-5 accent-accent"
          />
          <span class="min-w-0 text-sm"
            ><span class="block font-medium">{{ target.label }}</span
            ><span class="block break-all text-xs text-muted">{{ target.entity_id }}</span
            ><span class="block text-xs text-muted"
              >{{ t(target.kind === "script" ? "editor.script" : "editor.mediaPlayer")
              }}<template v-if="target.volume !== null">
                · {{ t("editor.volume", { n: Math.round(target.volume * 100) }) }}</template
              ></span
            ></span
          >
        </label>
      </div>
      <label v-if="previewAvailable" class="flex min-h-11 cursor-pointer items-center gap-3 text-sm"
        ><input
          v-model="usePreview"
          data-test="use-preview"
          type="checkbox"
          :disabled="pending"
          class="size-5 shrink-0 accent-accent"
        />{{ t("editor.usePreview") }}</label
      >
      <div v-if="url" role="status">
        <p class="text-sm text-ok">{{ t("editor.sent") }}</p>
        <p class="mt-1 break-all text-xs text-muted">{{ url }}</p>
      </div>
    </div>
    <template #footer>
      <p v-if="error" role="alert" class="mb-3 text-sm break-words text-danger">{{ error }}</p>
      <button
        v-if="targets.length"
        data-test="send-audition"
        class="btn-primary min-h-11! w-full"
        :disabled="!targetId || pending"
        :aria-busy="pending"
        @click="send"
      >
        {{ t(pending ? "editor.sending" : "editor.send") }}
      </button>
    </template>
  </Sheet>
</template>
