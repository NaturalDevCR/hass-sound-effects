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
  const points = [{ time: 0, value: s.fadeIn > 0 ? 0 : gain }];
  if (s.fadeIn > 0) points.push({ time: s.fadeIn, value: gain });
  if (s.fadeOut > 0) {
    points.push({ time: length - s.fadeOut, value: gain }, { time: length, value: 0 });
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
  onEnded?: () => void;
  onError?: (cause: unknown) => void;
  constructor(ctx?: AudioContext) {
    this.ctx = ctx;
  }
  private context(): AudioContext {
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
    if (cached) return cached;
    // Allocate synchronously in the gesture, before awaiting the network.
    const ctx = this.context();
    const result = (async () => {
      const response = await fetch(url);
      if (!response.ok)
        throw new ApiError(response.status, translate("error.http", { status: response.status }));
      return ctx.decodeAudioData(await response.arrayBuffer());
    })().catch((cause) => {
      this.cache.delete(url);
      throw cause;
    });
    this.cache.set(url, result);
    return result;
  }
  play(buffer: AudioBuffer, settings: PreviewSettings, opts: { loop?: boolean; from?: number } = {}): void {
    this.stop();
    const ctx = this.context();
    if (ctx.state === "suspended")
      void ctx.resume().catch((cause) => {
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
    const points = gainSchedule(settings);
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
    this.startedAt = now;
    source.onended = () => {
      if (this.source !== source) return;
      source.onended = null;
      source.disconnect();
      gain.disconnect();
      this.source = undefined;
      this.gain = undefined;
      this.offset = end;
      if (opts.loop) this.play(buffer, settings, { loop: true });
      else this.onEnded?.();
    };
    source.start(now, offset, end - offset);
  }
  stop(): void {
    this.offset = this.position;
    if (this.source) {
      this.source.onended = null;
      this.source.stop();
      this.source.disconnect();
      this.gain?.disconnect();
    }
    this.source = undefined;
    this.gain = undefined;
  }
  get position(): number {
    return this.source && this.ctx
      ? Math.min(this.end, this.offset + this.ctx.currentTime - this.startedAt)
      : this.offset;
  }
  get playing(): boolean {
    return this.source !== undefined;
  }
}
export const audioEngine = new AudioEngine();
