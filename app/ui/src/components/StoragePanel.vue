<script setup lang="ts">
import { computed } from "vue";
import type { State } from "@/api/types";
import { formatBytes } from "@/lib/format";
import { useI18n } from "@/i18n";
const props = defineProps<{ storage: State["storage"] }>();
const { t } = useI18n();
const rows = computed(() => [
  { key: "originals" as const, bytes: props.storage.originals_bytes, color: "bg-accent" },
  { key: "published" as const, bytes: props.storage.published_bytes, color: "bg-ok" },
  { key: "previews" as const, bytes: props.storage.previews_bytes, color: "bg-warn" },
]);
const total = computed(() => rows.value.reduce((sum, row) => sum + row.bytes, 0));
</script>
<template>
  <section class="panel min-w-0 space-y-4" aria-labelledby="storage-heading">
    <h3 id="storage-heading" class="font-semibold">{{ t("system.storage") }}</h3>
    <p class="text-sm font-medium tabular-nums">{{ t("system.total", { size: formatBytes(total) }) }}</p>
    <div v-if="total" aria-hidden="true" class="flex h-3 overflow-hidden rounded-full bg-hover">
      <div
        v-for="row in rows"
        :key="row.key"
        :class="row.color"
        :style="{ width: `${(row.bytes / total) * 100}%` }"
      />
    </div>
    <dl class="space-y-3 text-sm">
      <div v-for="row in rows" :key="row.key" class="flex flex-wrap justify-between gap-2">
        <dt class="flex items-center gap-2">
          <span aria-hidden="true" class="size-2.5 rounded-full" :class="row.color" />{{
            t(`system.${row.key}`)
          }}
        </dt>
        <dd class="tabular-nums">{{ formatBytes(row.bytes) }}</dd>
      </div>
    </dl>
    <div v-if="!total" class="space-y-3">
      <p class="text-sm text-muted">{{ t("system.storageEmpty") }}</p>
      <RouterLink :to="{ name: 'upload' }" class="btn-primary min-h-11!">{{ t("upload.heading") }}</RouterLink>
    </div>
  </section>
</template>
