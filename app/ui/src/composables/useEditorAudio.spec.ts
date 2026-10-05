import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { defineComponent, h, ref } from "vue";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useEditorAudio } from "./useEditorAudio";
import { AudioUnsupportedError } from "@/lib/audioEngine";
import { IDENTITY } from "@/lib/recipe";
const engine = vi.hoisted(() => ({
  clearCache: vi.fn(),
  suspend: vi.fn().mockResolvedValue(undefined),
  setLoop: vi.fn(),
  load: vi.fn(),
  play: vi.fn(),
  stop: vi.fn(),
  position: 0,
  playing: false,
  onError: undefined as ((cause: unknown) => void) | undefined,
}));
vi.mock("@/lib/audioEngine", async (original) => ({
  ...(await original<typeof import("@/lib/audioEngine")>()), audioEngine: engine,
}));
vi.mock("./usePlayer", () => ({ usePlayer: () => ({ stop: vi.fn() }) }));
let wrapper: VueWrapper;
const buffer = {
  duration: 10,
  numberOfChannels: 1,
  length: 4,
  getChannelData: () => new Float32Array([0, -1, 0.5, 0]),
};
beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
  engine.position = 0;
  engine.playing = false;
  engine.load.mockResolvedValue(buffer);
  engine.play.mockImplementation(() => {
    engine.playing = true;
  });
  engine.stop.mockImplementation(() => {
    engine.playing = false;
  });
  Object.defineProperty(navigator, "userActivation", { configurable: true, value: { hasBeenActive: true } });
});
afterEach(() => {
  wrapper.unmount();
  vi.useRealTimers();
});
async function open() {
  const id = ref("roar");
  const recipe = ref({ ...IDENTITY });
  const valid = ref(true);
  let audio!: ReturnType<typeof useEditorAudio>;
  wrapper = mount(
    defineComponent({
      setup() {
        audio = useEditorAudio(id, recipe, valid);
        return () => h("div");
      },
    }),
  );
  await flushPromises();
  return { audio, recipe, id, valid };
}
it("decodes the original once, computes peaks and debounces live edits for 80 ms at the engine position", async () => {
  const { audio, recipe } = await open();
  expect(engine.load).toHaveBeenCalledWith("api/ui/sounds/roar/original");
  expect(audio.peaks.value).toEqual([0, 1, 0.5, 0]);
  audio.play();
  engine.position = 3;
  recipe.value.gain_db = 3;
  await flushPromises();
  await vi.advanceTimersByTimeAsync(40);
  recipe.value.fade_in = 1;
  await flushPromises();
  await vi.advanceTimersByTimeAsync(79);
  expect(engine.play).toHaveBeenCalledTimes(1);
  await vi.advanceTimersByTimeAsync(1);
  expect(engine.play).toHaveBeenLastCalledWith(buffer, expect.objectContaining({ gainDb: 3, fadeIn: 1 }), {
    loop: false,
    from: 3,
  });
  expect(engine.load).toHaveBeenCalledTimes(1);
});
it("seeks while playing and cancels pending restarts when stopped", async () => {
  const { audio, recipe } = await open();
  audio.play();
  audio.seek(4);
  expect(engine.play).toHaveBeenLastCalledWith(buffer, expect.anything(), { loop: false, from: 4 });
  recipe.value.gain_db = 2;
  await flushPromises();
  audio.stop();
  await vi.advanceTimersByTimeAsync(100);
  expect(engine.play).toHaveBeenCalledTimes(2);
});
it("ignores a stale decode after navigating to another sound", async () => {
  let resolve!: (value: typeof buffer) => void;
  engine.load.mockReturnValueOnce(
    new Promise((answer) => {
      resolve = answer;
    }),
  );
  const { audio, id } = await open();
  id.value = "door";
  await flushPromises();
  const nextBuffer = audio.buffer.value;
  resolve({ ...buffer, duration: 30 });
  await flushPromises();
  expect(audio.buffer.value).toBe(nextBuffer);
  expect(audio.duration.value).toBe(10);
  expect(engine.load).toHaveBeenLastCalledWith("api/ui/sounds/door/original");
});
it("stops live playback for invalid trim and lets bypass play the original", async () => {
  const { audio, valid } = await open();
  audio.play();
  valid.value = false;
  audio.bypass.value = true;
  await flushPromises();
  await vi.advanceTimersByTimeAsync(80);
  expect(engine.play).toHaveBeenLastCalledWith(
    buffer,
    expect.objectContaining({ bypass: true }),
    expect.anything(),
  );
  audio.bypass.value = false;
  await flushPromises();
  expect(audio.playing.value).toBe(false);
});

it("evicts buffers on sound changes/unmount and suspends the context", async () => {
  const { audio, id } = await open();
  id.value = "door";
  await flushPromises();
  expect(engine.clearCache).toHaveBeenCalledOnce();
  wrapper.unmount();
  expect(audio.buffer.value).toBeUndefined();
  expect(engine.suspend).toHaveBeenCalledOnce();
});
it("toggles looping during playback without debouncing or restarting", async () => {
  const { audio } = await open();
  audio.play();
  audio.loop.value = true;
  await flushPromises();
  expect(engine.setLoop).toHaveBeenCalledWith(true);
  await vi.advanceTimersByTimeAsync(80);
  expect(engine.play).toHaveBeenCalledOnce();
});

it("distinguishes decode, synchronous playback, and asynchronous resume errors", async () => {
  engine.load.mockRejectedValueOnce(new Error("Decode failed"));
  const { audio } = await open();
  expect(audio.error.value).toBe("Could not decode this audio. Try again.");
  await audio.decode();
  engine.play.mockImplementationOnce(() => { throw new Error("Start failed"); });
  audio.play();
  expect(audio.error.value).toBe("Could not play this audio. Try again.");
  audio.play();
  expect(audio.error.value).toBeNull();
  engine.onError?.(new Error("Resume rejected"));
  expect(audio.error.value).toBe("Could not play this audio. Try again.");
  expect(audio.playing.value).toBe(false);
});
it("keeps the unsupported Web Audio message for load and play failures", async () => {
  engine.load.mockRejectedValueOnce(new AudioUnsupportedError());
  const { audio } = await open();
  expect(audio.error.value).toBe("This browser cannot play live audio previews.");
  await audio.decode();
  engine.play.mockImplementationOnce(() => { throw new AudioUnsupportedError(); });
  audio.play();
  expect(audio.error.value).toBe("This browser cannot play live audio previews.");
});
