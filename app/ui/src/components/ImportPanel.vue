<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ui, messageOf } from "@/api/client";
import { useStudio } from "@/composables/useStudio";
import { useJobs } from "@/composables/useJobs";
import { useToast } from "@/composables/useToast";
import { useI18n } from "@/i18n";
import { CATEGORY_DEFAULT } from "@/lib/profiles";
import { addTag } from "@/lib/tags";
import ImportBrowser from "./ImportBrowser.vue";
import SeasonPicker, { type SeasonSelection } from "./SeasonPicker.vue";
import TagEditor from "./TagEditor.vue";
import ProfilePicker from "./ProfilePicker.vue";
const { t, tp } = useI18n();
const studio = useStudio();
const { categories, sounds } = studio;
const browser = ref<InstanceType<typeof ImportBrowser> | null>(null);
const category = ref("");
watch(
  categories,
  (list) => {
    if (!list.some((c) => c.id === category.value)) category.value = list[0]?.id ?? "";
  },
  { immediate: true },
);
const seasons = ref<SeasonSelection>({ seasons: ["regular"], all_seasons: false });
const tags = ref<string[]>([]);
const draft = ref("");
const profile = ref<string | null>(CATEGORY_DEFAULT);
const suggestions = computed(() => [...new Set(sounds.value.flatMap((s) => s.tags))].sort());
const valid = computed(
  () => !!category.value && (seasons.value.all_seasons || !!seasons.value.seasons.length),
);
const pending = ref(false);
const error = ref<string | null>(null);
async function run(paths: string[]) {
  if (!valid.value || pending.value || !paths.length) return;
  pending.value = true;
  error.value = null;
  tags.value = addTag(tags.value, draft.value);
  draft.value = "";
  const defaults = { paths, category_id: category.value, ...seasons.value, tags: [...tags.value] };
  try {
    const result = await ui.importer.run(
      profile.value === CATEGORY_DEFAULT ? defaults : { ...defaults, profile_id: profile.value },
    );
    useToast().push(tp("system.imported", result.sounds.length), "success");
    await Promise.all([useJobs().refresh(), studio.refreshSounds()]);
    browser.value?.clearSelection();
  } catch (cause) {
    error.value = messageOf(cause);
  } finally {
    pending.value = false;
  }
}
</script>
<template>
  <section class="panel min-w-0 space-y-4" aria-labelledby="import-heading">
    <h3 id="import-heading" class="font-semibold">{{ t("system.import") }}</h3>
    <p class="text-sm text-muted">{{ t("system.importHint") }}</p>
    <ImportBrowser ref="browser" :pending="pending" :can-import="valid" @import="run">
      <fieldset class="min-w-0 space-y-4 border-t border-line pt-4" :disabled="pending">
        <legend class="pt-4 text-sm font-medium">{{ t("upload.defaults") }}</legend>
        <div>
          <label for="import-category" class="mb-1 block text-sm">{{ t("organize.categories") }}</label>
          <select id="import-category" v-model="category" class="field">
            <option value="" disabled>{{ t("library.dialog.category.placeholder") }}</option>
            <option v-for="c in categories" :key="c.id" :value="c.id">{{ c.name }}</option>
          </select>
        </div>
        <SeasonPicker v-model="seasons" />
        <TagEditor v-model="tags" v-model:draft="draft" :suggestions="suggestions" />
        <ProfilePicker v-model="profile" allow-none allow-category-default />
        <p v-if="!valid" role="alert" class="text-sm text-warn">{{ t("upload.invalidDefaults") }}</p>
        <p v-if="error" role="alert" class="text-sm break-words text-danger">{{ error }}</p>
      </fieldset>
    </ImportBrowser>
  </section>
</template>
