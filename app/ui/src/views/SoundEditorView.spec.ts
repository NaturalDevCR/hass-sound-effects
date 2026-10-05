import { flushPromises } from "@vue/test-utils";
import { expect, it, describe } from "vitest";
import { mocks, job, original, wrapper, open } from "@/test/editorHarness";
import SoundEditorView from "./SoundEditorView.vue";
import { useStudio } from "@/composables/useStudio";
import { useJobs } from "@/composables/useJobs";
import { useConfirm } from "@/composables/useConfirm";
import { makeSound } from "@/test/factories";
describe("sound editor", () => {
  it("disables unchanged save, publishes selected gain/profile and stays open", async () => {
    await open();
    expect(wrapper.get('[data-test="publish"]').attributes("disabled")).toBeDefined();
    await wrapper.get('[data-test="gain"]').setValue("3");
    await wrapper.findAll('input[type="radio"]')[1]!.setValue(true);
    expect(wrapper.get('[data-test="publish"]').attributes("disabled")).toBeUndefined();
    await wrapper.get('[data-test="publish"]').trigger("click");
    await flushPromises();
    expect(mocks.api.putRecipe).toHaveBeenCalledWith(
      "roar",
      expect.objectContaining({ gain_db: 3, profile_id: "voice" }),
    );
    expect(wrapper.find('[data-test="gain"]').exists()).toBe(true);
    expect(wrapper.text()).toContain("Rendering");
  });
  it("guards close and route leave; cancel retains edits", async () => {
    const router = await open();
    await wrapper.get('[data-test="gain"]').setValue("2");
    await wrapper.get('button[aria-label="Close"]').trigger("click");
    await flushPromises();
    expect(useConfirm().request.value?.title).toBe("Discard unsaved changes?");
    useConfirm().answer(false);
    await flushPromises();
    expect(router.currentRoute.value.path).toBe("/sounds/roar");
    const leaving = router.push("/");
    await flushPromises();
    expect(useConfirm().request.value).not.toBeNull();
    useConfirm().answer(true);
    await leaving;
    expect(router.currentRoute.value.path).toBe("/");
  });
  it("saves details independently, including a pending tag draft", async () => {
    await open();
    await wrapper.get('[data-test="detail-title"]').setValue("Door roar");
    const tags = wrapper.findAll('input[type="text"]').at(-1)!;
    await tags.setValue("Front Door");
    await wrapper.get('button[role="switch"][aria-checked="true"]').trigger("click");
    await wrapper.get('[data-test="save-details"]').trigger("click");
    await flushPromises();
    expect(mocks.api.update).toHaveBeenCalledWith(
      "roar",
      expect.objectContaining({ title: "Door roar", tags: ["front_door"], enabled: false }),
    );
    expect(mocks.api.putRecipe).not.toHaveBeenCalled();
    expect(wrapper.get('[data-test="save-details"]').attributes("disabled")).toBeDefined();
  });
  it("guards dirty details on Escape", async () => {
    await open();
    await wrapper.get('[data-test="detail-title"]').setValue("Changed");
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    await flushPromises();
    expect(useConfirm().request.value).not.toBeNull();
  });
  it("waits for the exact preview job before playing, then exposes preview testing", async () => {
    await open();
    await wrapper.get('[data-test="preview"]').trigger("click");
    await flushPromises();
    expect(mocks.media.play.mock.invocationCallOrder[0]).toBeLessThan(mocks.api.preview.mock.invocationCallOrder[0]!);
    expect(mocks.api.preview).toHaveBeenCalledWith("roar", useStudio().sounds.value[0]!.recipe);
    expect(mocks.media.play).toHaveBeenCalledTimes(1);
    expect(wrapper.get('[data-test="preview"]').attributes("aria-busy")).toBe("true");
    useJobs().jobs.value = [{ ...job("done"), id: "unrelated" }];
    await flushPromises();
    expect(mocks.media.play).toHaveBeenCalledTimes(1);
    useJobs().jobs.value = [job("done")];
    await flushPromises();
    expect(mocks.media.play).toHaveBeenCalledTimes(2);
    expect(mocks.media.src).toMatch(/^api\/ui\/sounds\/roar\/preview\?v=/);
    expect(wrapper.text()).toContain("Preview ready");
  });
  it("shows failed preview inline and allows retry", async () => {
    await open();
    await wrapper.get('[data-test="preview"]').trigger("click");
    await flushPromises();
    useJobs().jobs.value = [{ ...job("failed"), error: "Render failed" }];
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain("Render failed");
    expect(mocks.media.play).toHaveBeenCalledTimes(1);
    expect(wrapper.get('[data-test="preview"]').attributes("disabled")).toBeUndefined();
  });
  it("handles keyboard shortcuts and ignores typing and modal dialogs", async () => {
    await open();
    const send = (key: string) =>
      document.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
    send("l");
    send("b");
    await flushPromises();
    expect(wrapper.get('[data-test="loop"]').attributes("aria-pressed")).toBe("true");
    expect(wrapper.get('[data-test="bypass"]').attributes("aria-pressed")).toBe("true");
    send(" ");
    await flushPromises();
    expect(mocks.engine.play).toHaveBeenCalled();
    await wrapper.get('[data-test="detail-title"]').trigger("keydown", { key: "b" });
    expect(wrapper.get('[data-test="bypass"]').attributes("aria-pressed")).toBe("true");
    await wrapper.get('[data-test="audition"]').trigger("click");
    send("b");
    await flushPromises();
    expect(wrapper.get('[data-test="bypass"]').attributes("aria-pressed")).toBe("true");
  });
  it("reports decode failure and retries", async () => {
    mocks.engine.load.mockRejectedValueOnce(new Error("Bad audio"));
    await open();
    expect(wrapper.get('[role="alert"]').text()).toContain("Could not decode this audio");
    await wrapper.get('[data-test="retry-decode"]').trigger("click");
    await flushPromises();
    expect(wrapper.find('[data-test="waveform"]').exists()).toBe(true);
  });
  it("shows missing sound and disables invalid trim and busy publishing", async () => {
    await open("missing");
    expect(wrapper.text()).toContain("Sound not found");
    expect(mocks.engine.load).not.toHaveBeenCalled();
    wrapper.unmount();
    await open();
    await wrapper.get('[data-test="trim-start"]').setValue("10");
    expect(wrapper.text()).toContain("The start must come before the end.");
    expect(wrapper.get('[data-test="publish"]').attributes("disabled")).toBeDefined();
  });
});

