<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, toRef, useId } from "vue";
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from "vue-router";
import { mdiWaveform } from "@mdi/js";
import Sheet from "@/components/Sheet.vue";
import EmptyState from "@/components/EmptyState.vue";
import StatusPill from "@/components/StatusPill.vue";
import WaveformEditor from "@/components/WaveformEditor.vue";
import TransportBar from "@/components/TransportBar.vue";
import LevelControls from "@/components/LevelControls.vue";
import NormalizationPanel from "@/components/NormalizationPanel.vue";
import DetailsForm from "@/components/DetailsForm.vue";
import EditorActions from "@/components/EditorActions.vue";
import AuditionDialog from "@/components/AuditionDialog.vue";
import { useSoundEditor } from "@/composables/useSoundEditor";
import { useConfirm } from "@/composables/useConfirm";
import { useI18n } from "@/i18n";
import { messageOf } from "@/api/client";
import { clipLength } from "@/lib/recipe";
const props = defineProps<{ id: string }>();
const route = useRoute();
const router = useRouter();
const { t } = useI18n();
const inputId = useId();
const editor = useSoundEditor(toRef(props, "id"));
const {
  sound,
  recipe,
  details,
  tagDraft,
  recipeDirty,
  detailsDirty,
  duration,
  problems,
  valid,
  busy,
  saving,
  deleting,
  detailsSaving,
  error,
  detailsError,
  detailsValid,
  canSave,
  previewPending,
  previewReady,
  previewAvailable,
  auditionOpen,
  loaded,
} = editor;
const {
  peaks,
  loading,
  activated,
  error: audioError,
  buffer,
  position,
  playing,
  loop,
  bypass,
} = editor.audio;
const length = computed(() => (bypass.value ? duration.value : clipLength(recipe.value, duration.value)));
const end = computed(() => recipe.value.trim_end ?? duration.value);
onBeforeRouteLeave(() => editor.guard());
onBeforeRouteUpdate((to, from) => (to.params.id !== from.params.id ? editor.guard() : true));
async function close() {
  // The route guard owns confirmation, including browser back and Escape.
  if (router.options.history.state.back) router.back();
  else await router.replace({ path: "/", query: route.query });
}
function trim(start: number, finish: number) {
  editor.patchRecipe({
    trim_start: Number(start.toFixed(2)),
    trim_end: Math.abs(finish - duration.value) < 0.005 ? null : Number(finish.toFixed(2)),
  });
}
function nudge(event: KeyboardEvent, side: "start" | "end") {
  if (!["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(event.key)) return;
  event.preventDefault();
  const step = (event.shiftKey ? 0.1 : 0.01) * (["ArrowUp", "ArrowRight"].includes(event.key) ? 1 : -1);
  if (side === "start") trim(Number((recipe.value.trim_start + step).toFixed(2)), end.value);
  else trim(recipe.value.trim_start, Number((end.value + step).toFixed(2)));
}
function shortcut(event: KeyboardEvent) {
  if (
    auditionOpen.value ||
    useConfirm().request.value ||
    event.defaultPrevented ||
    event.repeat ||
    event.isComposing ||
    event.ctrlKey ||
    event.metaKey ||
    event.altKey
  )
    return;
  const target = event.target;
  if (
    target instanceof HTMLElement &&
    (target.closest('input,textarea,select,[contenteditable="true"]') ||
      (event.key === " " && target.closest("button,a")))
  )
    return;
  if (event.key === " ") {
    event.preventDefault();
    editor.audio.toggle();
  } else if (event.key.toLowerCase() === "l") loop.value = !loop.value;
  else if (event.key.toLowerCase() === "b") bypass.value = !bypass.value;
}
onMounted(() => document.addEventListener("keydown", shortcut));
onBeforeUnmount(() => document.removeEventListener("keydown", shortcut));
</script>
<template>
  <Sheet :open="true" :title="sound?.title ?? t('editor.title')" @close="close">
    <template #meta><StatusPill v-if="sound" :status="sound.status" /></template>
    <div v-if="!loaded" class="space-y-4" :aria-label="t('common.loading')" aria-busy="true">
      <div class="h-24 animate-pulse rounded-lg bg-raised" />
      <div class="h-48 animate-pulse rounded-lg bg-raised" />
    </div>
    <div v-else-if="!sound" class="space-y-4">
      <EmptyState
        :icon="mdiWaveform"
        :title="t('editor.notFound')"
        :description="t('editor.notFoundBody')"
      /><RouterLink to="/" class="btn-primary min-h-11! w-full">{{ t("editor.back") }}</RouterLink>
    </div>
    <div v-else class="min-w-0 space-y-4">
      <section class="space-y-3">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <h3 class="font-semibold">{{ t("editor.waveform") }}</h3>
          <button
            class="btn-ghost min-h-11! px-2"
            @click="editor.patchRecipe({ trim_start: 0, trim_end: null })"
          >
            {{ t("editor.resetTrim") }}
          </button>
        </div>
        <p class="text-xs text-muted">{{ t("editor.waveformHint") }}</p>
        <div v-if="audioError" class="rounded-lg border border-danger/40 bg-danger/10 p-4">
          <p role="alert" class="text-sm break-words text-danger">{{ audioError }}</p>
          <button data-test="retry-decode" class="btn mt-3 min-h-11!" @click="editor.audio.decode">
            {{ t("common.retry") }}
          </button>
        </div>
        <WaveformEditor
          v-else-if="buffer"
          :key="id"
          :peaks="peaks"
          :duration="duration"
          :recipe="recipe"
          :position="position"
          @trim="trim"
          @seek="editor.audio.seek"
          @error="audioError = messageOf($event)"
        />
        <div v-else class="grid h-24 place-items-center rounded-lg bg-ground md:h-30" :aria-busy="loading">
          <p v-if="loading" class="animate-pulse text-sm text-muted">{{ t("editor.loadingAudio") }}</p>
          <button v-else-if="!activated" class="btn min-h-11!" @click="editor.audio.decode">
            {{ t("editor.loadAudio") }}
          </button>
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label :for="`${inputId}-start`" class="mb-1 block text-xs text-muted">{{
              t("editor.start")
            }}</label
            ><input
              :id="`${inputId}-start`"
              data-test="trim-start"
              type="number"
              min="0"
              :max="end"
              step="0.01"
              :value="recipe.trim_start"
              class="field tabular-nums"
              @input="trim(Number(($event.target as HTMLInputElement).value), end)"
              @keydown="nudge($event, 'start')"
            />
          </div>
          <div>
            <label :for="`${inputId}-end`" class="mb-1 block text-xs text-muted">{{ t("editor.end") }}</label
            ><input
              :id="`${inputId}-end`"
              data-test="trim-end"
              type="number"
              :min="recipe.trim_start"
              :max="duration"
              step="0.01"
              :value="end"
              class="field tabular-nums"
              @input="trim(recipe.trim_start, Number(($event.target as HTMLInputElement).value))"
              @keydown="nudge($event, 'end')"
            />
          </div>
        </div>
        <ul v-if="problems.length" role="alert" class="space-y-1 text-sm text-danger">
          <li v-for="problem in problems" :key="problem">{{ t(problem) }}</li>
        </ul>
      </section>
      <TransportBar
        :playing="playing"
        :loop="loop"
        :bypass="bypass"
        :position="position"
        :length="length"
        :disabled="!buffer || (!bypass && !valid)"
        @play="editor.audio.toggle"
        @loop="loop = !loop"
        @bypass="bypass = !bypass"
      />
      <p v-if="sound.error" role="alert" class="text-sm break-words text-danger">{{ sound.error }}</p>
      <LevelControls :recipe="recipe" :duration="duration" @change="editor.patchRecipe" />
      <NormalizationPanel v-model="recipe.profile_id" :published="sound.published" />
      <DetailsForm
        v-model="details"
        v-model:draft="tagDraft"
        :dirty="detailsDirty"
        :valid="detailsValid"
        :pending="detailsSaving"
        :blocked="saving || deleting"
        :error="detailsError"
        @save="editor.saveDetails"
      />
    </div>
    <template v-if="sound" #footer
      ><EditorActions
        :valid="valid"
        :can-save="canSave"
        :dirty="recipeDirty"
        :saving="saving"
        :deleting="deleting"
        :details-saving="detailsSaving"
        :preview-pending="previewPending"
        :preview-ready="previewReady"
        :preview-available="previewAvailable"
        :error="error"
        :busy="busy"
        @preview="editor.preview"
        @audition="auditionOpen = true"
        @save="editor.save"
        @revert="editor.revert"
        @remove="editor.remove(close)"
    /></template>
  </Sheet>
  <AuditionDialog
    :open="auditionOpen"
    :sound-id="id"
    :preview-available="previewAvailable"
    @close="auditionOpen = false"
  />
</template>
