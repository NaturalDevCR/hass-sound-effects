import { mount, flushPromises } from "@vue/test-utils";
import { beforeEach, afterEach, expect, it, vi } from "vitest";
import ConnectionPanel from "./ConnectionPanel.vue";
import { ui } from "@/api/client";
import { copyText } from "@/lib/clipboard";
import { useStudio } from "@/composables/useStudio";
import { useConfirm } from "@/composables/useConfirm";
import { useI18n } from "@/i18n";
import { makeState } from "@/test/system";
vi.mock("@/lib/clipboard", () => ({ copyText: vi.fn() }));
vi.mock("@/composables/useStudio", async (original) => {
  const actual = await original<typeof import("@/composables/useStudio")>();
  const refresh = vi.fn();
  return { useStudio: () => ({ ...actual.useStudio(), refresh }) };
});
let w: ReturnType<typeof mount>;
beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
  useI18n().setLocale("en");
  useStudio().state.value = makeState();
  vi.spyOn(ui, "token").mockResolvedValue({ token: "secret" });
  vi.spyOn(ui, "rotateToken").mockResolvedValue({ api_token_masked: "new" });
  vi.mocked(copyText).mockResolvedValue(true);
});
afterEach(() => {
  w?.unmount();
  useConfirm().answer(false);
  vi.restoreAllMocks();
  vi.useRealTimers();
});
it("fetches only on explicit reveal and clears the token after 30 seconds", async () => {
  w = mount(ConnectionPanel, { props: { state: makeState() } });
  expect(ui.token).not.toHaveBeenCalled();
  await w.get('[data-test="reveal-token"]').trigger("click");
  await flushPromises();
  expect((w.get('[data-test="token"]').element as HTMLInputElement).value).toBe("secret");
  await vi.advanceTimersByTimeAsync(30_000);
  expect((w.get('[data-test="token"]').element as HTMLInputElement).value).toBe("••••abcd");
  expect(useStudio().state.value).not.toHaveProperty("token");
});
it("copies hostname and token; selects visible token if copying fails", async () => {
  w = mount(ConnectionPanel, { props: { state: makeState() }, attachTo: document.body });
  await w.get('[data-test="copy-host"]').trigger("click");
  expect(copyText).toHaveBeenCalledWith("studio.local");
  vi.mocked(copyText).mockResolvedValue(false);
  await w.get('[data-test="copy-token"]').trigger("click");
  await flushPromises();
  const token = w.get('[data-test="token"]').element as HTMLInputElement;
  expect(token.value).toBe("secret");
  expect(token.selectionEnd).toBe(6);
  expect(w.text()).toContain("Select and copy manually");
});
it("rotates only after danger confirmation, hides token and refreshes state", async () => {
  w = mount(ConnectionPanel, { props: { state: makeState() } });
  await w.get('[data-test="rotate-token"]').trigger("click");
  expect(ui.rotateToken).not.toHaveBeenCalled();
  expect(useConfirm().request.value?.danger).toBe(true);
  expect(useConfirm().request.value?.message).toContain("automatically");
  useConfirm().answer(true);
  await flushPromises();
  expect(ui.rotateToken).toHaveBeenCalledOnce();
  expect(useStudio().refresh).toHaveBeenCalledOnce();
});
it("explains a missing Supervisor hostname", () => {
  w = mount(ConnectionPanel, { props: { state: { ...makeState(), hostname: null } } });
  expect(w.text()).toContain("Supervisor");
  expect(w.text()).toContain("8099");
  expect(w.get('[data-test="copy-host"]').attributes("disabled")).toBeDefined();
});
it("cancels rotation without changing the token", async () => {
  w = mount(ConnectionPanel, { props: { state: makeState() } });
  await w.get('[data-test="rotate-token"]').trigger("click");
  useConfirm().answer(false);
  await flushPromises();
  expect(ui.rotateToken).not.toHaveBeenCalled();
  expect(w.attributes("aria-busy")).toBe("false");
});
it("shows token fetch errors inline and releases pending state", async () => {
  vi.mocked(ui.token).mockRejectedValueOnce(new Error("Token unavailable"));
  w = mount(ConnectionPanel, { props: { state: makeState() } });
  await w.get('[data-test="reveal-token"]').trigger("click");
  await flushPromises();
  expect(w.get('[role="alert"]').text()).toBe("Token unavailable");
  expect(w.get('[data-test="reveal-token"]').attributes("disabled")).toBeUndefined();
});
