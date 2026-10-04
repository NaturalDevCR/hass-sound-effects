import { mdiPlay, mdiStop } from "@mdi/js";
import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import SoundItem from "@/components/SoundItem.vue";
import { useI18n } from "@/i18n";
import { makeCategory, makeSeason, makeSound } from "@/test/factories";

const regular = makeSeason({ id: "regular", name: "Regular" });
const halloween = makeSeason({ id: "halloween", name: "Halloween", color: "#f97316" });

type Props = InstanceType<typeof SoundItem>["$props"];

function mountItem(props: Partial<Props> = {}) {
  return mount(SoundItem, {
    props: {
      sound: makeSound({
        id: "s1",
        title: "Front door",
        published: {
          revision: 3,
          filename: "s1-r3.mp3",
          duration: 2.5,
          loudness_lufs: -16.04,
          true_peak_db: -1.5,
          size: 1,
          published_at: "2026-10-03T10:00:00Z",
          mime_type: "audio/mpeg",
        },
      }),
      seasons: [regular],
      playing: false,
      selected: false,
      selecting: false,
      ...props,
    } as Props,
    attachTo: document.body,
  });
}

function pointer(wrapper: ReturnType<typeof mountItem>, type: string, init: Record<string, unknown> = {}) {
  const event = new Event(type, { bubbles: true, cancelable: true });
  Object.assign(event, { pointerType: "touch", isPrimary: true, clientX: 100, clientY: 100, ...init });
  wrapper.get('[data-test="body"]').element.dispatchEvent(event);
}

beforeEach(() => useI18n().setLocale("en"));
afterEach(() => {
  vi.useRealTimers();
  document.body.innerHTML = "";
});

