<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, toRef } from "vue";
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from "vue-router";
import { mdiWaveform } from "@mdi/js";
import Sheet from "@/components/Sheet.vue";
import EmptyState from "@/components/EmptyState.vue";
import StatusPill from "@/components/StatusPill.vue";
import TrimInputs from "@/components/TrimInputs.vue";
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
import { clipLength } from "@/lib/recipe";
const props = defineProps<{ id: string }>();
const route = useRoute();
const router = useRouter();
const { t } = useI18n();
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
  actionError,
  detailsValid,
  canSave,
  previewPending,
  previewReady,
  previewAvailable,
  previewPlaying,
  previewHint,
  auditionOpen,
  loaded,
} = editor;
const {
  peaks,
  loading,
  activated,
  error: audioError,
  buffer,
  playing,
  loop,
  bypass,
} = editor.audio;
const length = computed(() => (bypass.value ? duration.value : clipLength(recipe.value, duration.value)));
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
    trim_end: finish >= duration.value - 0.0005 ? null : Number(finish.toFixed(2)),
  });
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
    (target.closest('select,textarea,[contenteditable]:not([contenteditable="false"])') ||
      (target instanceof HTMLInputElement && ["text", "number", "search", "email", "password", "tel", "url", "date", "datetime-local", "month", "week", "time"].includes(target.type)))
  )
    return;
  if (event.key === " ") {
    if (target instanceof HTMLElement && target.closest(
      'button,a,[role="switch"],[role="radio"],input[type="checkbox"],input[type="radio"],select',
    )) return;
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
          :position="editor.audio.position"
          @trim="trim"
          @seek="editor.audio.seek"
          @error="audioError = t('editor.decodeError')"
        />
        <div v-else class="grid h-24 place-items-center rounded-lg bg-ground md:h-30" :aria-busy="loading">
          <p v-if="!sound.original" class="text-sm text-muted">{{ t("editor.waveformProcessing") }}</p>
          <p v-else-if="loading" class="animate-pulse text-sm text-muted">{{ t("editor.loadingAudio") }}</p>
          <button v-else-if="!activated" class="btn min-h-11!" @click="editor.audio.decode">
            {{ t("editor.loadAudio") }}
          </button>
        </div>
        <TrimInputs :recipe="recipe" :duration="duration" :disabled="!sound.original" @trim="trim" @invalid="editor.trimInvalid.value = $event" />
        <ul v-if="problems.length" role="alert" class="space-y-1 text-sm text-danger">
          <li v-for="problem in problems" :key="problem">{{ t(problem) }}</li>
        </ul>
      </section>
      <TransportBar
        :playing="playing"
        :loop="loop"
        :bypass="bypass"
        :position="editor.audio.position"
        :length="length"
        :trim-start="recipe.trim_start"
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
        :error="actionError"
        :preview-playing="previewPlaying"
        :preview-hint="previewHint"
        :busy="busy"
        @preview="editor.preview"
        @play-preview="editor.togglePreview"
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
