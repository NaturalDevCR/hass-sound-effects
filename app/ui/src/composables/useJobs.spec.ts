import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Job } from "@/api/types";

const mocks = vi.hoisted(() => ({
  ui: { jobs: vi.fn() },
  refreshSounds: vi.fn(),
}));

vi.mock("@/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/client")>()),
  ui: mocks.ui,
}));
vi.mock("@/composables/useStudio", () => ({
  useStudio: () => ({ refreshSounds: mocks.refreshSounds }),
}));

const job = (patch: Partial<Job> & { id: string }): Job => ({
  kind: "publish",
  sound_id: "s1",
  sound_title: "Doorbell",
  status: "done",
  progress: 1,
  error: null,
  created_at: "2026-10-03T10:00:00Z",
  started_at: "2026-10-03T10:00:01Z",
  finished_at: "2026-10-03T10:00:02Z",
  ...patch,
});

async function load() {
  vi.resetModules();
  const { useJobs } = await import("@/composables/useJobs");
  const { useToast } = await import("@/composables/useToast");
  return { jobs: useJobs(), toast: useToast() };
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
  mocks.refreshSounds.mockResolvedValue(undefined);
});
afterEach(() => vi.useRealTimers());

describe("useJobs polling", () => {
  it("fetches immediately and then every 10 s while idle", async () => {
    mocks.ui.jobs.mockResolvedValue([job({ id: "old" })]);
    const { jobs } = await load();
    jobs.start();
    await vi.advanceTimersByTimeAsync(0);
    expect(mocks.ui.jobs).toHaveBeenCalledTimes(1);
    expect(jobs.jobs.value).toHaveLength(1);
    expect(jobs.active.value).toHaveLength(0);

    await vi.advanceTimersByTimeAsync(9_999);
    expect(mocks.ui.jobs).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(mocks.ui.jobs).toHaveBeenCalledTimes(2);
    jobs.stop();
  });

  it("polls every 1500 ms while a job is queued or running", async () => {
    mocks.ui.jobs.mockResolvedValue([
      job({ id: "a", status: "running", progress: 0.4 }),
      job({ id: "b", status: "queued", progress: 0 }),
      job({ id: "c" }),
    ]);
    const { jobs } = await load();
    jobs.start();
    await vi.advanceTimersByTimeAsync(0);
    expect(jobs.active.value.map((j) => j.id)).toEqual(["a", "b"]);

    await vi.advanceTimersByTimeAsync(1_500);
    expect(mocks.ui.jobs).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(3_000);
    expect(mocks.ui.jobs).toHaveBeenCalledTimes(4);
    jobs.stop();
  });

  it("refreshes sounds and toasts once when a job finishes", async () => {
    mocks.ui.jobs
      .mockResolvedValueOnce([job({ id: "a", status: "running", progress: 0.5 })])
      .mockResolvedValue([job({ id: "a", status: "done" })]);
    const { jobs, toast } = await load();
    jobs.start();
    await vi.advanceTimersByTimeAsync(0);
    expect(mocks.refreshSounds).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(1_500);
    expect(mocks.refreshSounds).toHaveBeenCalledTimes(1);
    expect(toast.toasts.value.some((t) => t.kind === "success" && t.message.includes("Doorbell"))).toBe(true);

    await vi.advanceTimersByTimeAsync(10_000);
    expect(mocks.refreshSounds).toHaveBeenCalledTimes(1);
    jobs.stop();
  });

  it("does not replay history: jobs already finished at first load stay quiet", async () => {
    mocks.ui.jobs.mockResolvedValue([job({ id: "old1" }), job({ id: "old2", status: "failed", error: "x" })]);
    const { jobs, toast } = await load();
    jobs.start();
    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(10_000);
    expect(mocks.refreshSounds).not.toHaveBeenCalled();
    expect(toast.toasts.value).toHaveLength(0);
    jobs.stop();
  });

  it("catches jobs that start and finish between two polls", async () => {
    mocks.ui.jobs
      .mockResolvedValueOnce([])
      .mockResolvedValue([job({ id: "fast", kind: "publish", status: "done" })]);
    const { jobs } = await load();
    jobs.start();
    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(10_000);
    expect(mocks.refreshSounds).toHaveBeenCalledTimes(1);
    jobs.stop();
  });

  it("surfaces failures as an error toast carrying the job error", async () => {
    mocks.ui.jobs
      .mockResolvedValueOnce([job({ id: "a", status: "running", progress: 0.1 })])
      .mockResolvedValue([job({ id: "a", status: "failed", error: "ffmpeg exited with 1" })]);
    const { jobs, toast } = await load();
    jobs.start();
    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(1_500);
    const error = toast.toasts.value.find((t) => t.kind === "error");
    expect(error?.message).toContain("ffmpeg exited with 1");
    jobs.stop();
  });

  it("keeps the last list when a poll fails and keeps polling", async () => {
    mocks.ui.jobs
      .mockResolvedValueOnce([job({ id: "a", status: "running", progress: 0.2 })])
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValue([job({ id: "a", status: "running", progress: 0.9 })]);
    const { jobs } = await load();
    jobs.start();
    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(1_500);
    expect(jobs.jobs.value[0]?.progress).toBe(0.2);
    await vi.advanceTimersByTimeAsync(1_500);
    expect(jobs.jobs.value[0]?.progress).toBe(0.9);
    jobs.stop();
  });

  it("start() is idempotent and stop() halts polling", async () => {
    mocks.ui.jobs.mockResolvedValue([]);
    const { jobs } = await load();
    jobs.start();
    jobs.start();
    await vi.advanceTimersByTimeAsync(0);
    expect(mocks.ui.jobs).toHaveBeenCalledTimes(1);
    jobs.stop();
    await vi.advanceTimersByTimeAsync(60_000);
    expect(mocks.ui.jobs).toHaveBeenCalledTimes(1);
  });

  it("refresh() polls right away so callers need not wait for the timer", async () => {
    mocks.ui.jobs.mockResolvedValue([]);
    const { jobs } = await load();
    jobs.start();
    await vi.advanceTimersByTimeAsync(0);
    await jobs.refresh();
    expect(mocks.ui.jobs).toHaveBeenCalledTimes(2);
    jobs.stop();
  });
});
