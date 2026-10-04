import { ApiError } from "@/api/client";
import { translate } from "@/i18n";
export type PreviewSettings = {
  trimStart: number;
  trimEnd: number;
  gainDb: number;
  fadeIn: number;
  fadeOut: number;
  bypass: boolean;
};
type GainPoint = { time: number; value: number };

export function gainSchedule(s: PreviewSettings): GainPoint[] {
  if (s.bypass) return [{ time: 0, value: 1 }];
  const gain = 10 ** (s.gainDb / 20);
  const length = Math.max(0, s.trimEnd - s.trimStart);
  const sum = Math.max(0, s.fadeIn) + Math.max(0, s.fadeOut);
  const scale = sum > length ? length / sum : 1;
  const fadeIn = Math.max(0, s.fadeIn) * scale;
  const fadeOut = Math.max(0, s.fadeOut) * scale;
  const points = [{ time: 0, value: fadeIn > 0 ? 0 : gain }];
  if (fadeIn > 0) points.push({ time: fadeIn, value: gain });
  if (fadeOut > 0) {
    points.push({ time: length - fadeOut, value: gain }, { time: length, value: 0 });
  }
  return points;
}

/** Shared context is allocated lazily; the editor calls load only after user activation. */
let sharedContext: AudioContext | undefined;
export class AudioEngine {
  private ctx?: AudioContext;
  private cache = new Map<string, Promise<AudioBuffer>>();
  private source?: AudioBufferSourceNode;
  private gain?: GainNode;
  private startedAt = 0;
  private offset = 0;
  private end = 0;
  private start = 0;
  private level = 1;
  private lifecycle = 0;
  onEnded?: () => void;
  onError?: (cause: unknown) => void;
  constructor(ctx?: AudioContext) {
    this.ctx = ctx;
  }
  private context(): AudioContext {
    const session = (navigator as Navigator & { audioSession?: { type: string } }).audioSession;
    if (session) {
      try { session.type = "playback"; } catch { /* Some browsers expose a read-only session. */ }
    }
    if (!this.ctx) {
      const Audio =
        globalThis.AudioContext ??
        (globalThis as typeof globalThis & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (!Audio) throw new Error(translate("editor.audioUnsupported"));
      sharedContext ??= new Audio();
      this.ctx = sharedContext;
    }
    return this.ctx;
  }
  load(url: string): Promise<AudioBuffer> {
    const cached = this.cache.get(url);
    if (cached) {
      this.cache.delete(url);
      this.cache.set(url, cached);
      return cached;
    }
    // Allocate synchronously in the gesture, before awaiting the network.
    const ctx = this.context();
    const result = (async () => {
      const response = await fetch(url);
      if (!response.ok)
        throw new ApiError(response.status, translate("error.http", { status: response.status }));
      return ctx.decodeAudioData(await response.arrayBuffer());
    })().catch((cause) => {
      if (this.cache.get(url) === result) this.cache.delete(url);
      throw cause;
    });
    this.cache.set(url, result);
    while (this.cache.size > 2) this.cache.delete(this.cache.keys().next().value!);
    return result;
  }
  /** At most two URL entries (including pending decodes), touched on every load.
   * Clearing drops pending promises too; late resolutions never repopulate the cache. */
  clearCache(): void {
    this.cache.clear();
  }
  async suspend(): Promise<void> {
    const ticket = ++this.lifecycle;
    this.stop();
    this.clearCache();
    if (!this.ctx) return;
    // Let the stop ramp finish; a new play cancels this pending suspension.
    await new Promise((resolve) => setTimeout(resolve, 10));
    if (ticket === this.lifecycle) await this.ctx.suspend();
  }
  play(buffer: AudioBuffer, settings: PreviewSettings, opts: { loop?: boolean; from?: number } = {}): void {
    const ticket = ++this.lifecycle;
    this.stop();
    const ctx = this.context();
    if (["suspended", "interrupted"].includes(ctx.state))
      void ctx.resume().catch((cause) => {
        if (ticket !== this.lifecycle) return;
        this.stop();
        this.onError?.(cause);
      });
    const start = settings.bypass ? 0 : settings.trimStart;
    const end = settings.bypass ? buffer.duration : Math.min(buffer.duration, settings.trimEnd);
    const offset = Math.max(start, Math.min(opts.from ?? start, end));
    if (end <= offset) return;
    const source = ctx.createBufferSource();
    const gain = ctx.createGain();
    source.buffer = buffer;
    source.connect(gain);
    gain.connect(ctx.destination);
    const now = ctx.currentTime;
    const elapsed = offset - start;
    const points = gainSchedule({ ...settings, trimStart: start, trimEnd: end });
    // Interpolate the envelope at a seek/restart, then schedule only remaining points.
    let value = points[0]!.value;
    for (let i = 1; i < points.length; i++) {
      const previous = points[i - 1]!;
      const next = points[i]!;
      if (elapsed >= next.time) value = next.value;
      else {
        if (elapsed >= previous.time)
          value =
            previous.value +
            ((next.value - previous.value) * (elapsed - previous.time)) / (next.time - previous.time);
        break;
      }
    }
    gain.gain.setValueAtTime(value, now);
    for (const point of points)
      if (point.time > elapsed) gain.gain.linearRampToValueAtTime(point.value, now + point.time - elapsed);
    this.source = source;
    this.gain = gain;
    this.offset = offset;
    this.end = end;
    this.start = start;
    this.level = settings.bypass ? 1 : 10 ** (settings.gainDb / 20);
    source.loop = opts.loop ?? false;
    source.loopStart = start;
    source.loopEnd = end;
    // Loop fades apply to the first pass only; restore steady gain at its boundary.
    if (source.loop) gain.gain.setValueAtTime(this.level, now + end - offset);
    this.startedAt = now;
    source.onended = () => {
      source.onended = null;
      source.disconnect();
      gain.disconnect();
      if (this.source !== source) return;
      this.source = undefined;
      this.gain = undefined;
      this.offset = end;
      this.onEnded?.();
    };
    source.start(now, offset);
    if (!source.loop) source.stop(now + end - offset);
  }
  setLoop(loop: boolean): void {
    if (!this.source || !this.ctx || this.source.loop === loop) return;
    const now = this.ctx.currentTime;
    this.offset = this.position;
    this.startedAt = now;
    this.source.loop = loop;
    // A later stop() replaces the existing scheduled stop (Web Audio contract).
    this.source.stop(loop ? now + 1e9 : now + this.end - this.offset);
    this.gain!.gain.cancelScheduledValues(now);
    this.gain!.gain.setValueAtTime(this.level, now);
  }
  stop(): void {
    this.offset = this.position;
    const source = this.source;
    const gain = this.gain;
    if (source && gain && this.ctx) {
      const now = this.ctx.currentTime;
      if (gain.gain.cancelAndHoldAtTime) gain.gain.cancelAndHoldAtTime(now);
      else {
        gain.gain.cancelScheduledValues(now);
        gain.gain.setValueAtTime(gain.gain.value, now);
      }
      gain.gain.linearRampToValueAtTime(0, now + 0.01);
      source.stop(now + 0.01);
      // onended disconnects the retired nodes after the ramp, without ending a new source.
    }
    this.source = undefined;
    this.gain = undefined;
  }
  get position(): number {
    if (!this.source || !this.ctx) return this.offset;
    const position = this.offset + this.ctx.currentTime - this.startedAt;
    return this.source.loop
      ? this.start + ((position - this.start) % (this.end - this.start))
      : Math.min(this.end, position);
  }
  get playing(): boolean {
    return this.source !== undefined;
  }
}
export const audioEngine = new AudioEngine();
