<script setup lang="ts">
import { mdiCog } from "@mdi/js";
import EmptyState from "@/components/EmptyState.vue";
import { useI18n } from "@/i18n";

const { t } = useI18n();
</script>

<template>
  <section aria-labelledby="system-heading">
    <h2 id="system-heading" class="mb-4 text-lg font-semibold">{{ t("system.heading") }}</h2>
    <EmptyState :icon="mdiCog" :title="t('system.empty.title')" :description="t('system.empty.body')" />
  </section>
</template>
