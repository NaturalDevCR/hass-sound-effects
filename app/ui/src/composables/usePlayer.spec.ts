import { beforeEach, describe, expect, it, vi } from "vitest";

type Listener = () => void;

class FakeAudio {
  static last: FakeAudio | null = null;
  static playImpl: () => Promise<void> = async () => undefined;
  src = "";
  currentTime = 0;
  preload = "";
  play = vi.fn(() => FakeAudio.playImpl());
  pause = vi.fn();
  private listeners = new Map<string, Listener[]>();
  constructor() {
    FakeAudio.last = this;
  }
  addEventListener(type: string, fn: Listener) {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), fn]);
  }
  emit(type: string) {
    for (const fn of this.listeners.get(type) ?? []) fn();
  }
}

async function load() {
  vi.resetModules();
  vi.stubGlobal("Audio", FakeAudio);
  FakeAudio.playImpl = async () => undefined;
  const { usePlayer } = await import("@/composables/usePlayer");
  const { useToast } = await import("@/composables/useToast");
  return { player: usePlayer(), toast: useToast() };
}

beforeEach(() => vi.unstubAllGlobals());

describe("usePlayer", () => {
  it("plays a url and tracks the current sound", async () => {
    const { player } = await load();
    player.toggle("s1", "api/ui/sounds/s1/published?v=1");
    const audio = FakeAudio.last!;
    expect(audio.src).toBe("api/ui/sounds/s1/published?v=1");
    expect(audio.play).toHaveBeenCalledTimes(1);
    expect(player.currentId.value).toBe("s1");
    expect(player.playing.value).toBe(true);
  });

  it("toggling the same sound stops it", async () => {
    const { player } = await load();
    player.toggle("s1", "u1");
    player.toggle("s1", "u1");
    expect(FakeAudio.last!.pause).toHaveBeenCalled();
    expect(player.playing.value).toBe(false);
    expect(player.currentId.value).toBeNull();
  });

  it("switches sources on a single shared element", async () => {
    const { player } = await load();
    player.toggle("s1", "u1");
    const first = FakeAudio.last;
    player.toggle("s2", "u2");
    expect(FakeAudio.last).toBe(first);
    expect(first!.src).toBe("u2");
    expect(first!.play).toHaveBeenCalledTimes(2);
    expect(player.currentId.value).toBe("s2");
    expect(player.playing.value).toBe(true);
  });

  it("resets when playback ends", async () => {
    const { player } = await load();
    player.toggle("s1", "u1");
    FakeAudio.last!.emit("ended");
    expect(player.playing.value).toBe(false);
    expect(player.currentId.value).toBeNull();
  });

  it("stop() pauses and clears state", async () => {
    const { player } = await load();
    player.toggle("s1", "u1");
    player.stop();
    expect(FakeAudio.last!.pause).toHaveBeenCalled();
    expect(player.currentId.value).toBeNull();
  });

  it("reports playback failures with a toast and resets", async () => {
    const { player, toast } = await load();
    FakeAudio.playImpl = () => Promise.reject(new Error("NotSupportedError"));
    player.toggle("s1", "u1");
    await Promise.resolve();
    await Promise.resolve();
    expect(player.playing.value).toBe(false);
    expect(player.currentId.value).toBeNull();
    expect(toast.toasts.value.at(-1)?.kind).toBe("error");
  });
});
