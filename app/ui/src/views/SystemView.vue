<script setup lang="ts">
import { nextTick, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { useStudio } from "@/composables/useStudio";
import { useI18n } from "@/i18n";
import ConnectionPanel from "@/components/ConnectionPanel.vue";
import FilesPanel from "@/components/FilesPanel.vue";
import MediaUrlPanel from "@/components/MediaUrlPanel.vue";
import ImportPanel from "@/components/ImportPanel.vue";
import SpeakersPanel from "@/components/SpeakersPanel.vue";
import LimitsPanel from "@/components/LimitsPanel.vue";
import StoragePanel from "@/components/StoragePanel.vue";
import JobsPanel from "@/components/JobsPanel.vue";
const { t } = useI18n();
const { state, loaded, loading, error, refresh } = useStudio();
const route = useRoute();
const importSection = ref<HTMLElement | null>(null);
watch(
  [() => loaded.value && !!state.value, () => route.query.section, () => route.hash],
  async ([ready, section, hash]) => {
    if (!ready || (section !== "import" && hash !== "#import")) return;
    await nextTick();
    importSection.value?.scrollIntoView({ block: "start", behavior: "auto" });
    importSection.value?.focus({ preventScroll: true });
  },
  { immediate: true, flush: "post" },
);
</script>
<template>
  <section class="min-w-0 space-y-4" aria-labelledby="system-heading">
    <h2 id="system-heading" class="text-xl font-semibold">{{ t("system.heading") }}</h2>
    <div v-if="!loaded || !state" class="panel">
      <p v-if="loading" role="status">{{ t("common.loading") }}</p>
      <template v-else
        ><p v-if="error" role="alert" class="break-words text-danger">{{ error }}</p>
        <button class="btn-primary min-h-11! mt-3" @click="refresh">{{ t("common.retry") }}</button></template
      >
    </div>
    <div v-else class="grid min-w-0 items-start gap-4 lg:grid-cols-2">
      <div class="min-w-0 space-y-4">
        <ConnectionPanel :state="state" />
        <FilesPanel :www="state.www" />
        <MediaUrlPanel />
        <LimitsPanel />
      </div>
      <div class="min-w-0 space-y-4">
        <div id="import" ref="importSection" tabindex="-1" class="min-w-0 scroll-mt-20"><ImportPanel /></div>
        <SpeakersPanel />
        <StoragePanel :storage="state.storage" />
        <JobsPanel />
      </div>
    </div>
    <p v-if="loaded && error" role="alert" class="text-sm break-words text-danger">{{ error }}</p>
  </section>
</template>
