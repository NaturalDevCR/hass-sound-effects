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
  const gains: any[] = [];
  const makeGain = () => ({
    connect: vi.fn(),
    disconnect: vi.fn(),
    gain: { value: 1, setValueAtTime: vi.fn(), linearRampToValueAtTime: vi.fn(), cancelScheduledValues: vi.fn() },
  });
  const gain = makeGain();
  const ctx = {
    currentTime: 10,
    state: "running",
    destination: {},
    resume: vi.fn().mockResolvedValue(undefined),
    suspend: vi.fn().mockResolvedValue(undefined),
    decodeAudioData: vi.fn().mockResolvedValue({ duration: 12 }),
    createGain: vi.fn(() => { const node = gains.length ? makeGain() : gain; gains.push(node); return node; }),
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
    gains,
    sources,
    engine: new AudioEngine(ctx as unknown as AudioContext),
    buffer: { duration: 12 } as AudioBuffer,
  };
}
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); delete (navigator as any).audioSession; });
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
    expect(sources[0].start).toHaveBeenCalledWith(10, 2, 8);

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
    expect(sources[0].start).toHaveBeenCalledWith(10, 3, 7);
    expect(gain.gain.setValueAtTime).toHaveBeenCalledWith(0.5, 10);
    expect(gain.gain.linearRampToValueAtTime).toHaveBeenCalledWith(1, 11);
    expect(gain.gain.linearRampToValueAtTime).toHaveBeenCalledWith(0, 17);
  });
  it("schedules separate gap-free passes with complete fade envelopes", async () => {
    vi.useFakeTimers();
    const { engine, ctx, sources, gains, buffer } = fakeContext();
    engine.play(buffer, { ...settings, gainDb: 0, fadeIn: 1, fadeOut: 2 }, { loop: true });
    expect(sources[0].loop).not.toBe(true);
    expect(sources).toHaveLength(1);
    ctx.currentTime = 17.9;
    await vi.advanceTimersByTimeAsync(7900);
    expect(sources).toHaveLength(2);
    for (const [index, when] of [10, 18].entries()) {
      expect(sources[index].start).toHaveBeenCalledWith(when, 2, 8);
      expect(gains[index].gain.setValueAtTime).toHaveBeenCalledWith(0, when);
      expect(gains[index].gain.linearRampToValueAtTime).toHaveBeenCalledWith(1, when + 1);
      expect(gains[index].gain.linearRampToValueAtTime).toHaveBeenCalledWith(1, when + 6);
      expect(gains[index].gain.linearRampToValueAtTime).toHaveBeenCalledWith(0, when + 8);
    }
    ctx.currentTime = 19;
    sources[0].onended();
    expect(engine.position).toBe(3);
    ctx.currentTime = 25.9;
    await vi.advanceTimersByTimeAsync(8000);
    expect(sources[2].start).toHaveBeenCalledWith(26, 2, 8);
    expect(gains[2].gain.linearRampToValueAtTime).toHaveBeenCalledWith(0, 34);
    engine.stop();
  });
  it("enables looping without restarting and disables it without changing the current fade", async () => {
    vi.useFakeTimers();
    const { engine, ctx, sources, gain, buffer } = fakeContext();
    engine.onEnded = vi.fn();
    engine.play(buffer, { ...settings, gainDb: 0, fadeIn: 1, fadeOut: 2 });
    ctx.currentTime = 13;
    engine.setLoop(true);
    expect(sources).toHaveLength(1);
    ctx.currentTime = 17.9;
    await vi.advanceTimersByTimeAsync(4900);
    expect(sources[1].start).toHaveBeenCalledWith(18, 2, 8);
    const automation = gain.gain.linearRampToValueAtTime.mock.calls.slice();
    engine.setLoop(false);
    expect(sources[0].stop).not.toHaveBeenCalled();
    expect(gain.gain.cancelScheduledValues).not.toHaveBeenCalled();
    expect(gain.gain.linearRampToValueAtTime.mock.calls).toEqual(automation);
    expect(sources[1].stop).toHaveBeenCalled();
    sources[1].onended();
    expect(engine.playing).toBe(true);
    ctx.currentTime = 18;
    sources[0].onended();
    expect(engine.onEnded).toHaveBeenCalledOnce();
    expect(engine.playing).toBe(false);
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
    await engine.suspend();
    expect((navigator as any).audioSession.type).toBe("auto");
  });
  it("A/B plays the full untouched original and reports natural end", () => {
    const { engine, sources, buffer } = fakeContext();
    engine.onEnded = vi.fn();
    engine.play(buffer, { ...settings, bypass: true });
    expect(sources[0].start).toHaveBeenCalledWith(10, 0, 12);
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

it("computes the Firefox stop level during fades before reading the reset AudioParam", () => {
  const { engine, ctx, gain, buffer } = fakeContext();
  let level = 99;
  const read = vi.fn(() => level);
  Object.defineProperty(gain.gain, "value", { get: read });
  gain.gain.setValueAtTime.mockImplementation((value: number) => { level = value; });
  engine.play(buffer, { ...settings, gainDb: 0, fadeIn: 2, fadeOut: 2 });
  ctx.currentTime = 10.5;
  engine.stop();
  expect(gain.gain.setValueAtTime).toHaveBeenLastCalledWith(0.25, 10.5);
  expect(gain.gain.cancelScheduledValues.mock.invocationCallOrder[0]).toBeLessThan(gain.gain.setValueAtTime.mock.invocationCallOrder.at(-1)!);
  expect(gain.gain.setValueAtTime.mock.invocationCallOrder.at(-1)).toBeLessThan(read.mock.invocationCallOrder[0]!);
  expect(gain.gain.linearRampToValueAtTime).toHaveBeenLastCalledWith(0, 10.51);
});
it("uses the unsupported audio message when Web Audio is absent", () => {
  vi.stubGlobal("AudioContext", undefined);
  vi.stubGlobal("webkitAudioContext", undefined);
  expect(() => new AudioEngine().load("original")).toThrow("This browser cannot play live audio previews.");
});

it("does not ramp or cancel the current envelope when looping is disabled earlier in a pass", async () => {
  vi.useFakeTimers();
  const { engine, ctx, sources, gain, buffer } = fakeContext();
  engine.play(buffer, { ...settings, gainDb: 0, fadeIn: 1, fadeOut: 2 }, { loop: true });
  ctx.currentTime = 13;
  engine.setLoop(false);
  expect(sources[0].stop).not.toHaveBeenCalled();
  expect(gain.gain.cancelScheduledValues).not.toHaveBeenCalled();
  expect(gain.gain.linearRampToValueAtTime).toHaveBeenLastCalledWith(0, 18);
  await vi.advanceTimersByTimeAsync(8000);
  expect(sources).toHaveLength(1);
});
it("schedules the next full pass immediately when enabling loop within the look-ahead window", () => {
  const { engine, ctx, sources, buffer } = fakeContext();
  engine.play(buffer, settings, { from: 4 });
  ctx.currentTime = 15.95;
  engine.setLoop(true);
  expect(sources[0].start).toHaveBeenCalledWith(10, 4, 6);
  expect(sources[1].start).toHaveBeenCalledWith(16, 2, 8);
  engine.stop();
});
it("bounds look-ahead for sub-100ms clips and preserves the current pass on loop-off", () => {
  const { engine, sources, buffer } = fakeContext();
  engine.play(buffer, { ...settings, trimEnd: 2.05, gainDb: 0, fadeIn: 0.01, fadeOut: 0.01 }, { loop: true });
  expect(sources.length).toBeGreaterThan(1);
  expect(sources.length).toBeLessThanOrEqual(4);
  engine.setLoop(false);
  expect(sources[0].stop).not.toHaveBeenCalled();
  for (const future of sources.slice(1)) expect(future.stop).toHaveBeenCalled();
  engine.stop();
});
it("reports a failed context resume as a playback failure and stops the source", async () => {
  const { engine, ctx, sources, buffer } = fakeContext();
  const failure = new Error("Resume rejected");
  ctx.state = "interrupted";
  ctx.resume.mockRejectedValueOnce(failure);
  engine.onError = vi.fn();
  engine.play(buffer, settings);
  await Promise.resolve();
  expect(engine.onError).toHaveBeenCalledWith(failure);
  expect(engine.playing).toBe(false);
  expect(sources[0].stop).toHaveBeenCalled();
});
it("ignores resume rejection after the user stops playback", async () => {
  const { engine, ctx, buffer } = fakeContext();
  let reject!: (cause: Error) => void;
  ctx.state = "suspended";
  ctx.resume.mockReturnValueOnce(new Promise((_resolve, fail) => { reject = fail; }));
  engine.onError = vi.fn();
  engine.play(buffer, settings);
  engine.stop();
  reject(new Error("Late resume failure"));
  await Promise.resolve();
  expect(engine.onError).not.toHaveBeenCalled();
});
it("reports scheduling failure when loop is enabled without leaking a running source", () => {
  const { engine, ctx, buffer } = fakeContext();
  engine.play(buffer, settings);
  ctx.currentTime = 17.95;
  const failure = new Error("Source allocation failed");
  ctx.createBufferSource.mockImplementationOnce(() => { throw failure; });
  engine.onError = vi.fn();
  engine.setLoop(true);
  expect(engine.onError).toHaveBeenCalledWith(failure);
  expect(engine.playing).toBe(false);
});
