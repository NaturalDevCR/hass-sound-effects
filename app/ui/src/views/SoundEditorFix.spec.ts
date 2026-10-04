import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { defineComponent, h } from "vue";
import { createRouter, createMemoryHistory, RouterView } from "vue-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import SoundEditorView from "./SoundEditorView.vue";
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
vi.mock("@/lib/audioEngine", () => ({ audioEngine: mocks.engine }));
vi.mock("@/composables/usePlayer", () => ({ usePlayer: () => mocks.player }));
const job = (status: Job["status"] = "running"): Job => ({
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
let wrapper: VueWrapper;
const original = {
  filename: "roar.wav",
  duration: 10,
  sample_rate: 44100,
  channels: 1,
  format: "wav",
  codec: "pcm",
  size: 2000,
};
async function open(id = "roar") {
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

it("keeps trim string drafts through clearing/decimals, commits blur and preserves two-second fades", async () => {
  const sound = useStudio().sounds.value[0]!;
  sound.recipe = { ...sound.recipe, trim_start: 0.5, trim_end: 9, fade_in: 2, fade_out: 2 };
  await open();
  const end = wrapper.get('[data-test="trim-end"]');
  await end.trigger("focus");
  (end.element as HTMLInputElement).value = "";
  await end.trigger("input");
  expect(wrapper.findComponent({ name: "WaveformEditor" }).props("recipe").trim_end).toBe(9);
  (end.element as HTMLInputElement).value = "8.";
  await end.trigger("input");
  expect((end.element as HTMLInputElement).value).toBe("8.");
  expect(wrapper.findComponent({ name: "WaveformEditor" }).props("recipe").trim_end).toBe(9);
  await end.trigger("blur");
  await flushPromises();
  await wrapper.get('[data-test="publish"]').trigger("click");
  expect(mocks.api.putRecipe).toHaveBeenCalledWith("roar", expect.objectContaining({ trim_end: 8, fade_in: 2, fade_out: 2 }));
});
it("commits trim on Enter and keeps waveform edits synchronized", async () => {
  await open();
  const start = wrapper.get('[data-test="trim-start"]');
  (start.element as HTMLInputElement).value = "1.25";
  await start.trigger("input");
  await start.trigger("keydown", { key: "Enter" });
  expect(wrapper.findComponent({ name: "WaveformEditor" }).props("recipe").trim_start).toBe(1.25);
  wrapper.findComponent({ name: "WaveformEditor" }).vm.$emit("trim", 2, 8);
  await flushPromises();
  expect((start.element as HTMLInputElement).value).toBe("2");
});
it("never offers a stored server preview in a new session", async () => {
  useStudio().sounds.value[0]!.has_preview = true;
  await open();
  expect(wrapper.find('[data-test="play-preview"]').exists()).toBe(false);
  await wrapper.get('[data-test="audition"]').trigger("click");
  expect(wrapper.findComponent({ name: "AuditionDialog" }).props("previewAvailable")).toBe(false);
});
it("replays the session preview without rendering again and handles rejected autoplay with a hint", async () => {
  await open();
  await wrapper.get('[data-test="preview"]').trigger("click");
  await flushPromises();
  mocks.media.play.mockRejectedValueOnce(new Error("NotAllowedError"));
  useJobs().jobs.value = [job("done")];
  await flushPromises();
  expect(wrapper.get('[data-test="play-preview"]').text()).toBe("Play preview");
  expect(wrapper.text()).toContain("Tap Play preview");
  expect(wrapper.find('[role="alert"]').exists()).toBe(false);
  await wrapper.get('[data-test="play-preview"]').trigger("click");
  await flushPromises();
  expect(wrapper.get('[data-test="play-preview"]').text()).toBe("Stop preview");
  await wrapper.get('[data-test="play-preview"]').trigger("click");
  expect(mocks.media.pause).toHaveBeenCalled();
  await wrapper.get('[data-test="play-preview"]').trigger("click");
  await flushPromises();
  mocks.media.onended?.();
  await flushPromises();
  expect(wrapper.get('[data-test="play-preview"]').text()).toBe("Play preview");
  expect(mocks.api.preview).toHaveBeenCalledTimes(1);
});
it("times out pending previews after 120 seconds and ignores late completion", async () => {
  vi.useFakeTimers();
  await open();
  await wrapper.get('[data-test="preview"]').trigger("click");
  await flushPromises();
  await vi.advanceTimersByTimeAsync(120_000);
  expect(wrapper.get('[role="alert"]').text()).toContain("120 seconds");
  expect(wrapper.get('[data-test="preview"]').attributes("disabled")).toBeUndefined();
  useJobs().jobs.value = [job("done")];
  await flushPromises();
  expect(wrapper.find('[data-test="play-preview"]').exists()).toBe(false);
});
it("allows shortcuts from range, radio and checkbox controls and offers touch gain reset", async () => {
  await open();
  await wrapper.get('[data-test="gain"]').setValue("3");
  await wrapper.get('[data-test="gain"]').trigger("keydown", { key: "l" });
  expect(wrapper.get('[data-test="loop"]').attributes("aria-pressed")).toBe("true");
  await wrapper.get('input[type="radio"]').trigger("keydown", { key: "b" });
  expect(wrapper.get('[data-test="bypass"]').attributes("aria-pressed")).toBe("true");
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  wrapper.element.append(checkbox);
  checkbox.dispatchEvent(new KeyboardEvent("keydown", { key: " ", bubbles: true }));
  expect(mocks.engine.play).toHaveBeenCalled();
  await wrapper.get('[data-test="reset-gain"]').trigger("click");
  expect((wrapper.get('[data-test="gain"]').element as HTMLInputElement).value).toBe("0");
});
it("shows a processing placeholder without trim errors until original audio is available", async () => {
  useStudio().sounds.value[0]!.original = null;
  useStudio().sounds.value[0]!.status = "processing";
  await open();
  expect(wrapper.text()).toContain("Waveform available after processing");
  expect(wrapper.text()).not.toContain("The start must come before the end.");
  expect(mocks.engine.load).not.toHaveBeenCalled();
});

it("updates transport positions relative to trim without rerendering the editor or announcing each frame", async () => {
  useStudio().sounds.value[0]!.recipe.trim_start = 2;
  await open();
  const editor = wrapper.findComponent(SoundEditorView);
  const tree = editor.vm.$.subTree;
  const transport = wrapper.findComponent({ name: "TransportBar" });
  const position = transport.props("position");
  position.value = 5;
  await flushPromises();
  expect(wrapper.get('[data-test="position"]').text()).toBe("0:03.0 / 0:08.0");
  expect(editor.vm.$.subTree).toBe(tree);
  expect(transport.find("output").exists()).toBe(false);
  expect(transport.get('[aria-live="polite"]').text()).toBe("");
  await wrapper.get('[data-test="bypass"]').trigger("click");
  expect(wrapper.get('[data-test="position"]').text()).toBe("0:05.0 / 0:10.0");
});

it("clears the session preview when navigating to another sound", async () => {
  const router = await open();
  await wrapper.get('[data-test="preview"]').trigger("click");
  await flushPromises();
  useJobs().jobs.value = [job("done")];
  await flushPromises();
  useStudio().sounds.value.push(makeSound({ id: "door", original, has_preview: true }));
  await router.push("/sounds/door");
  await flushPromises();
  expect(wrapper.find('[data-test="play-preview"]').exists()).toBe(false);
  expect(mocks.engine.clearCache).toHaveBeenCalled();
});
