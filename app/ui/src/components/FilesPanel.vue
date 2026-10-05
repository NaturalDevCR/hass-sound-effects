<script setup lang="ts">
import type { State } from "@/api/types";
import { useI18n } from "@/i18n";
defineProps<{ www: State["www"] }>();
const { t } = useI18n();
const booleanText = (value: boolean | null) =>
  t(value === null ? "system.unknown" : value ? "system.yes" : "system.no");
</script>
<template>
  <section class="panel min-w-0 space-y-4" aria-labelledby="files-heading">
    <h3 id="files-heading" class="font-semibold">{{ t("system.files") }}</h3>
    <p class="font-mono text-sm">/config/www</p>
    <dl class="space-y-2 text-sm">
      <div class="flex flex-wrap justify-between gap-2">
        <dt class="text-muted">{{ t("system.exists") }}</dt>
        <dd>{{ booleanText(www.exists) }}</dd>
      </div>
      <div class="flex flex-wrap justify-between gap-2">
        <dt class="text-muted">{{ t("system.served") }}</dt>
        <dd>{{ booleanText(www.served) }}</dd>
      </div>
      <div class="flex flex-wrap justify-between gap-2">
        <dt class="text-muted">{{ t("system.created") }}</dt>
        <dd>{{ booleanText(www.created_by_app) }}</dd>
      </div>
    </dl>
    <p
      v-if="www.served === false"
      role="alert"
      class="rounded-lg border border-warn/40 bg-warn/10 p-3 text-sm text-warn"
    >
      {{ t("system.restart") }}
    </p>
  </section>
</template>
