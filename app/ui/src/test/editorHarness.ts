import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { defineComponent, h } from "vue";
import { createRouter, createMemoryHistory, RouterView } from "vue-router";
import { afterEach, beforeEach, vi } from "vitest";
import SoundEditorView from "@/views/SoundEditorView.vue";
import { useStudio } from "@/composables/useStudio";
import { useJobs } from "@/composables/useJobs";
import { useConfirm } from "@/composables/useConfirm";
import { useI18n } from "@/i18n";
import { makeCategory, makeProfile, makeSeason, makeSound } from "@/test/factories";
import type { Job } from "@/api/types";
const mocks = vi.hoisted(() => ({
  api: {
    list: vi.fn(),
    putRecipe: vi.fn(),
    update: vi.fn(),
    preview: vi.fn(),
    audition: vi.fn(),
    remove: vi.fn(),
  },
  jobs: vi.fn(),
  engine: { clearCache: vi.fn(), suspend: vi.fn().mockResolvedValue(undefined), setLoop: vi.fn(), load: vi.fn(), play: vi.fn(), stop: vi.fn(), playing: false, position: 0, onEnded: undefined },
  media: { src: "", currentTime: 0, paused: true, play: vi.fn().mockResolvedValue(undefined), pause: vi.fn(), load: vi.fn(), removeAttribute: vi.fn(), onended: null as (() => void) | null },
  player: { stop: vi.fn(), toggle: vi.fn() },
}));
vi.mock("@/api/client", async (original) => ({
  ...(await original<typeof import("@/api/client")>()),
  ui: { sounds: mocks.api, jobs: mocks.jobs },
}));
vi.mock("@/lib/audioEngine", async (original) => ({
  ...(await original<typeof import("@/lib/audioEngine")>()), audioEngine: mocks.engine,
}));
vi.mock("@/composables/usePlayer", () => ({ usePlayer: () => mocks.player }));
export const job = (status: Job["status"] = "running"): Job => ({
  id: "preview-1",
  kind: "preview",
  sound_id: "roar",
  sound_title: "Lion",
  status,
  progress: 0,
  error: null,
  created_at: "",
  started_at: null,
  finished_at: null,
});
export let wrapper: VueWrapper;
export const original = {
  filename: "roar.wav",
  duration: 10,
  sample_rate: 44100,
  channels: 1,
  format: "wav",
  codec: "pcm",
  size: 2000,
};
export async function open(id = "roar") {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/", component: { template: "<p>Library</p>" } },
      { path: "/sounds/:id", component: SoundEditorView, props: true },
      { path: "/system", component: { template: "<p>System</p>" } },
    ],
  });
  await router.push(`/sounds/${id}`);
  await router.isReady();
  wrapper = mount(defineComponent({ render: () => h(RouterView) }), {
    attachTo: document.body,
    global: {
      plugins: [router],
      stubs: {
        teleport: true,
        WaveformEditor: { name: "WaveformEditor", props: ["recipe"], template: '<div data-test="waveform" />' },
      },
    },
  });
  await flushPromises();
  return router;
}
beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal("Audio", function () { return mocks.media; });
  mocks.media.src = "";
  mocks.media.play.mockResolvedValue(undefined);
  useI18n().setLocale("en");
  useConfirm().answer(false);
  const studio = useStudio();
  studio.loaded.value = true;
  studio.sounds.value = [makeSound({ id: "roar", title: "Lion", original })];
  studio.categories.value = [makeCategory({ id: "general" })];
  studio.seasons.value = [makeSeason({ id: "regular" })];
  studio.profiles.value = [makeProfile({ id: "voice" })];
  studio.state.value = null;
  mocks.engine.playing = false;
  mocks.engine.position = 0;
  mocks.engine.load.mockResolvedValue({
    duration: 10,
    numberOfChannels: 1,
    getChannelData: () => new Float32Array(10),
  });
  mocks.api.list.mockImplementation(async () => studio.sounds.value);
  mocks.api.update.mockImplementation(async (_id, patch) =>
    makeSound({ ...studio.sounds.value[0]!, ...patch }),
  );
  mocks.api.putRecipe.mockImplementation(async (_id, recipe) => ({
    sound: makeSound({ ...studio.sounds.value[0]!, recipe, status: "rendering" }),
    job: job(),
  }));
  mocks.api.preview.mockResolvedValue({ job: job() });
  mocks.jobs.mockResolvedValue([job()]);
  useJobs().jobs.value = [];
  Object.defineProperty(navigator, "userActivation", { configurable: true, value: { hasBeenActive: true } });
});
afterEach(() => {
  wrapper?.unmount();
  useConfirm().answer(false);
  document.body.innerHTML = "";
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

export { mocks };
