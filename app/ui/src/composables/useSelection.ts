import { computed, nextTick, ref, watch, type Ref } from "vue";
import { messageOf, ui } from "@/api/client";
import type { BulkResult, BulkSet, Category, Sound } from "@/api/types";
import type { BulkAction } from "@/components/BulkBar.vue";
import type { LibraryDialogKind, LibraryDialogResult } from "@/components/LibraryDialog.vue";
import { useConfirm } from "@/composables/useConfirm";
import { useJobs } from "@/composables/useJobs";
import { useStudio } from "@/composables/useStudio";
import { useToast } from "@/composables/useToast";
import { useI18n } from "@/i18n";

type Options = {
  /** The sounds currently listed: "Select all" takes these, and the selection never outgrows them. */
  visible: Readonly<Ref<Sound[]>>;
  /** The category the loudness strip belongs to (target of "Level this category"). */
  activeCategory: Readonly<Ref<Category | undefined>>;
  /** Gets focus back when the bulk bar disappears and focus would otherwise be lost. */
  returnFocusTo: Readonly<Ref<HTMLElement | null>>;
};

/**
 * Multi-select and everything that acts on the selection: selection mode, the bulk request
 * lifecycle (pending, inline error, toast, refresh sounds and jobs), the delete confirmation and
 * the dialog behind Category / Seasons / Tags / Normalize / Level. Per component instance.
 */
export function useSelection({ visible, activeCategory, returnFocusTo }: Options) {
  const { t, tp } = useI18n();
  const studio = useStudio();
  const { sounds, categoryById } = studio;
  const toast = useToast();
  const { confirm } = useConfirm();

  const selectMode = ref(false);
  const selected = ref<Set<string>>(new Set());
  /** Selected sounds that filters hid (and so deselected) since the user last touched the selection. */
  const prunedCount = ref(0);

  const busy = ref(false);
  const actionError = ref<string | null>(null);
  const dialog = ref<LibraryDialogKind | null>(null);
  const levelCategoryId = ref<string | null>(null);

  const soundsById = computed(() => new Map(sounds.value.map((s) => [s.id, s])));
  const note = computed(() => (prunedCount.value > 0 ? tp("library.bulk.pruned", prunedCount.value) : null));
  const selectedTags = computed(() => [
    ...new Set([...selected.value].flatMap((id) => soundsById.value.get(id)?.tags ?? [])),
  ]);
  const dialogCount = computed(() => selected.value.size);
  const levelCategory = computed(() => (levelCategoryId.value ? categoryById(levelCategoryId.value) : undefined));

  // --- selection -----------------------------------------------------------------------------
  function toggleSelect(id: string): void {
    selectMode.value = true;
    prunedCount.value = 0;
    const next = new Set(selected.value);
    if (!next.delete(id)) next.add(id);
    selected.value = next;
  }

  function selectAll(): void {
    prunedCount.value = 0;
    selected.value = new Set(visible.value.map((s) => s.id));
  }

  function exitSelection(): void {
    selectMode.value = false;
    selected.value = new Set();
    prunedCount.value = 0;
    actionError.value = null;
    // The bar (and the Done button the user may have been on) is gone after the next render:
    // hand focus back unless the user already put it somewhere else.
    void nextTick(() => {
      const active = document.activeElement;
      if (!active || active === document.body || !active.isConnected) returnFocusTo.value?.focus({ preventScroll: true });
    });
  }

  function toggleSelectMode(): void {
    if (selectMode.value) exitSelection();
    else selectMode.value = true;
  }

  function onEscape(): void {
    if (selectMode.value && dialog.value === null) exitSelection();
  }

  // Bulk actions only ever touch what is on screen: narrowing the list narrows the selection.
  watch(visible, (list) => {
    if (!selected.value.size) return;
    const shown = new Set(list.map((s) => s.id));
    const kept: string[] = [];
    let hidden = 0;
    for (const id of selected.value) {
      if (shown.has(id)) kept.push(id);
      else if (soundsById.value.has(id)) hidden += 1; // still exists, just filtered out
    }
    if (kept.length === selected.value.size) return;
    selected.value = new Set(kept);
    prunedCount.value += hidden;
  });

  // Nothing left to act on (everything was deleted, here or elsewhere): no empty bulk bar.
  watch(
    () => sounds.value.length,
    (count) => {
      if (count === 0) exitSelection();
    },
  );

  // --- bulk actions --------------------------------------------------------------------------
  const bulkMessage = (result: BulkResult) =>
    result.queued > 0 ? tp("toast.bulk.queued", result.queued) : tp("toast.bulk.updated", result.updated);

  /** Runs one request: pending state, inline error, success toast, then fresh sounds and jobs. */
  async function perform(work: () => Promise<string>): Promise<boolean> {
    if (busy.value) return false;
    busy.value = true;
    actionError.value = null;
    try {
      toast.push(await work(), "success");
      // Renders may have been queued: refresh both lists (neither refresh throws).
      await Promise.all([studio.refreshSounds(), useJobs().refresh()]);
      return true;
    } catch (cause) {
      actionError.value = messageOf(cause);
      return false;
    } finally {
      busy.value = false;
    }
  }

  const bulk = (set: BulkSet) =>
    perform(async () => bulkMessage(await ui.sounds.bulk({ ids: [...selected.value], set })));

  async function onBulkAction(action: BulkAction): Promise<void> {
    actionError.value = null;
    prunedCount.value = 0;
    switch (action) {
      case "enable":
      case "disable":
        await bulk({ enabled: action === "enable" });
        return;
      case "delete": {
        const ids = [...selected.value];
        const confirmed = await confirm({
          title: tp("library.confirm.delete.title", ids.length),
          message: t("library.confirm.delete.message"),
          confirmLabel: t("common.delete"),
          danger: true,
        });
        if (!confirmed) return;
        const done = await perform(async () => tp("toast.bulk.deleted", (await ui.sounds.bulkDelete(ids)).deleted));
        if (done) exitSelection();
        return;
      }
      default:
        dialog.value = action;
    }
  }

  function openLevel(): void {
    if (!activeCategory.value) return;
    levelCategoryId.value = activeCategory.value.id;
    actionError.value = null;
    dialog.value = "level";
  }

  function closeDialog(): void {
    if (busy.value) return;
    dialog.value = null;
    actionError.value = null;
  }

  async function onDialogSubmit(result: LibraryDialogResult): Promise<void> {
    let done: boolean;
    switch (result.kind) {
      case "category":
        done = await bulk({ category_id: result.categoryId });
        break;
      case "seasons":
        done = await bulk({ seasons: result.seasons, all_seasons: result.allSeasons });
        break;
      case "tags":
        done = await bulk({
          ...(result.add.length ? { add_tags: result.add } : {}),
          ...(result.remove.length ? { remove_tags: result.remove } : {}),
        });
        break;
      case "normalize":
        done = await bulk({ profile_id: result.profileId });
        break;
      case "level": {
        const categoryId = levelCategoryId.value;
        if (!categoryId) return;
        done = await perform(async () =>
          tp("toast.bulk.queued", (await ui.profiles.apply(result.profileId, { category_id: categoryId })).queued),
        );
        break;
      }
    }
    if (done) dialog.value = null;
  }

  return {
    selectMode,
    selected,
    note,
    busy,
    actionError,
    dialog,
    dialogCount,
    selectedTags,
    levelCategory,
    toggleSelect,
    selectAll,
    exitSelection,
    toggleSelectMode,
    onEscape,
    onBulkAction,
    openLevel,
    closeDialog,
    onDialogSubmit,
  };
}
