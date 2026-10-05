import { computed, onBeforeUnmount, ref, watch, type Ref } from "vue";
import { audioUrl, messageOf, ui } from "@/api/client";
import type { Recipe } from "@/api/types";
import { useI18n } from "@/i18n";
import { recipesEqual } from "@/lib/recipe";
import { useJobs } from "./useJobs";
import { usePlayer } from "./usePlayer";

// A short silent PCM clip unlocks this very media element during the render gesture.
const SILENCE = "data:audio/wav;base64,UklGRnQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YVAAAACAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgA==";
export function useEditorPreview(id: Readonly<Ref<string>>, recipe: Ref<Recipe>, stopLive: () => void) {
  const { t } = useI18n();
  const jobs = useJobs();
  const previewPending = ref(false);
  const previewReady = ref(false);
  const previewRecipe = ref<Recipe | null>(null);
  const previewPlaying = ref(false);
  const previewHint = ref(false);
  const previewError = ref<string | null>(null);
  const previewAvailable = computed(
    () => previewReady.value && !!previewRecipe.value && recipesEqual(recipe.value, previewRecipe.value),
  );
  let media: HTMLAudioElement | undefined;
  let jobId: string | null = null;
  let url = "";
  let generation = 0;
  let playbackGeneration = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let release: (() => void) | undefined;
  function stopPreview() {
    playbackGeneration++;
    media?.pause();
    if (media) media.currentTime = 0;
    previewPlaying.value = false;
  }
  function finish() {
    clearTimeout(timer);
    release?.();
    release = undefined;
    previewPending.value = false;
    jobId = null;
  }
  function reset() {
    generation++;
    stopPreview();
    finish();
    previewReady.value = false;
    previewRecipe.value = null;
    previewHint.value = false;
    previewError.value = null;
    url = "";
    media?.removeAttribute("src");
    media?.load();
  }
  async function playPreview() {
    if (!media || !previewReady.value || !url) return;
    stopLive();
    usePlayer().stop();
    const ticket = ++playbackGeneration;
    media.src = url;
    media.currentTime = 0;
    previewHint.value = false;
    try {
      await media.play();
      if (ticket === playbackGeneration) previewPlaying.value = true;
    } catch {
      if (ticket !== playbackGeneration) return;
      previewPlaying.value = false;
      previewHint.value = true;
    }
  }
  function togglePreview() {
    if (previewPlaying.value) stopPreview();
    else void playPreview();
  }
  async function preview() {
    if (previewPending.value) return;
    reset();
    stopLive();
    usePlayer().stop();
    media ??= new Audio();
    media.onended = () => {
      previewPlaying.value = false;
    };
    media.onpause = () => {
      if (media?.paused) previewPlaying.value = false;
    };
    media.onerror = () => {
      previewPlaying.value = false;
      previewHint.value = true;
    };
    media.src = SILENCE;
    media.load();
    // Must run synchronously inside the Preview-render click, before any API await.
    void media.play().catch(() => {});
    previewPending.value = true;
    previewRecipe.value = { ...recipe.value };
    const snapshot = { ...recipe.value };
    const ticket = generation;
    release = jobs.suppressPreviewToast(id.value);
    timer = setTimeout(() => {
      generation++;
      previewError.value = t("editor.previewTimeout");
      finish();
    }, 120_000);
    try {
      const result = await ui.sounds.preview(id.value, snapshot);
      if (ticket !== generation) return;
      jobId = result.job.id;
      await jobs.refresh();
    } catch (cause) {
      if (ticket !== generation) return;
      previewError.value = messageOf(cause);
      finish();
    }
  }
  watch(jobs.jobs, (list) => {
    const job = list.find((item) => item.id === jobId);
    if (!job || !["done", "failed"].includes(job.status)) return;
    finish();
    if (job.status === "failed") {
      previewError.value = job.error ?? t("error.unknown");
      return;
    }
    previewReady.value = true;
    url = audioUrl(id.value, "preview", Date.now());
    if (previewAvailable.value) void playPreview();
  });
  watch(id, reset);
  onBeforeUnmount(reset);
  return {
    previewPending,
    previewReady,
    previewRecipe,
    previewAvailable,
    previewPlaying,
    previewHint,
    previewError,
    preview,
    togglePreview,
    stopPreview,
  };
}
