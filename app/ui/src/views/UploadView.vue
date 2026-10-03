<script setup lang="ts">
import { mdiUpload } from "@mdi/js";
import EmptyState from "@/components/EmptyState.vue";
import { useI18n } from "@/i18n";

const { t } = useI18n();
</script>

<template>
  <section aria-labelledby="upload-heading">
    <h2 id="upload-heading" class="mb-4 text-lg font-semibold">{{ t("upload.heading") }}</h2>
    <EmptyState :icon="mdiUpload" :title="t('upload.empty.title')" :description="t('upload.empty.body')" />
  </section>
</template>
