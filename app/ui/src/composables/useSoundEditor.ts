import { computed, onBeforeUnmount, ref, watch, type Ref } from "vue";
import { messageOf, ui } from "@/api/client";
import type { Recipe, Sound } from "@/api/types";
import { useI18n } from "@/i18n";
import { clampRecipe, IDENTITY, recipesEqual, validateRecipe } from "@/lib/recipe";
import { addTag } from "@/lib/tags";
import { useConfirm } from "./useConfirm";
import { useJobs } from "./useJobs";
import { useEditorPreview } from "./useEditorPreview";
import { useStudio } from "./useStudio";
import { useToast } from "./useToast";
import { useEditorAudio } from "./useEditorAudio";
export type EditorDetails = Pick<
  Sound,
  "title" | "category_id" | "seasons" | "all_seasons" | "tags" | "enabled" | "notes"
>;
const detailsOf = (s: Sound): EditorDetails => ({
  title: s.title,
  category_id: s.category_id,
  seasons: [...s.seasons],
  all_seasons: s.all_seasons,
  tags: [...s.tags],
  enabled: s.enabled,
  notes: s.notes,
});
const equalDetails = (a: EditorDetails, b: EditorDetails) => JSON.stringify(a) === JSON.stringify(b);

export function useSoundEditor(id: Readonly<Ref<string>>) {
  const { t } = useI18n();
  const studio = useStudio();
  const jobs = useJobs();
  const toast = useToast();
  const sound = computed(() => studio.sounds.value.find((s) => s.id === id.value));
  const recipe = ref<Recipe>({ ...IDENTITY });
  const savedRecipe = ref<Recipe>({ ...IDENTITY });
  const details = ref<EditorDetails>({
    title: "",
    category_id: "",
    tags: [],
    seasons: [],
    all_seasons: false,
    enabled: true,
    notes: "",
  });
  const savedDetails = ref<EditorDetails>({ ...details.value });
  const tagDraft = ref("");
  const effectiveDetails = computed(() => ({
    ...details.value,
    title: details.value.title.trim(),
    tags: addTag(details.value.tags, tagDraft.value),
  }));
  const recipeDirty = computed(() => !recipesEqual(recipe.value, savedRecipe.value));
  const detailsDirty = computed(
    () => !equalDetails(effectiveDetails.value, savedDetails.value) || !!tagDraft.value.trim(),
  );
  const dirty = computed(() => recipeDirty.value || detailsDirty.value);
  const valid = computed(() => problems.value.length === 0 && !!sound.value?.original);
  const audio = useEditorAudio(
    id,
    recipe,
    valid,
    computed(() => !!sound.value?.original),
  );
  const duration = computed(() => audio.duration.value || sound.value?.original?.duration || 0);
  const problems = computed(() =>
    sound.value?.original ? validateRecipe(recipe.value, duration.value) : [],
  );
  const busy = computed(() => sound.value?.status === "rendering" || sound.value?.status === "processing");
  const saving = ref(false);
  const deleting = ref(false);
  const detailsSaving = ref(false);
  const error = ref<string | null>(null);
  const detailsError = ref<string | null>(null);
  const detailsValid = computed(
    () =>
      !!effectiveDetails.value.title &&
      !!details.value.category_id &&
      (details.value.all_seasons || details.value.seasons.length > 0),
  );
  const canSave = computed(
    () =>
      recipeDirty.value &&
      valid.value &&
      !busy.value &&
      !saving.value &&
      !detailsSaving.value &&
      !deleting.value,
  );
  const previews = useEditorPreview(id, recipe, audio.stop);
  watch(audio.playing, (playing) => {
    if (playing) previews.stopPreview();
  });
  const auditionOpen = ref(false);
  let initializedId = "";
  let disposed = false;
  let deleted = false;
  let confirmInFlight: Promise<boolean> | undefined;
  watch(
    sound,
    (next) => {
      if (!next) return;
      if (initializedId !== next.id) {
        initializedId = next.id;
        recipe.value = { ...next.recipe };
        details.value = detailsOf(next);
        tagDraft.value = "";
        error.value = null;
        detailsError.value = null;
      } else {
        if (!recipeDirty.value) recipe.value = { ...next.recipe };
        if (!detailsDirty.value) details.value = detailsOf(next);
      }
      savedRecipe.value = { ...next.recipe };
      savedDetails.value = detailsOf(next);
    },
    { immediate: true },
  );
  function replaceSound(next: Sound) {
    studio.sounds.value = studio.sounds.value.map((s) => (s.id === next.id ? next : s));
  }
  function patchRecipe(patch: Partial<Recipe>) {
    const next = clampRecipe({ ...recipe.value, ...patch }, duration.value);
    // Trim edits retain the author's fades; validateRecipe reports an oversized envelope.
    recipe.value = {
      ...next,
      fade_in: patch.fade_in ?? recipe.value.fade_in,
      fade_out: patch.fade_out ?? recipe.value.fade_out,
    };
  }
  async function save() {
    if (!canSave.value) return;
    saving.value = true;
    error.value = null;
    const snapshot = { ...recipe.value };
    const soundId = id.value;
    try {
      const result = await ui.sounds.putRecipe(soundId, snapshot);
      if (disposed || id.value !== soundId) return;
      replaceSound(result.sound);
      savedRecipe.value = { ...result.sound.recipe };
      toast.push(t("editor.publishQueued"), "success");
      await Promise.all([jobs.refresh(), studio.refreshSounds()]);
    } catch (cause) {
      error.value = messageOf(cause);
    } finally {
      saving.value = false;
    }
  }
  async function saveDetails() {
    if (!detailsDirty.value || !detailsValid.value || detailsSaving.value || saving.value || deleting.value)
      return;
    detailsSaving.value = true;
    detailsError.value = null;
    const snapshot = {
      ...effectiveDetails.value,
      seasons: [...details.value.seasons],
      tags: [...effectiveDetails.value.tags],
    };
    const soundId = id.value;
    try {
      const result = await ui.sounds.update(soundId, snapshot);
      if (disposed || id.value !== soundId) return;
      if (equalDetails(effectiveDetails.value, snapshot)) {
        details.value = detailsOf(result);
        tagDraft.value = "";
      }
      savedDetails.value = detailsOf(result);
      replaceSound(result);
      toast.push(t("editor.detailsSaved"), "success");
      await studio.refreshSounds();
    } catch (cause) {
      detailsError.value = messageOf(cause);
    } finally {
      detailsSaving.value = false;
    }
  }
  function preview() {
    if (!valid.value || deleting.value) return;
    return previews.preview();
  }
  function guard(): Promise<boolean> {
    if (deleted || !dirty.value) return Promise.resolve(true);
    confirmInFlight ??= useConfirm()
      .confirm({
        title: t("editor.discardTitle"),
        message: t("editor.discardBody"),
        confirmLabel: t("editor.discard"),
        danger: true,
      })
      .finally(() => {
        confirmInFlight = undefined;
      });
    return confirmInFlight;
  }
  async function remove(close: () => Promise<unknown> | void) {
    if (deleting.value || saving.value || detailsSaving.value) return;
    if (
      !(await useConfirm().confirm({
        title: t("editor.deleteTitle", { title: sound.value?.title ?? "" }),
        message: t("editor.deleteBody"),
        confirmLabel: t("editor.delete"),
        danger: true,
      }))
    )
      return;
    deleting.value = true;
    error.value = null;
    try {
      await ui.sounds.remove(id.value);
      deleted = true;
      audio.stop();
      await close();
      await studio.refreshSounds();
      toast.push(t("editor.deleted"), "success");
    } catch (cause) {
      error.value = messageOf(cause);
    } finally {
      deleting.value = false;
    }
  }
  function revert() {
    recipe.value = { ...savedRecipe.value };
  }
  function beforeUnload(event: BeforeUnloadEvent) {
    if (dirty.value && !deleted) {
      event.preventDefault();
      event.returnValue = "";
    }
  }
  window.addEventListener("beforeunload", beforeUnload);
  onBeforeUnmount(() => {
    disposed = true;
    window.removeEventListener("beforeunload", beforeUnload);
  });
  return {
    sound,
    recipe,
    details,
    tagDraft,
    recipeDirty,
    detailsDirty,
    dirty,
    duration,
    problems,
    valid,
    audio,
    busy,
    saving,
    deleting,
    detailsSaving,
    error,
    detailsError,
    detailsValid,
    canSave,
    ...previews,
    auditionOpen,
    patchRecipe,
    save,
    saveDetails,
    preview,
    guard,
    remove,
    revert,
    loaded: studio.loaded,
  };
}
