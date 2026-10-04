vi.mock("@/composables/useJobs", () => {
  const refresh = vi.fn().mockResolvedValue(undefined);
  return { useJobs: () => ({ refresh }) };
});
vi.mock("@/composables/useStudio", async (original) => {
  const actual = await original<typeof import("@/composables/useStudio")>();
  const refresh = vi.fn().mockResolvedValue(undefined),
    refreshSounds = vi.fn().mockResolvedValue(undefined);
  return {
    ...actual,
    useStudio: () => ({ ...actual.useStudio(), refresh, refreshSounds }),
  };
});
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import { ui } from "@/api/client";
import { useStudio } from "./useStudio";
import { useJobs } from "./useJobs";
import { useUpload } from "./useUpload";
import { makeSound } from "@/test/factories";
vi.mock("@/api/client", async (original) => ({
  ...(await original<typeof import("@/api/client")>()),
  ui: { uploads: { create: vi.fn(), chunk: vi.fn(), complete: vi.fn() } },
}));
const defaults = {
  category_id: "general",
  seasons: ["regular"],
  all_seasons: false,
  tags: ["door"],
};
const file = (name = "bell.wav", size = 9 * 1024 * 1024) => new File([new Uint8Array(size)], name);
describe("useUpload", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    useUpload().items.value = [];
    useStudio().sounds.value = [];
    vi.mocked(ui.uploads.create).mockResolvedValue({
      upload_id: "u",
      chunk_size: 4194304,
    });
    vi.mocked(ui.uploads.chunk).mockResolvedValue({ received: 0 });
    vi.mocked(ui.uploads.complete).mockResolvedValue(makeSound({ id: "s", status: "processing" }));
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });
  it("sends a 9 MB file as three sequential raw chunks and completes with defaults", async () => {
    const upload = useUpload();
    upload.add([file()]);
    await upload.start(defaults);
    expect(ui.uploads.chunk).toHaveBeenCalledTimes(3);
    expect(vi.mocked(ui.uploads.chunk).mock.calls.map((c) => [c[1], c[2].size])).toEqual([
      [0, 4194304],
      [1, 4194304],
      [2, 1048576],
    ]);
    expect(ui.uploads.complete).toHaveBeenCalledWith("u", defaults);
    expect(upload.items.value[0]?.status).toBe("processing");
    expect(useStudio().refresh).toHaveBeenCalled();
    expect(useStudio().refreshSounds).toHaveBeenCalled();
    expect(useJobs().refresh).toHaveBeenCalled();
    useStudio().sounds.value = [makeSound({ id: "s" })];
    await nextTick();
    expect(upload.items.value[0]?.status).toBe("done");
  });
  it.each([null, "soft", "__category_default__"])("preserves profile choice %s", async (profile_id) => {
    const upload = useUpload();
    upload.add([file("a.MP3", 1)]);
    await upload.start({ ...defaults, profile_id });
    const body = vi.mocked(ui.uploads.complete).mock.calls[0]?.[1];
    if (profile_id === "__category_default__") expect(body).not.toHaveProperty("profile_id");
    else expect(body?.profile_id).toBe(profile_id);
  });
  it("limits concurrency to two and continues after a chunk failure", async () => {
    let active = 0,
      max = 0;
    vi.mocked(ui.uploads.create).mockImplementation(async (name) => ({
      upload_id: name,
      chunk_size: 4194304,
    }));
    vi.mocked(ui.uploads.chunk).mockImplementation(async (id) => {
      active++;
      max = Math.max(max, active);
      await Promise.resolve();
      active--;
      if (id === "bad.wav") throw new Error("chunk failed");
      return { received: 1 };
    });
    const upload = useUpload();
    upload.add([file("bad.wav", 1), file("b.wav", 1), file("c.wav", 1)]);
    await Promise.all([upload.start(defaults), upload.start(defaults)]);
    expect(max).toBe(2);
    expect(ui.uploads.complete).toHaveBeenCalledTimes(2);
    expect(upload.items.value[0]).toMatchObject({
      status: "error",
      error: "chunk failed",
    });
  });
  it("flags unsupported and oversized files before sending any requests", async () => {
    useStudio().state.value = { settings: { max_upload_mb: 1 } } as never;
    const upload = useUpload();
    upload.add([file("no.exe", 1), file("large.wav", 2 * 1024 * 1024)]);
    expect(upload.items.value.every((i) => i.status === "error")).toBe(true);
    await upload.start(defaults);
    expect(ui.uploads.create).not.toHaveBeenCalled();
    useStudio().state.value = null;
  });
  it("tracks processing failures reported by studio refresh", async () => {
    const upload = useUpload();
    upload.add([file("a.wav", 1)]);
    await upload.start(defaults);
    useStudio().sounds.value = [makeSound({ id: "s", status: "failed", error: "decode failed" })];
    await nextTick();
    expect(upload.items.value[0]).toMatchObject({
      status: "error",
      error: "decode failed",
    });
  });

  it("snapshots defaults, reports byte progress, and protects active items from removal", async () => {
    let release!: () => void;
    vi.mocked(ui.uploads.chunk).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          release = () => resolve({ received: 4194304 });
        }),
    );
    const upload = useUpload();
    upload.add([file()]);
    const chosen = { ...defaults, tags: ["first"], seasons: ["regular"] };
    const running = upload.start(chosen);
    await nextTick();
    const id = upload.items.value[0]!.id;
    upload.remove(id);
    expect(upload.items.value).toHaveLength(1);
    chosen.tags.push("later");
    chosen.seasons.push("winter");
    release();
    await running;
    expect(ui.uploads.complete).toHaveBeenCalledWith("u", { ...defaults, tags: ["first"], seasons: ["regular"] });
    expect(upload.items.value[0]?.progress).toBe(1);
    upload.remove(id);
    expect(upload.items.value).toHaveLength(1);
    useStudio().sounds.value = [makeSound({ id: "s" })];
    await nextTick();
    upload.clearDone();
    expect(upload.items.value).toHaveLength(0);
  });
  it("rechecks the size limit at start and retries a failed transfer", async () => {
    const upload = useUpload();
    upload.add([file("retry.wav", 1)]);
    vi.mocked(ui.uploads.chunk).mockRejectedValueOnce(new Error("offline"));
    await upload.start(defaults);
    const id = upload.items.value[0]!.id;
    upload.retry(id);
    expect(upload.items.value[0]?.status).toBe("pending");
    await upload.start(defaults);
    expect(upload.items.value[0]?.status).toBe("processing");
    upload.add([file("too-big.wav", 2 * 1024 * 1024)]);
    useStudio().state.value = { settings: { max_upload_mb: 1 } } as never;
    await upload.start(defaults);
    expect(upload.items.value.at(-1)?.status).toBe("error");
    useStudio().state.value = null;
  });
});
