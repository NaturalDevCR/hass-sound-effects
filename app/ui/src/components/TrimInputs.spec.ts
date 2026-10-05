import { mount } from "@vue/test-utils";
import { expect, it } from "vitest";
import TrimInputs from "./TrimInputs.vue";
import { IDENTITY } from "@/lib/recipe";
it("reports invalid drafts upward only after commit, clearing the alert on input", async () => {
  const w = mount(TrimInputs, { props: { recipe: { ...IDENTITY }, duration: 10, disabled: false } });
  const input = w.get('[data-test="trim-end"]');
  (input.element as HTMLInputElement).value = "oops";
  await input.trigger("input");
  expect(w.find('[role="alert"]').exists()).toBe(false);
  await input.trigger("blur");
  expect(w.find('[role="alert"]').exists()).toBe(true);
  expect(w.emitted("invalid")?.at(-1)).toEqual([true]);
  (input.element as HTMLInputElement).value = "8.";
  await input.trigger("input");
  expect(w.find('[role="alert"]').exists()).toBe(false);
  expect(w.emitted("invalid")?.at(-1)).toEqual([false]);
  w.unmount();
});
it("lets Escape bubble when unchanged, but consumes it to revert a draft", async () => {
  const w = mount(TrimInputs, { props: { recipe: { ...IDENTITY }, duration: 10, disabled: false } });
  const input = w.get("input");
  const escaped = () => new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });
  const clean = escaped();
  input.element.dispatchEvent(clean);
  expect(clean.defaultPrevented).toBe(false);
  await input.setValue("oops");
  const draft = escaped();
  input.element.dispatchEvent(draft);
  await w.vm.$nextTick();
  expect(draft.defaultPrevented).toBe(true);
  expect((input.element as HTMLInputElement).value).toBe("0");
  w.unmount();
});
it("shows durations rounded to milliseconds without rewriting the recipe on blur", async () => {
  const w = mount(TrimInputs, {
    props: { recipe: { ...IDENTITY }, duration: 8.045714, disabled: false },
  });
  const end = w.get('[data-test="trim-end"]');
  expect((end.element as HTMLInputElement).value).toBe("8.046");
  await end.trigger("focus");
  await end.trigger("blur");
  expect(w.emitted("trim")).toBeUndefined();
  w.unmount();
});
