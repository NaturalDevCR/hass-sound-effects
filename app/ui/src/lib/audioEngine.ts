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

// Shared by seek automation and the Firefox stop fallback.
function envelopeLevel(points: GainPoint[], elapsed: number): number {
  let value = points[0]!.value;
  for (let i = 1; i < points.length; i++) {
    const previous = points[i - 1]!;
    const next = points[i]!;
    if (elapsed >= next.time) value = next.value;
    else {
      if (elapsed >= previous.time)
        value = previous.value +
          (next.value - previous.value) * (elapsed - previous.time) / (next.time - previous.time);
      break;
    }
  }
  return value;
}
export class AudioUnsupportedError extends Error {
  constructor() {
    super(translate("editor.audioUnsupported"));
  }
}
type Pass = {
  source: AudioBufferSourceNode;
  gain: GainNode;
  when: number;
  offset: number;
  endTime: number;
};
type AudioSession = { type: string };

/** Shared context is allocated lazily; the editor calls load only after user activation. */
let sharedContext: AudioContext | undefined;
export class AudioEngine {
  private ctx?: AudioContext;
  private cache = new Map<string, Promise<AudioBuffer>>();
  private passes: Pass[] = [];
  private timer?: ReturnType<typeof setTimeout>;
  private buffer?: AudioBuffer;
  private points: GainPoint[] = [];
  private looping = false;
  private offset = 0;
  private start = 0;
  private end = 0;
  private session?: AudioSession;
  private previousSessionType?: string;
  private lifecycle = 0;
  onEnded?: () => void;
  onError?: (cause: unknown) => void;
  constructor(ctx?: AudioContext) {
    this.ctx = ctx;
  }
  private context(): AudioContext {
    const session = (navigator as Navigator & { audioSession?: AudioSession }).audioSession;
    if (session) {
      try {
        if (!this.session) {
          this.previousSessionType = session.type;
          this.session = session;
        }
        session.type = "playback";
      } catch { /* Some browsers expose a read-only session. */ }
    }
    if (!this.ctx) {
      const Audio =
        globalThis.AudioContext ??
        (globalThis as typeof globalThis & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (!Audio) throw new AudioUnsupportedError();
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
    this.stop();
    const ticket = this.lifecycle;
    this.clearCache();
    if (this.session && this.previousSessionType !== undefined) {
      try { this.session.type = this.previousSessionType; } catch { /* Read-only session. */ }
      this.session = undefined;
      this.previousSessionType = undefined;
    }
    if (!this.ctx) return;
    // Let the stop ramp finish; a new play cancels this pending suspension.
    await new Promise((resolve) => setTimeout(resolve, 10));
    if (ticket === this.lifecycle) await this.ctx.suspend();
  }
  play(buffer: AudioBuffer, settings: PreviewSettings, opts: { loop?: boolean; from?: number } = {}): void {
    this.stop();
    const ticket = this.lifecycle;
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
    this.buffer = buffer;
    this.start = start;
    this.end = end;
    this.offset = offset;
    this.points = gainSchedule({ ...settings, trimStart: start, trimEnd: end });
    this.looping = opts.loop ?? false;
    this.schedulePass(ctx.currentTime, offset);
    this.lookAhead();
  }
  private schedulePass(when: number, offset: number): void {
    const ctx = this.ctx!;
    const source = ctx.createBufferSource();
    const gain = ctx.createGain();
    source.buffer = this.buffer!;
    source.connect(gain);
    gain.connect(ctx.destination);
    const elapsed = offset - this.start;
    gain.gain.setValueAtTime(envelopeLevel(this.points, elapsed), when);
    for (const point of this.points)
      if (point.time > elapsed) gain.gain.linearRampToValueAtTime(point.value, when + point.time - elapsed);
    const pass = { source, gain, when, offset, endTime: when + this.end - offset };
    source.onended = () => {
      source.onended = null;
      source.disconnect();
      gain.disconnect();
      const index = this.passes.indexOf(pass);
      if (index < 0) return;
      this.passes.splice(index, 1);
      if (this.passes.length) return;
      clearTimeout(this.timer);
      this.offset = this.end;
      this.onEnded?.();
    };
    try {
      // Each pass owns its full envelope and ends exactly at the next pass's start.
      source.start(when, offset, this.end - offset);
      this.passes.push(pass);
    } catch (cause) {
      source.onended = null;
      source.disconnect();
      gain.disconnect();
      throw cause;
    }
  }
  private lookAhead(): void {
    clearTimeout(this.timer);
    while (this.looping && this.ctx) {
      const tail = this.passes.at(-1);
      if (!tail) return;
      const delay = (tail.endTime - this.ctx.currentTime - 0.1) * 1000;
      // Treat sub-ms rounding as due; short clips may need several passes in the horizon.
      if (delay <= 1) {
        // A throttled timer may arrive several passes late. Start one fresh pass now;
        // never enqueue expired passes (Web Audio would start them together).
        this.schedulePass(Math.max(tail.endTime, this.ctx.currentTime), this.start);
        continue;
      }
      this.timer = setTimeout(() => {
        try { this.lookAhead(); }
        catch (cause) { this.stop(); this.onError?.(cause); }
      }, delay);
      return;
    }
  }
  setLoop(loop: boolean): void {
    if (this.looping === loop) return;
    this.looping = loop;
    clearTimeout(this.timer);
    if (loop) {
      try { this.lookAhead(); }
      catch (cause) { this.stop(); this.onError?.(cause); }
    }
    else if (this.ctx) {
      // Withdraw only future passes; the audible pass keeps all its fade automation.
      for (const pass of this.passes.filter((p) => p.when > this.ctx!.currentTime)) {
        this.passes.splice(this.passes.indexOf(pass), 1);
        pass.source.stop();
      }
    }
  }
  stop(): void {
    this.lifecycle++;
    clearTimeout(this.timer);
    this.offset = this.position;
    const now = this.ctx?.currentTime ?? 0;
    for (const pass of this.passes) {
      if (pass.when > now) pass.source.stop();
      else {
        const param = pass.gain.gain;
        if (param.cancelAndHoldAtTime) param.cancelAndHoldAtTime(now);
        else {
          const elapsed = pass.offset - this.start + now - pass.when;
          const currentComputedLevel = envelopeLevel(this.points, elapsed);
          param.cancelScheduledValues(now);
          param.setValueAtTime(currentComputedLevel, now);
          // Firefox's value getter is reliable only after resetting the automation.
          const held = param.value;
          if (!Number.isFinite(held)) param.setValueAtTime(currentComputedLevel, now);
        }
        param.linearRampToValueAtTime(0, now + 0.01);
        pass.source.stop(now + 0.01);
      }
    }
    this.passes = [];
    this.buffer = undefined;
  }
  get position(): number {
    if (!this.ctx) return this.offset;
    const pass = [...this.passes].reverse().find((p) => p.when <= this.ctx!.currentTime);
    return pass ? Math.min(this.end, pass.offset + this.ctx.currentTime - pass.when) : this.offset;
  }
  get playing(): boolean {
    return this.passes.length > 0;
  }
}
export const audioEngine = new AudioEngine();