it("nudges trim by hundredths, shift by tenths and preserves invalid fades after trimming", async () => {
  await open();
  const start = wrapper.get('[data-test="trim-start"]');
  await start.trigger("keydown", { key: "ArrowUp" });
  expect((start.element as HTMLInputElement).value).toBe("0.01");
  await start.trigger("keydown", { key: "ArrowUp", shiftKey: true });
  expect((start.element as HTMLInputElement).value).toBe("0.11");
  await wrapper.get('[data-test="fade_in"]').setValue("4");
  await wrapper.get('[data-test="trim-end"]').setValue("1");
  expect(wrapper.text()).toContain("4.00 s");
  expect(wrapper.text()).toContain("The fades are longer than the trimmed clip.");
  expect(wrapper.get('[data-test="publish"]').attributes("disabled")).toBeDefined();
});
it("invalidates an exact preview when the recipe changes and preserves new edits during publishing", async () => {
  await open();
  await wrapper.get('[data-test="preview"]').trigger("click");
  await flushPromises();
  useJobs().jobs.value = [job("done")];
  await flushPromises();
  await wrapper.get('[data-test="gain"]').setValue("2");
  expect(wrapper.text()).toContain("Recipe changed");
  let resolve!: (value: any) => void;
  mocks.api.putRecipe.mockReturnValueOnce(
    new Promise((answer) => {
      resolve = answer;
    }),
  );
  await wrapper.get('[data-test="publish"]').trigger("click");
  await wrapper.get('[data-test="gain"]').setValue("3");
  resolve({
    sound: makeSound({
      ...useStudio().sounds.value[0]!,
      recipe: { ...useStudio().sounds.value[0]!.recipe, gain_db: 2 },
      status: "rendering",
    }),
    job: job(),
  });
  await flushPromises();
  expect((wrapper.get('[data-test="gain"]').element as HTMLInputElement).value).toBe("3");
  expect(wrapper.get('[data-test="publish"]').attributes("disabled")).toBeDefined();
  useStudio().sounds.value = [
    makeSound({
      ...useStudio().sounds.value[0]!,
      status: "ready",
      published: { ...useStudio().sounds.value[0]!.published!, revision: 2, loudness_lufs: -18 },
    }),
  ];
  await flushPromises();
  expect(wrapper.text()).toContain("Revision 2");
  expect(wrapper.text()).toContain("−18.0 LUFS");
  expect(wrapper.get('[data-test="publish"]').attributes("disabled")).toBeUndefined();
});
it("deletes only after danger confirmation, closes without a second dirty prompt, and refreshes", async () => {
  const router = await open();
  await wrapper.get('[data-test="gain"]').setValue("2");
  await wrapper.get('[data-test="delete"]').trigger("click");
  await flushPromises();
  expect(useConfirm().request.value?.danger).toBe(true);
  useConfirm().answer(false);
  await flushPromises();
  expect(mocks.api.remove).not.toHaveBeenCalled();
  await wrapper.get('[data-test="delete"]').trigger("click");
  useConfirm().answer(true);
  await flushPromises();
  expect(mocks.api.remove).toHaveBeenCalledWith("roar");
  expect(router.currentRoute.value.path).toBe("/");
  expect(useConfirm().request.value).toBeNull();
  expect(mocks.api.list).toHaveBeenCalled();
});
it("keeps details dirty when a save fails and shows inline errors for publishing", async () => {
  await open();
  mocks.api.update.mockRejectedValueOnce(new Error("Details rejected"));
  await wrapper.get('[data-test="detail-title"]').setValue("Changed");
  await wrapper.get('[data-test="save-details"]').trigger("click");
  await flushPromises();
  expect(wrapper.text()).toContain("Details rejected");
  expect(wrapper.get('[data-test="save-details"]').attributes("disabled")).toBeUndefined();
  mocks.api.putRecipe.mockRejectedValueOnce(new Error("Publish rejected"));
  await wrapper.get('[data-test="gain"]').setValue("2");
  await wrapper.get('[data-test="publish"]').trigger("click");
  await flushPromises();
  expect(wrapper.text()).toContain("Publish rejected");
  expect(wrapper.get('[data-test="publish"]').attributes("disabled")).toBeUndefined();
});
