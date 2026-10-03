<script setup lang="ts">
import { mdiShapeOutline } from "@mdi/js";
import EmptyState from "@/components/EmptyState.vue";
import { useI18n } from "@/i18n";

const { t } = useI18n();
</script>

<template>
  <section aria-labelledby="organize-heading">
    <h2 id="organize-heading" class="mb-4 text-lg font-semibold">{{ t("organize.heading") }}</h2>
    <EmptyState
      :icon="mdiShapeOutline"
      :title="t('organize.empty.title')"
      :description="t('organize.empty.body')"
    />
  </section>
</template>
