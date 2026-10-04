<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { mdiUpload } from "@mdi/js";
import type { Category } from "@/api/types";
import CategoryForm from "@/components/CategoryForm.vue";
import DropZone from "@/components/DropZone.vue";
import EmptyState from "@/components/EmptyState.vue";
import SeasonPicker, { type SeasonSelection } from "@/components/SeasonPicker.vue";
import TagEditor from "@/components/TagEditor.vue";
import ProfilePicker from "@/components/ProfilePicker.vue";
import { CATEGORY_DEFAULT } from "@/lib/profiles";
import UploadRow from "@/components/UploadRow.vue";
import Sheet from "@/components/Sheet.vue";
import { useUpload } from "@/composables/useUpload";
import { useStudio } from "@/composables/useStudio";
import { useI18n } from "@/i18n";
import { addTag } from "@/lib/tags";
const { t, tp } = useI18n();
const { categories, sounds, seasons: availableSeasons, profiles, loaded, loading, refresh, error } = useStudio();
const { items, busy, add, start, remove, clearDone, retry } = useUpload();
const dropZone = ref<InstanceType<typeof DropZone> | null>(null);
const category = ref("");
watch(
  categories,
  (values) => {
    if (!values.some((c) => c.id === category.value)) category.value = values[0]?.id ?? "";
  },
  { immediate: true },
);
const seasons = ref<SeasonSelection>({
  seasons: ["regular"],
  all_seasons: false,
});
const tags = ref<string[]>([]);
const draft = ref("");
const profile = ref<string | null>(CATEGORY_DEFAULT);
const suggestions = computed(() => [...new Set(sounds.value.flatMap((s) => s.tags))].sort());
const defaultsSummary = computed(() => {
  const categoryName = categories.value.find((c) => c.id === category.value)?.name
    ?? t("library.dialog.category.placeholder");
  const seasonNames = seasons.value.all_seasons
    ? t("library.item.allSeasons")
    : seasons.value.seasons.map((id) => availableSeasons.value.find((s) => s.id === id)?.name ?? id).join(", ")
      || t("common.none");
  const profileName = profile.value === CATEGORY_DEFAULT
    ? t("picker.profile.categoryDefault")
    : profile.value === null
      ? t("picker.profile.none")
      : profiles.value.find((p) => p.id === profile.value)?.name ?? "";
  return [categoryName, seasonNames, profileName].join(" · ");
});
const bar = ref<HTMLElement | null>(null);
const barHeight = ref(160);
watch(
  bar,
  (element, _, onCleanup) => {
    if (!element) return;
    const measure = () => { barHeight.value = element.getBoundingClientRect().height; };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    onCleanup(() => observer.disconnect());
  },
  { flush: "post" },
);
const defaultsOpen = ref(false);
const newCategory = ref(false);
const categoryBusy = ref(false);
const showBar = computed(() => busy.value || items.value.some((item) => ["pending", "uploading", "processing"].includes(item.status)));
const count = computed(() => items.value.filter((i) => i.status === "pending").length);
const valid = computed(() => !!category.value && (seasons.value.all_seasons || seasons.value.seasons.length > 0));
function upload(): void {
  if (!valid.value || busy.value || !loaded.value) return;
  tags.value = addTag(tags.value, draft.value);
  draft.value = "";
  const defaults = {
    category_id: category.value,
    ...seasons.value,
    tags: tags.value,
  };
  void start(profile.value === CATEGORY_DEFAULT ? defaults : { ...defaults, profile_id: profile.value });
}
function created(value: Category): void {
  category.value = value.id;
  newCategory.value = false;
}
</script>
<template>
  <section
    class="min-w-0 space-y-4"
    :style="{ paddingBottom: loaded && showBar ? `${barHeight + 24}px` : undefined }"
    aria-labelledby="upload-heading"
  >
    <h2 id="upload-heading" class="text-xl font-semibold">
      {{ t("upload.heading") }}
    </h2>
    <div v-if="!loaded" class="panel">
      <p v-if="loading" role="status">{{ t("common.loading") }}</p>
      <template v-else
        ><p v-if="error" role="alert" class="break-words text-danger">
          {{ error }}
        </p>
        <button class="btn-primary mt-3" @click="refresh">
          {{ t("common.retry") }}
        </button></template
      >
    </div>
    <div v-else class="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]">
      <aside class="min-w-0">
        <div class="panel lg:sticky lg:top-20">
          <button
            type="button"
            class="flex min-h-11 w-full items-center justify-between gap-2 text-left font-medium lg:hidden"
            :aria-expanded="defaultsOpen"
            aria-controls="upload-defaults"
            @click="defaultsOpen = !defaultsOpen"
          >
            <span class="min-w-0">
              <span class="block">{{ t("upload.defaults") }}</span>
              <span
                v-if="!defaultsOpen"
                data-test="defaults-summary"
                class="block truncate text-xs font-normal text-muted"
                :title="defaultsSummary"
              >{{ defaultsSummary }}</span>
            </span>
            <span aria-hidden="true">{{ defaultsOpen ? "−" : "+" }}</span>
          </button>
          <h3 class="mb-2 hidden font-medium lg:block">
            {{ t("upload.defaults") }}
          </h3>
          <div id="upload-defaults" class="space-y-4" :class="defaultsOpen ? 'block' : 'hidden lg:block'">
            <p class="text-sm text-muted">{{ t("upload.defaults.hint") }}</p>
            <div>
              <label for="upload-category" class="mb-1.5 block text-sm font-medium">{{
                t("organize.categories")
              }}</label
              ><select id="upload-category" v-model="category" class="field">
                <option value="" disabled>
                  {{ t("library.dialog.category.placeholder") }}
                </option>
                <option v-for="c in categories" :key="c.id" :value="c.id">
                  {{ c.name }}
                </option></select
              ><button type="button" class="btn-ghost mt-1 w-full" @click="newCategory = true">
                {{ t("organize.newCategory") }}
              </button>
            </div>
            <SeasonPicker v-model="seasons" />
            <TagEditor v-model="tags" v-model:draft="draft" :suggestions="suggestions" />
            <ProfilePicker v-model="profile" allow-none allow-category-default />
          </div>
        </div>
      </aside>
      <div class="min-w-0 space-y-4">
        <DropZone ref="dropZone" @files="add" />
        <div v-if="items.length" class="space-y-3">
          <div class="flex justify-end">
            <button
              type="button"
              class="btn-ghost"
              :disabled="!items.some((i) => i.status === 'done')"
              @click="clearDone"
            >
              {{ t("upload.clear") }}
            </button>
          </div>
          <ul class="space-y-2">
            <UploadRow v-for="item in items" :key="item.id" :item="item" @remove="remove" @retry="retry" />
          </ul>
        </div>
        <EmptyState v-else :icon="mdiUpload" :title="t('upload.empty.title')" :description="t('upload.empty.body')">
          <button type="button" class="btn-primary" @click="dropZone?.chooseFiles()">{{ t("upload.choose") }}</button>
        </EmptyState>
      </div>
    </div>
    <div
      v-if="loaded && showBar"
      ref="bar"
      data-test="upload-bar"
      class="fixed inset-x-0 bottom-[var(--tabbar-h)] z-30 border-t border-line bg-surface/95 px-4 pt-3 pb-3 md:pb-[max(0.75rem,env(safe-area-inset-bottom))] backdrop-blur md:left-60 md:px-6"
    >
      <p v-if="!valid && count" role="alert" class="mx-auto mb-2 max-w-7xl text-sm text-warn">
        {{ t("upload.invalidDefaults") }}
      </p>
      <button
        type="button"
        class="btn-primary mx-auto flex w-full max-w-7xl"
        :disabled="busy || !count || !valid"
        @click="upload"
      >
        {{ busy ? t("upload.active") : tp("upload.start", count) }}
      </button>
    </div>
    <Sheet :open="newCategory" :title="t('organize.newCategory')" @close="!categoryBusy && (newCategory = false)"
      ><CategoryForm v-if="newCategory" @busy="categoryBusy = $event" @saved="created"
    /></Sheet>
  </section>
</template>
