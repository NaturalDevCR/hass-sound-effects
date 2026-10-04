import { ref, watch, type Ref } from "vue";
import { messageOf, ui } from "@/api/client";
import type { UploadComplete } from "@/api/types";
import { translate } from "@/i18n";
import { useStudio } from "./useStudio";
import { useJobs } from "./useJobs";

export type UploadItem = {
  id: string;
  file: File;
  status: "pending" | "uploading" | "processing" | "done" | "error";
  progress: number;
  error: string | null;
  soundId: string | null;
};
export type UploadDefaults = Omit<UploadComplete, "title">;
export const UPLOAD_EXTENSIONS = [".mp3", ".wav", ".flac", ".ogg", ".opus", ".m4a", ".aac", ".webm", ".mp4", ".mov"];
const items: Ref<UploadItem[]> = ref([]);
const busy = ref(false);
const studio = useStudio();
let run: Promise<void> | null = null;
let pollTimer: ReturnType<typeof setTimeout> | undefined;

function validation(file: File): string | null {
  if (!UPLOAD_EXTENSIONS.some((ext) => file.name.toLowerCase().endsWith(ext))) return translate("upload.unsupported");
  const limit = studio.state.value?.settings.max_upload_mb;
  if (limit !== undefined && file.size > limit * 1024 * 1024) return translate("upload.oversized", { n: limit });
  return file.size === 0 ? translate("upload.emptyFile") : null;
}

// Module state survives route changes. Only processing items need an extra sound poll:
// jobs may have finished before the job tray's first request was primed.
function schedule(): void {
  clearTimeout(pollTimer);
  if (!items.value.some((item) => item.status === "processing")) return;
  pollTimer = setTimeout(async () => {
    if (!document.hidden) await studio.refreshSounds();
    schedule();
  }, 1500);
}
watch(studio.sounds, (sounds) => {
  const byId = new Map(sounds.map((sound) => [sound.id, sound]));
  for (const item of items.value) {
    if (item.status !== "processing" || !item.soundId) continue;
    const sound = byId.get(item.soundId);
    if (sound?.status === "ready") item.status = "done";
    if (sound?.status === "failed") {
      item.status = "error";
      item.error = sound.error ?? translate("error.unknown");
    }
  }
  schedule();
});

function add(files: FileList | File[]): void {
  for (const file of Array.from(files)) {
    const error = validation(file);
    items.value.push({
      id: crypto.randomUUID(),
      file,
      status: error ? "error" : "pending",
      progress: 0,
      error,
      soundId: null,
    });
  }
}

async function upload(item: UploadItem, body: UploadDefaults): Promise<void> {
  if (!items.value.includes(item)) return;
  item.error = validation(item.file);
  if (item.error) {
    item.status = "error";
    return;
  }
  item.status = "uploading";
  try {
    const { upload_id, chunk_size } = await ui.uploads.create(item.file.name, item.file.size);
    if (!Number.isInteger(chunk_size) || chunk_size <= 0) throw new Error(translate("error.invalidResponse"));
    for (let offset = 0, index = 0; offset < item.file.size; offset += chunk_size, index++) {
      const end = Math.min(offset + chunk_size, item.file.size);
      await ui.uploads.chunk(upload_id, index, item.file.slice(offset, end));
      item.progress = end / item.file.size;
    }
    const sound = await ui.uploads.complete(upload_id, body);
    item.soundId = sound.id;
    item.status = "processing";
    schedule();
    await Promise.all([useJobs().refresh(), studio.refreshSounds(), studio.refresh()]);
  } catch (cause) {
    item.status = "error";
    item.error = messageOf(cause);
  }
}

function start(defaults: UploadDefaults): Promise<void> {
  if (run) return run;
  if (!defaults.category_id || (!defaults.all_seasons && !defaults.seasons.length)) return Promise.resolve();
  // Snapshot defaults: edits made during the upload affect the next batch only.
  const body = {
    ...defaults,
    seasons: [...defaults.seasons],
    tags: [...defaults.tags],
  };
  if (body.profile_id === "__category_default__" || body.profile_id === undefined) delete body.profile_id;
  const queue = items.value.filter((item) => item.status === "pending");
  busy.value = true;
  async function worker(): Promise<void> {
    for (let item = queue.shift(); item; item = queue.shift()) await upload(item, body);
  }
  run = Promise.all([worker(), worker()])
    .then(() => {})
    .finally(() => {
      busy.value = false;
      run = null;
    });
  return run;
}
function remove(id: string): void {
  items.value = items.value.filter(
    (item) => item.id !== id || item.status === "uploading" || item.status === "processing",
  );
}
function retry(id: string): void {
  const item = items.value.find((item) => item.id === id);
  if (item?.status !== "error" || item.soundId) return;
  item.error = validation(item.file);
  if (!item.error) {
    item.status = "pending";
    item.progress = 0;
  }
}
function clearDone(): void {
  items.value = items.value.filter((item) => item.status !== "done");
}
export function useUpload() {
  return { items, busy, add, start, remove, clearDone, retry };
}
