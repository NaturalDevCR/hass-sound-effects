import { mount, flushPromises } from "@vue/test-utils";
import { afterEach, expect, it, vi } from "vitest";
import { createRouter, createMemoryHistory } from "vue-router";
import SystemView from "./SystemView.vue";
import { useStudio } from "@/composables/useStudio";
import { makeState } from "@/test/system";
afterEach(() => vi.restoreAllMocks());
it.each(["/system?section=import", "/system#import"])(
  "scrolls the import panel after state loads at %s",
  async (path) => {
    useStudio().loaded.value = false;
    useStudio().state.value = null;
    const scroll = vi.fn();
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", { configurable: true, value: scroll });
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: "/system", component: SystemView }],
    });
    await router.push(path);
    await router.isReady();
    const w = mount(SystemView, {
      global: {
        plugins: [router],
        stubs: {
          ConnectionPanel: true,
          FilesPanel: true,
          MediaUrlPanel: true,
          ImportPanel: true,
          SpeakersPanel: true,
          LimitsPanel: true,
          StoragePanel: true,
          JobsPanel: true,
        },
      },
    });
    expect(scroll).not.toHaveBeenCalled();
    useStudio().state.value = makeState();
    useStudio().loaded.value = true;
    await flushPromises();
    expect(w.find("#import").exists()).toBe(true);
    expect(scroll).toHaveBeenCalledOnce();
    useStudio().state.value = makeState();
    await flushPromises();
    expect(scroll).toHaveBeenCalledOnce();
    w.unmount();
  },
);
