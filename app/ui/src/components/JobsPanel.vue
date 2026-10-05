<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import { mdiProgressCheck } from "@mdi/js";
import type { Job } from "@/api/types";
import { useJobs } from "@/composables/useJobs";
import { useI18n } from "@/i18n";
import { formatDateTime, formatDuration } from "@/lib/format";
import StatusPill from "./StatusPill.vue";
import EmptyState from "./EmptyState.vue";
const { t, locale } = useI18n();
const { jobs, refresh, error } = useJobs();
const pending = ref(false);
const now = ref(Date.now());
let timer: ReturnType<typeof setInterval>;
const status = (job: Job) =>
  (({ queued: "processing", running: "rendering", done: "ready", failed: "failed" }) as const)[job.status];
const percent = (job: Job) => Math.round(Math.min(1, Math.max(0, job.progress)) * 100);
function duration(job: Job) {
  if (!job.started_at) return null;
  return formatDuration(
    Math.max(
      0,
      ((job.finished_at ? Date.parse(job.finished_at) : now.value) - Date.parse(job.started_at)) / 1000,
    ),
  );
}
async function reload() {
  if (pending.value) return;
  pending.value = true;
  try {
    await refresh();
  } finally {
    pending.value = false;
  }
}
onMounted(() => {
  void reload();
  timer = setInterval(() => {
    now.value = Date.now();
  }, 1000);
});
onBeforeUnmount(() => clearInterval(timer));
</script>
<template>
  <section class="panel min-w-0 space-y-4" aria-labelledby="system-jobs-heading" :aria-busy="pending">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <h3 id="system-jobs-heading" class="font-semibold">{{ t("jobs.title") }}</h3>
      <button class="btn min-h-11!" :disabled="pending" @click="reload">
        {{ pending ? t("common.loading") : t("system.refresh") }}
      </button>
    </div>
    <p v-if="error" role="alert" class="text-sm break-words text-danger">{{ error }}</p>
    <p v-if="pending && !jobs.length" role="status" class="text-sm text-muted">{{ t("common.loading") }}</p>
    <EmptyState
      v-else-if="!jobs.length"
      :icon="mdiProgressCheck"
      :title="t('jobs.empty')"
      :description="t('system.jobsEmptyHint')"
    >
      <RouterLink :to="{ name: 'upload' }" class="btn-primary min-h-11!">{{
        t("upload.heading")
      }}</RouterLink>
    </EmptyState>
    <ul v-else class="max-h-[32rem] space-y-3 overflow-y-auto overscroll-contain">
      <li v-for="job in jobs" :key="job.id" class="space-y-2 rounded-lg border border-line bg-ground p-3">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <p class="min-w-0 break-words text-sm font-medium">{{ job.sound_title }}</p>
          <StatusPill :status="status(job)" :label="t(`jobs.status.${job.status}`)" />
        </div>
        <p class="text-xs text-muted">
          {{ t(`jobs.kind.${job.kind}`) }} · {{ formatDateTime(job.created_at, locale) }}
        </p>
        <div
          v-if="job.status === 'running' || job.status === 'queued'"
          role="progressbar"
          :aria-label="t('jobs.progress', { title: job.sound_title, n: percent(job) })"
          :aria-valuenow="percent(job)"
          aria-valuemin="0"
          aria-valuemax="100"
          class="h-2 overflow-hidden rounded-full bg-hover"
        >
          <div class="h-full bg-accent" :style="{ width: `${percent(job)}%` }" />
        </div>
        <p v-if="duration(job)" class="text-xs text-muted tabular-nums">
          {{ t("system.jobDuration", { duration: duration(job)! }) }}
        </p>
        <p v-if="job.error" class="text-sm break-words text-danger">{{ job.error }}</p>
      </li>
    </ul>
  </section>
</template>
