<script lang="ts">
export type LibraryDialogKind = "category" | "seasons" | "tags" | "normalize" | "level";

/** What the user chose, ready for the parent to turn into an API call. */
export type LibraryDialogResult =
  | { kind: "category"; categoryId: string }
  | { kind: "seasons"; seasons: string[]; allSeasons: boolean }
  | { kind: "tags"; add: string[]; remove: string[] }
  | { kind: "normalize"; profileId: string | null }
  | { kind: "level"; profileId: string };
</script>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { mdiAlertCircleOutline, mdiLoading } from "@mdi/js";
import Icon from "@/components/Icon.vue";
import ProfilePicker from "@/components/ProfilePicker.vue";
import SeasonPicker, { type SeasonSelection } from "@/components/SeasonPicker.vue";
import Sheet from "@/components/Sheet.vue";
import TagEditor from "@/components/TagEditor.vue";
import { useStudio } from "@/composables/useStudio";
import { useI18n, type MessageKey } from "@/i18n";
import { addTag } from "@/lib/tags";

// The one dialog behind the bulk bar's Category / Seasons / Tags / Normalize actions and the
// loudness strip's "Level this category". It owns the form state and resets it every time it
// opens; running the request (pending/error) stays with the parent.
const props = defineProps<{
  kind: LibraryDialogKind | null;
  /** Sounds the change applies to. */
  count: number;
  pending: boolean;
  error: string | null;
  /** `level` only: the category being leveled and the profile to preselect. */
  categoryName?: string;
  defaultProfileId?: string | null;
  /** Existing tags to suggest when adding. */
  allTags: string[];
  /** Tags that are on the selected sounds (suggested when removing). */
  selectedTags: string[];
}>();
const emit = defineEmits<{ close: []; submit: [result: LibraryDialogResult] }>();

const { t, tp } = useI18n();
const { categories } = useStudio();

const categoryId = ref("");
const seasonChoice = ref<SeasonSelection>({ seasons: [], all_seasons: false });
const addTags = ref<string[]>([]);
const addDraft = ref("");
const removeTags = ref<string[]>([]);
const removeDraft = ref("");
const profile = ref<string | null | undefined>(undefined);

// What the dialog shows is a snapshot taken when it opens. The parent clears `kind` (and may
// change the count, category...) the moment it closes, while the Sheet is still fading out: the
// title and form must not flicker or switch to empty into that fade.
const shown = ref({
  kind: props.kind,
  count: props.count,
  categoryName: props.categoryName,
});

watch(
  () => props.kind,
  (kind) => {
    if (kind === null) return;
    shown.value = { kind, count: props.count, categoryName: props.categoryName };
    categoryId.value = "";
    seasonChoice.value = { seasons: [], all_seasons: false };
    addTags.value = [];
    addDraft.value = "";
    removeTags.value = [];
    removeDraft.value = "";
    profile.value = kind === "level" ? (props.defaultProfileId ?? undefined) : undefined;
  },
  { immediate: true },
);

/** The kind being shown: the last one opened, even while the Sheet fades out. */
const current = computed(() => shown.value.kind);

const titles: Record<LibraryDialogKind, MessageKey> = {
  category: "library.dialog.category.title",
  seasons: "library.dialog.seasons.title",
  tags: "library.dialog.tags.title",
  normalize: "library.dialog.normalize.title",
  level: "library.dialog.level.title",
};
const title = computed(() => (current.value ? t(titles[current.value], { category: shown.value.categoryName ?? "" }) : ""));

// Text typed in a tag field but never confirmed counts as intended: Apply must not drop it.
const effectiveAdd = computed(() => addTag(addTags.value, addDraft.value));
const effectiveRemove = computed(() => addTag(removeTags.value, removeDraft.value));
const tagConflict = computed(() => effectiveAdd.value.some((tag) => effectiveRemove.value.includes(tag)));
const seasonsValid = computed(() => seasonChoice.value.all_seasons || seasonChoice.value.seasons.length > 0);

