import { afterEach, describe, expect, it, vi } from "vitest";
import { AudioEngine, gainSchedule, type PreviewSettings } from "./audioEngine";
const settings: PreviewSettings = {
  trimStart: 2,
  trimEnd: 10,
  gainDb: 6,
  fadeIn: 0,
  fadeOut: 0,
  bypass: false,
};
function fakeContext() {
  const sources: any[] = [];
  const gain = {
    connect: vi.fn(),
    disconnect: vi.fn(),
    gain: { value: 1, setValueAtTime: vi.fn(), linearRampToValueAtTime: vi.fn(), cancelScheduledValues: vi.fn() },
  };
  const ctx = {
    currentTime: 10,
    state: "running",
    destination: {},
    resume: vi.fn().mockResolvedValue(undefined),
    suspend: vi.fn().mockResolvedValue(undefined),
    decodeAudioData: vi.fn().mockResolvedValue({ duration: 12 }),
    createGain: vi.fn(() => gain),
    createBufferSource: vi.fn(() => {
      const source = {
        buffer: null,
        onended: null as (() => void) | null,
        connect: vi.fn(),
        start: vi.fn(),
        stop: vi.fn(),
        disconnect: vi.fn(),
      };
      sources.push(source);
      return source;
    }),
  };
  return {
    ctx,
    gain,
    sources,
    engine: new AudioEngine(ctx as unknown as AudioContext),
    buffer: { duration: 12 } as AudioBuffer,
  };
}
afterEach(() => vi.unstubAllGlobals());
describe("gainSchedule", () => {
  it("converts dB to amplitude without unnecessary points", () => {
    expect(gainSchedule(settings)).toEqual([{ time: 0, value: 10 ** (6 / 20) }]);
  });
  it("ramps up and down at exact clip-relative times", () => {
    expect(gainSchedule({ ...settings, gainDb: 0, fadeIn: 1, fadeOut: 2 })).toEqual([
      { time: 0, value: 0 },
      { time: 1, value: 1 },
      { time: 6, value: 1 },
      { time: 8, value: 0 },
    ]);
    expect(gainSchedule({ ...settings, gainDb: 0, fadeOut: 2 })).toEqual([
      { time: 0, value: 1 },
      { time: 6, value: 1 },
      { time: 8, value: 0 },
    ]);
  });
  it("bypasses all editing", () =>
    expect(gainSchedule({ ...settings, bypass: true, fadeIn: 2 })).toEqual([{ time: 0, value: 1 }]));
});
describe("AudioEngine", () => {
  it("fetches and decodes once per URL, retries failed loads", async () => {
    const { ctx, engine } = fakeContext();
    const fetch = vi.fn().mockResolvedValue({ ok: true, arrayBuffer: async () => new ArrayBuffer(4) });
    vi.stubGlobal("fetch", fetch);
    await Promise.all([engine.load("original"), engine.load("original")]);
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(ctx.decodeAudioData).toHaveBeenCalledTimes(1);
    fetch.mockRejectedValueOnce(new Error("offline"));
    await expect(engine.load("other")).rejects.toThrow("offline");
    await engine.load("other");
    expect(fetch).toHaveBeenCalledTimes(3);
  });
  it("wires source → gain → destination and stops/disconnects", () => {
    const { engine, ctx, sources, gain, buffer } = fakeContext();
    engine.play(buffer, settings);
    expect(sources[0].connect).toHaveBeenCalledWith(gain);
    expect(gain.connect).toHaveBeenCalledWith(ctx.destination);
    expect(sources[0].start).toHaveBeenCalledWith(10, 2);
    expect(sources[0].stop).toHaveBeenCalledWith(18);
    expect(gain.gain.setValueAtTime).toHaveBeenCalledWith(10 ** (6 / 20), 10);
    ctx.currentTime = 11.5;
    expect(engine.position).toBe(3.5);
    engine.stop();
    expect(engine.playing).toBe(false);
    expect(sources[0].stop).toHaveBeenCalled();
    expect(sources[0].stop).toHaveBeenLastCalledWith(11.51);
    expect(gain.gain.linearRampToValueAtTime).toHaveBeenLastCalledWith(0, 11.51);
    sources[0].onended();
    expect(sources[0].disconnect).toHaveBeenCalled();
    expect(gain.disconnect).toHaveBeenCalled();
  });
  it("seeks inside a fade without restarting that fade", () => {
    const { engine, sources, gain, buffer } = fakeContext();
    engine.play(buffer, { ...settings, gainDb: 0, fadeIn: 2, fadeOut: 2 }, { from: 3 });
    expect(sources[0].start).toHaveBeenCalledWith(10, 3);
    expect(gain.gain.setValueAtTime).toHaveBeenCalledWith(0.5, 10);
    expect(gain.gain.linearRampToValueAtTime).toHaveBeenCalledWith(1, 11);
    expect(gain.gain.linearRampToValueAtTime).toHaveBeenCalledWith(0, 17);
  });
  it("loops seamlessly and toggles without restarting the source", () => {
    const { engine, ctx, sources, buffer } = fakeContext();
    engine.play(buffer, settings, { loop: true, from: 4 });
    expect(sources[0]).toMatchObject({ loop: true, loopStart: 2, loopEnd: 10 });
    expect(sources[0].start).toHaveBeenCalledWith(10, 4);
    ctx.currentTime = 17;
    expect(engine.position).toBe(3);
    engine.setLoop(false);
    expect(sources[0].loop).toBe(false);
    expect(sources[0].stop).toHaveBeenLastCalledWith(24);
    engine.setLoop(true);
    expect(sources).toHaveLength(1);
    expect(sources[0].loop).toBe(true);
  });
  it("keeps at most two buffers, touches LRU entries, and clears pending entries", async () => {
    const { engine, ctx } = fakeContext();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, arrayBuffer: async () => new ArrayBuffer(4) }));
    await engine.load("a");
    await engine.load("b");
    await engine.load("a");
    await engine.load("c");
    await engine.load("a");
    expect(ctx.decodeAudioData).toHaveBeenCalledTimes(3);
    await engine.load("b");
    expect(ctx.decodeAudioData).toHaveBeenCalledTimes(4);
    engine.clearCache();
    await engine.load("b");
    expect(ctx.decodeAudioData).toHaveBeenCalledTimes(5);
  });
  it("suspends on disposal, resumes interrupted contexts and sets the playback session", async () => {
    const { engine, ctx, buffer } = fakeContext();
    Object.defineProperty(navigator, "audioSession", { configurable: true, value: { type: "auto" } });
    await engine.suspend();
    expect(ctx.suspend).toHaveBeenCalledOnce();
    ctx.state = "interrupted";
    engine.play(buffer, settings);
    expect(ctx.resume).toHaveBeenCalledOnce();
    expect((navigator as any).audioSession.type).toBe("playback");
  });
  it("A/B plays the full untouched original and reports natural end", () => {
    const { engine, sources, buffer } = fakeContext();
    engine.onEnded = vi.fn();
    engine.play(buffer, { ...settings, bypass: true });
    expect(sources[0].start).toHaveBeenCalledWith(10, 0);
    sources[0].onended();
    expect(engine.playing).toBe(false);
    expect(engine.onEnded).toHaveBeenCalledTimes(1);
  });
});

it("scales overlapping fades proportionally to the clip length", () => {
  expect(gainSchedule({ ...settings, trimEnd: 5, gainDb: 0, fadeIn: 4, fadeOut: 2 })).toEqual([
    { time: 0, value: 0 }, { time: 2, value: 1 }, { time: 2, value: 1 }, { time: 3, value: 0 },
  ]);
});

it("does not let an evicted pending decode remove a newer cache entry", async () => {
  const { engine, ctx } = fakeContext();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, arrayBuffer: async () => new ArrayBuffer(4) }));
  let reject!: (cause: Error) => void;
  ctx.decodeAudioData.mockReturnValueOnce(new Promise((_resolve, fail) => { reject = fail; }));
  const pending = engine.load("a");
  await Promise.resolve();
  await Promise.resolve();
  engine.clearCache();
  await engine.load("a");
  reject(new Error("stale decode"));
  await expect(pending).rejects.toThrow("stale decode");
  await engine.load("a");
  expect(ctx.decodeAudioData).toHaveBeenCalledTimes(2);
});
