import { flushPromises } from "@vue/test-utils";
import { expect, it, vi } from "vitest";
import { mocks, job, original, wrapper, open } from "@/test/editorHarness";
import SoundEditorView from "./SoundEditorView.vue";
import { useStudio } from "@/composables/useStudio";
import { useJobs } from "@/composables/useJobs";
import { useConfirm } from "@/composables/useConfirm";
import { makeSound } from "@/test/factories";
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
it("allows L/B shortcuts from controls and preserves Space activation and offers touch gain reset", async () => {
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
  expect(mocks.engine.play).not.toHaveBeenCalled();
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

it.each(["publish", "details", "delete", "revert"])("clears preview failure when %s starts and shows the latest action error", async (action) => {
  await open();
  mocks.api.preview.mockRejectedValueOnce(new Error("Preview rejected"));
  await wrapper.get('[data-test="preview"]').trigger("click");
  await flushPromises();
  expect(wrapper.get('[role="alert"]').text()).toBe("Preview rejected");
  await wrapper.get('[data-test="gain"]').setValue("2");
  if (action === "publish") {
    mocks.api.putRecipe.mockRejectedValueOnce(new Error("Publish rejected"));
    await wrapper.get('[data-test="publish"]').trigger("click");
  } else if (action === "details") {
    mocks.api.update.mockRejectedValueOnce(new Error("Details rejected"));
    await wrapper.get('[data-test="detail-title"]').setValue("Changed");
    await wrapper.get('[data-test="save-details"]').trigger("click");
  } else if (action === "delete") {
    mocks.api.remove.mockRejectedValueOnce(new Error("Delete rejected"));
    await wrapper.get('[data-test="delete"]').trigger("click");
    expect(wrapper.text()).not.toContain("Preview rejected");
    useConfirm().answer(true);
  } else await wrapper.get('[data-test="revert"]').trigger("click");
  await flushPromises();
  expect(wrapper.text()).not.toContain("Preview rejected");
  if (action === "revert") expect(wrapper.find('[role="alert"]').exists()).toBe(false);
  else {
    expect(wrapper.findAll('[role="alert"]')).toHaveLength(1);
    expect(wrapper.get('[role="alert"]').text()).toBe(`${action[0]!.toUpperCase()}${action.slice(1)} rejected`);
  }
});
it("renders only the latest error across details, publish and preview actions", async () => {
  await open();
  await wrapper.get('[data-test="detail-title"]').setValue("Changed");
  mocks.api.update.mockRejectedValueOnce(new Error("Details rejected"));
  await wrapper.get('[data-test="save-details"]').trigger("click");
  await flushPromises();
  await wrapper.get('[data-test="gain"]').setValue("2");
  mocks.api.putRecipe.mockRejectedValueOnce(new Error("Publish rejected"));
  await wrapper.get('[data-test="publish"]').trigger("click");
  await flushPromises();
  expect(wrapper.findAll('[role="alert"]')).toHaveLength(1);
  expect(wrapper.get('[role="alert"]').text()).toBe("Publish rejected");
  mocks.api.preview.mockRejectedValueOnce(new Error("Preview rejected"));
  await wrapper.get('[data-test="preview"]').trigger("click");
  await flushPromises();
  expect(wrapper.findAll('[role="alert"]')).toHaveLength(1);
  expect(wrapper.get('[role="alert"]').text()).toBe("Preview rejected");
});
it("accepts comma decimals, keeps invalid drafts on blur, corrects them and reverts on Escape", async () => {
  await open();
  const end = wrapper.get('[data-test="trim-end"]');
  await end.setValue("8,5");
  await end.trigger("blur");
  await flushPromises();
  expect((end.element as HTMLInputElement).value).toBe("8.5");
  expect(wrapper.findComponent({ name: "WaveformEditor" }).props("recipe").trim_end).toBe(8.5);
  await end.setValue("nope");
  await end.trigger("blur");
  await flushPromises();
  expect((end.element as HTMLInputElement).value).toBe("nope");
  expect(end.attributes("aria-invalid")).toBe("true");
  expect(wrapper.text()).toContain("Enter a valid number");
  await end.setValue("7.5");
  expect(end.attributes("aria-invalid")).toBe("false");
  expect(wrapper.text()).not.toContain("Enter a valid number");
  await end.setValue("8,5,1");
  await end.trigger("keydown", { key: "Escape" });
  await flushPromises();
  expect((end.element as HTMLInputElement).value).toBe("7.5");
  expect(end.attributes("aria-invalid")).toBe("false");
  expect(useConfirm().request.value).toBeNull();
});
it("reserves Left/Right for caret movement and Up/Down for nudging", async () => {
  await open();
  const start = wrapper.get('[data-test="trim-start"]');
  await start.setValue("1.25");
  for (const key of ["ArrowLeft", "ArrowRight"]) {
    const event = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true });
    start.element.dispatchEvent(event);
    await flushPromises();
    expect(event.defaultPrevented).toBe(false);
    expect((start.element as HTMLInputElement).value).toBe("1.25");
  }
  await start.trigger("keydown", { key: "ArrowDown", shiftKey: true });
  expect((start.element as HTMLInputElement).value).toBe("1.15");
});
it.each(["10", "12", "9.9995", "10,5"])("stores full-duration End %s as identity", async (value) => {
  await open();
  await wrapper.get('[data-test="trim-end"]').setValue(value);
  expect(wrapper.findComponent({ name: "WaveformEditor" }).props("recipe").trim_end).toBeNull();
  expect(wrapper.get('[data-test="publish"]').attributes("disabled")).toBeDefined();
});
it("labels a stale rendered preview Play last render", async () => {
  await open();
  await wrapper.get('[data-test="preview"]').trigger("click");
  await flushPromises();
  useJobs().jobs.value = [job("done")];
  await flushPromises();
  await wrapper.get('[data-test="gain"]').setValue("2");
  await wrapper.get('[data-test="play-preview"]').trigger("click");
  expect(wrapper.get('[data-test="play-preview"]').text()).toBe("Play last render");
});
it.each(['button', 'a', '[role="switch"]', '[role="radio"]', 'input[type="checkbox"]', 'input[type="radio"]', 'select', 'textarea', 'input[type="text"]', '[contenteditable="true"]'])("leaves Space activation on focused %s", async (selector) => {
  await open();
  const samples = document.createElement("div");
  samples.innerHTML = '<button><span>Button</span></button><a href="#">Link</a><div role="switch"></div><div role="radio"></div><input type="checkbox"><input type="radio"><select></select><textarea></textarea><input type="text"><div contenteditable="true"></div>';
  wrapper.element.append(samples);
  const control = samples.querySelector(selector)!;
  const target = selector === 'button' ? control.firstChild! : control;
  const event = new KeyboardEvent("keydown", { key: " ", bubbles: true, cancelable: true });
  target.dispatchEvent(event);
  expect(event.defaultPrevented).toBe(false);
  expect(mocks.engine.play).not.toHaveBeenCalled();
});
it.each(['[data-test="gain"]', '[data-test="waveform"]'])("toggles playback with Space on %s", async (selector) => {
  await open();
  const event = new KeyboardEvent("keydown", { key: " ", bubbles: true, cancelable: true });
  wrapper.get(selector).element.dispatchEvent(event);
  expect(event.defaultPrevented).toBe(true);
  expect(mocks.engine.play).toHaveBeenCalledOnce();
});