const valid = computed(() => {
  switch (current.value) {
    case "category":
      return categoryId.value !== "";
    case "seasons":
      return seasonsValid.value;
    case "tags":
      return (effectiveAdd.value.length > 0 || effectiveRemove.value.length > 0) && !tagConflict.value;
    case "normalize":
      return profile.value !== undefined;
    case "level":
      return typeof profile.value === "string";
    default:
      return false;
  }
});

function submit(): void {
  if (props.kind === null || !valid.value || props.pending) return;
  switch (current.value) {
    case "category":
      emit("submit", { kind: "category", categoryId: categoryId.value });
      break;
    case "seasons":
      emit("submit", {
        kind: "seasons",
        seasons: seasonChoice.value.seasons,
        allSeasons: seasonChoice.value.all_seasons,
      });
      break;
    case "tags":
      emit("submit", { kind: "tags", add: effectiveAdd.value, remove: effectiveRemove.value });
      break;
    case "normalize":
      emit("submit", { kind: "normalize", profileId: profile.value ?? null });
      break;
    case "level":
      if (typeof profile.value === "string") emit("submit", { kind: "level", profileId: profile.value });
      break;
  }
}
</script>

<template>
  <Sheet :open="props.kind !== null" :title="title" @close="emit('close')">
    <div v-if="current" class="space-y-4">
      <p v-if="current === 'level'" class="text-sm text-muted">{{ t("library.dialog.level.hint") }}</p>
      <p v-else class="text-sm text-muted">{{ tp("library.dialog.scope", shown.count) }}</p>

      <div v-if="current === 'category'">
        <label for="library-dialog-category" class="mb-1.5 block text-sm font-medium">
          {{ t("library.dialog.category.label") }}
        </label>
        <select id="library-dialog-category" v-model="categoryId" data-test="dialog-category" class="field">
          <option value="" disabled>{{ t("library.dialog.category.placeholder") }}</option>
          <option v-for="category in categories" :key="category.id" :value="category.id">{{ category.name }}</option>
        </select>
      </div>

      <template v-else-if="current === 'seasons'">
        <SeasonPicker v-model="seasonChoice" />
        <p v-if="!seasonsValid" class="text-sm text-warn">{{ t("library.dialog.seasons.invalid") }}</p>
      </template>

      <template v-else-if="current === 'tags'">
        <TagEditor
          v-model="addTags"
          v-model:draft="addDraft"
          :suggestions="allTags"
          :label="t('library.dialog.tags.add')"
        />
        <TagEditor
          v-model="removeTags"
          v-model:draft="removeDraft"
          :suggestions="selectedTags"
          :label="t('library.dialog.tags.remove')"
        />
        <p v-if="tagConflict" role="alert" class="text-sm text-danger">{{ t("library.dialog.tags.conflict") }}</p>
      </template>

      <template v-else-if="current === 'normalize'">
        <p class="text-sm text-muted">{{ t("library.dialog.normalize.hint") }}</p>
        <ProfilePicker v-model="profile" allow-none />
      </template>

      <ProfilePicker v-else-if="current === 'level'" v-model="profile" />
    </div>

    <template #footer>
      <p
        v-if="error"
        role="alert"
        class="mb-3 flex items-start gap-2 rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-sm break-words"
      >
        <Icon :path="mdiAlertCircleOutline" :size="18" class="mt-0.5 shrink-0 text-danger" />
        <span class="min-w-0 flex-1">{{ error }}</span>
      </p>
      <div class="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <button data-test="cancel" type="button" class="btn" :disabled="pending" @click="emit('close')">
          {{ t("common.cancel") }}
        </button>
        <button
          data-test="apply"
          type="button"
          class="btn-primary"
          :disabled="!valid || pending"
          :aria-busy="pending ? 'true' : undefined"
          @click="submit"
        >
          <Icon v-if="pending" :path="mdiLoading" class="animate-spin" />
          {{ current === "level" ? t("library.dialog.level.apply") : t("common.apply") }}
        </button>
      </div>
    </template>
  </Sheet>
</template>
