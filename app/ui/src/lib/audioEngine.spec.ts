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
    gain: { setValueAtTime: vi.fn(), linearRampToValueAtTime: vi.fn() },
  };
  const ctx = {
    currentTime: 10,
    state: "running",
    destination: {},
    resume: vi.fn().mockResolvedValue(undefined),
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
    expect(sources[0].start).toHaveBeenCalledWith(10, 2, 8);
    expect(gain.gain.setValueAtTime).toHaveBeenCalledWith(10 ** (6 / 20), 10);
    ctx.currentTime = 11.5;
    expect(engine.position).toBe(3.5);
    engine.stop();
    expect(engine.playing).toBe(false);
    expect(sources[0].stop).toHaveBeenCalled();
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
  it("loops at trim start and ignores ended callbacks after stop", () => {
    const { engine, sources, buffer } = fakeContext();
    engine.onEnded = vi.fn();
    engine.play(buffer, settings, { loop: true, from: 4 });
    sources[0].onended();
    expect(sources[1].start).toHaveBeenCalledWith(10, 2, 8);
    engine.stop();
    expect(sources[1].onended).toBeNull();
    expect(engine.onEnded).not.toHaveBeenCalled();
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