describe("SoundItem", () => {
  it("renders the title, duration and integrated loudness", () => {
    const wrapper = mountItem();
    expect(wrapper.get('[data-test="title"]').text()).toBe("Front door");
    expect(wrapper.get('[data-test="meta"]').text()).toContain("0:02.5");
    expect(wrapper.get('[data-test="meta"]').text()).toContain("−16.0 LUFS");
  });

  it("shows a dash for loudness that was never measured", () => {
    const sound = makeSound({ id: "s2", published: null, status: "processing" });
    expect(mountItem({ sound }).get('[data-test="meta"]').text()).toContain("—");
  });

  it("emits open with the sound id when the body is clicked", async () => {
    const wrapper = mountItem();
    await wrapper.get('[data-test="body"]').trigger("click");
    expect(wrapper.emitted("open")).toEqual([["s1"]]);
    expect(wrapper.emitted("select")).toBeUndefined();
  });

  it("emits toggle-play from a 48 px play button without opening the sound", async () => {
    const wrapper = mountItem();
    const play = wrapper.get('[data-test="play"]');
    expect(play.classes()).toContain("size-12");
    expect(play.attributes("aria-label")).toBe("Play Front door");
    expect(play.attributes("aria-pressed")).toBe("false");
    expect(play.get("path").attributes("d")).toBe(mdiPlay);
    await play.trigger("click");
    expect(wrapper.emitted("toggle-play")).toEqual([["s1"]]);
    expect(wrapper.emitted("open")).toBeUndefined();
  });

  it("shows the playing state", () => {
    const play = mountItem({ playing: true }).get('[data-test="play"]');
    expect(play.attributes("aria-pressed")).toBe("true");
    expect(play.attributes("aria-label")).toBe("Stop Front door");
    expect(play.get("path").attributes("d")).toBe(mdiStop);
  });

  it("disables play when there is no published revision", async () => {
    const wrapper = mountItem({ sound: makeSound({ id: "s2", published: null, status: "processing" }) });
    const play = wrapper.get('[data-test="play"]');
    expect(play.attributes("disabled")).toBeDefined();
    await play.trigger("click");
    expect(wrapper.emitted("toggle-play")).toBeUndefined();
  });

  it("dims disabled sounds and badges them", () => {
    const wrapper = mountItem({ sound: makeSound({ id: "s3", title: "Muted", enabled: false }) });
    expect(wrapper.get('[data-test="disabled-badge"]').text()).toBe("Disabled");
    expect(wrapper.get('[data-test="content"]').classes()).toContain("opacity-60");
    expect(mountItem().find('[data-test="disabled-badge"]').exists()).toBe(false);
  });

  describe("status", () => {
    it("stays quiet for ready sounds", () => {
      expect(mountItem().find('[data-test="status"]').exists()).toBe(false);
    });

    it.each(["processing", "rendering"] as const)("shows a spinner pill while %s", (status) => {
      const wrapper = mountItem({ sound: makeSound({ id: "s4", status }) });
      const pill = wrapper.get('[data-test="status"]');
      expect(pill.get('[data-status]').attributes("data-status")).toBe(status);
      expect(pill.find("svg.animate-spin").exists()).toBe(true);
    });

    it("exposes the error of a failed sound as a tooltip and to screen readers", () => {
      const wrapper = mountItem({ sound: makeSound({ id: "s5", status: "failed", error: "ffmpeg exited 1" }) });
      const status = wrapper.get('[data-test="status"]');
      expect(status.attributes("title")).toBe("ffmpeg exited 1");
      expect(status.get(".sr-only").text()).toBe("ffmpeg exited 1");
    });
  });

  describe("badges and tags", () => {
    it("shows the season badges and the tags", () => {
      const wrapper = mountItem({
        sound: makeSound({ id: "s6", seasons: ["regular", "halloween"], tags: ["es", "bath"] }),
        seasons: [regular, halloween],
      });
      const text = wrapper.get('[data-test="chips"]').text();
      expect(text).toContain("Regular");
      expect(text).toContain("Halloween");
      expect(text).toContain("#es");
      expect(text).toContain("#bath");
    });

    it("shows a single All seasons badge for sounds that play all year", () => {
      const wrapper = mountItem({ sound: makeSound({ id: "s7", all_seasons: true, seasons: [] }), seasons: [] });
      expect(wrapper.get('[data-test="chips"]').text()).toContain("All seasons");
    });

    it("truncates long tag lists with a +N counter", () => {
      const tags = ["a", "b", "c", "d", "e"];
      const wrapper = mountItem({ sound: makeSound({ id: "s8", tags }) });
      const text = wrapper.get('[data-test="chips"]').text();
      expect(text).toContain("#a");
      expect(text).not.toContain("#e");
      expect(text).toContain("+2");
    });

    it("names the category when asked to", () => {
      const wrapper = mountItem({ category: makeCategory({ id: "general", name: "Doorbells" }) });
      expect(wrapper.get('[data-test="meta"]').text()).toContain("Doorbells");
      expect(mountItem().get('[data-test="meta"]').text()).not.toContain("Doorbells");
    });
  });

  describe("selection", () => {
    it("emits select from an accessible checkbox", async () => {
      const wrapper = mountItem({ selected: true });
      const box = wrapper.get('[data-test="select"]');
      expect(box.attributes("role")).toBe("checkbox");
      expect(box.attributes("aria-checked")).toBe("true");
      expect(box.attributes("aria-label")).toBe("Select Front door");
      await box.trigger("click");
      expect(wrapper.emitted("select")).toEqual([["s1"]]);
      expect(wrapper.emitted("open")).toBeUndefined();
    });

    it("turns a body click into a selection toggle while selecting", async () => {
      const wrapper = mountItem({ selecting: true });
      await wrapper.get('[data-test="body"]').trigger("click");
      expect(wrapper.emitted("select")).toEqual([["s1"]]);
      expect(wrapper.emitted("open")).toBeUndefined();
    });

    it("marks selected sounds", () => {
      expect(mountItem({ selected: true }).get("li").attributes("data-selected")).toBe("true");
      expect(mountItem().get("li").attributes("data-selected")).toBe("false");
    });
  });

  describe("long press", () => {
    beforeEach(() => vi.useFakeTimers());

    it("selects after 450 ms on touch and swallows the click that follows", async () => {
      const wrapper = mountItem();
      pointer(wrapper, "pointerdown");
      vi.advanceTimersByTime(449);
      expect(wrapper.emitted("select")).toBeUndefined();
      vi.advanceTimersByTime(1);
      expect(wrapper.emitted("select")).toEqual([["s1"]]);

      pointer(wrapper, "pointerup");
      await wrapper.get('[data-test="body"]').trigger("click");
      expect(wrapper.emitted("open")).toBeUndefined();
      expect(wrapper.emitted("select")).toHaveLength(1);

      // later (keyboard, a new tap) clicks work normally again
      vi.advanceTimersByTime(1000);
      await wrapper.get('[data-test="body"]').trigger("click");
      expect(wrapper.emitted("open")).toEqual([["s1"]]);
    });

    it("works with a pen too", () => {
      const wrapper = mountItem();
      pointer(wrapper, "pointerdown", { pointerType: "pen" });
      vi.advanceTimersByTime(450);
      expect(wrapper.emitted("select")).toHaveLength(1);
    });

    it("is cancelled by lifting the finger early (a normal tap)", async () => {
      const wrapper = mountItem();
      pointer(wrapper, "pointerdown");
      vi.advanceTimersByTime(200);
      pointer(wrapper, "pointerup");
      vi.advanceTimersByTime(1000);
      expect(wrapper.emitted("select")).toBeUndefined();
      await wrapper.get('[data-test="body"]').trigger("click");
      expect(wrapper.emitted("open")).toEqual([["s1"]]);
    });

    it("is cancelled by moving more than 8 px (the user is scrolling)", () => {
      const wrapper = mountItem();
      pointer(wrapper, "pointerdown");
      vi.advanceTimersByTime(100);
      pointer(wrapper, "pointermove", { clientX: 104, clientY: 104 }); // 5.7 px: still a press
      vi.advanceTimersByTime(100);
      pointer(wrapper, "pointermove", { clientX: 100, clientY: 109 }); // 9 px: scroll
      vi.advanceTimersByTime(1000);
      expect(wrapper.emitted("select")).toBeUndefined();
    });

    it("is cancelled when the browser takes over the gesture (pointercancel)", () => {
      const wrapper = mountItem();
      pointer(wrapper, "pointerdown");
      pointer(wrapper, "pointercancel");
      vi.advanceTimersByTime(1000);
      expect(wrapper.emitted("select")).toBeUndefined();
    });

    it("ignores the mouse: desktop uses the hover checkbox", () => {
      const wrapper = mountItem();
      pointer(wrapper, "pointerdown", { pointerType: "mouse" });
      vi.advanceTimersByTime(1000);
      expect(wrapper.emitted("select")).toBeUndefined();
    });

    it("does nothing extra while already selecting", () => {
      const wrapper = mountItem({ selecting: true });
      pointer(wrapper, "pointerdown");
      vi.advanceTimersByTime(1000);
      expect(wrapper.emitted("select")).toBeUndefined();
    });

    it("suppresses the touch context menu but not the mouse one", () => {
      const wrapper = mountItem();
      pointer(wrapper, "pointerdown");
      const touchMenu = new Event("contextmenu", { bubbles: true, cancelable: true });
      wrapper.get('[data-test="body"]').element.dispatchEvent(touchMenu);
      expect(touchMenu.defaultPrevented).toBe(true);

      pointer(wrapper, "pointerdown", { pointerType: "mouse" });
      const mouseMenu = new Event("contextmenu", { bubbles: true, cancelable: true });
      wrapper.get('[data-test="body"]').element.dispatchEvent(mouseMenu);
      expect(mouseMenu.defaultPrevented).toBe(false);
    });
  });
});
