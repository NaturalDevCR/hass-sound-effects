import { computed, ref } from "vue";
import { ui } from "@/api/client";
import type { Job } from "@/api/types";
import { translate } from "@/i18n";
import { useStudio } from "./useStudio";
import { useToast } from "./useToast";

const ACTIVE_POLL_MS = 1500;
const IDLE_POLL_MS = 10_000;

const jobs = ref<Job[]>([]);
const active = computed(() => jobs.value.filter((j) => j.status === "queued" || j.status === "running"));

let running = false;
let timer: ReturnType<typeof setTimeout> | undefined;
let inflight: Promise<void> | null = null;
/** Finished job ids we already reacted to. Filled silently on the first load so history is not replayed. */
const handled = new Set<string>();
let primed = false;

function describeFailure(job: Job): string {
  const reason = job.error ?? translate("error.unknown");
  const params = { title: job.sound_title, reason };
  switch (job.kind) {
    case "import":
      return translate("toast.job.importFailed", params);
    case "preview":
      return translate("toast.job.previewFailed", params);
    default:
      return translate("toast.job.publishFailed", params);
  }
}

function announceFinished(finished: Job[]): void {
  const { push } = useToast();
  for (const job of finished) {
    if (job.status === "failed") {
      push(describeFailure(job), "error");
    } else if (job.kind === "import") {
      push(translate("toast.job.import", { title: job.sound_title }), "success");
    } else if (job.kind === "publish") {
      push(translate("toast.job.publish", { title: job.sound_title }), "success");
    }
  }
}

function react(list: Job[]): void {
  const finished = list.filter((j) => j.status === "done" || j.status === "failed");
  const fresh = finished.filter((j) => !handled.has(j.id));
  for (const job of finished) handled.add(job.id);
  if (!primed) {
    primed = true;
    return;
  }
  if (fresh.length) {
    announceFinished(fresh);
    void useStudio().refreshSounds();
  }
}

function poll(): Promise<void> {
  if (inflight) return inflight;
  const run = (async () => {
    try {
      const list = await ui.jobs();
      jobs.value = list;
      react(list);
    } catch {
      // keep the last known list; the next tick retries
    }
  })().finally(() => {
    inflight = null;
  });
  inflight = run;
  return run;
}

const isHidden = () => typeof document !== "undefined" && document.hidden;

function schedule(): void {
  if (!running) return;
  clearTimeout(timer);
  timer = setTimeout(async () => {
    // A hidden tab (or a backgrounded Home Assistant app) skips the request; it catches up on return.
    if (!isHidden()) await poll();
    schedule();
  }, active.value.length ? ACTIVE_POLL_MS : IDLE_POLL_MS);
}

/** Polls right away (e.g. after queueing a render) and re-arms the timer. */
async function refresh(): Promise<void> {
  await poll();
  schedule();
}

function onVisibilityChange(): void {
  if (running && !isHidden()) void refresh();
}

function start(): void {
  if (running) return;
  running = true;
  document.addEventListener("visibilitychange", onVisibilityChange);
  void refresh();
}

function stop(): void {
  running = false;
  clearTimeout(timer);
  timer = undefined;
  document.removeEventListener("visibilitychange", onVisibilityChange);
}

/**
 * Shared job list. Polls every 1.5 s while anything is queued or running and every
 * 10 s otherwise; a job that finishes triggers a sound refresh and a toast.
 */
export function useJobs() {
  return { jobs, active, start, stop, refresh };
}
