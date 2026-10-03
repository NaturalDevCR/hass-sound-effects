import { createMemoryHistory, type RouteLocationNormalized } from "vue-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createAppRouter } from "@/router";

async function go(path: string) {
  const router = createAppRouter(createMemoryHistory());
  await router.push(path);
  return router.currentRoute.value;
}

describe("router", () => {
  it("serves the four top level views", async () => {
    expect((await go("/")).name).toBe("library");
    expect((await go("/upload")).name).toBe("upload");
    expect((await go("/organize")).name).toBe("organize");
    expect((await go("/system")).name).toBe("system");
  });

  it("nests the sound editor under Library so it stays mounted", async () => {
    const route = await go("/sounds/abc123");
    expect(route.name).toBe("sound");
    expect(route.params.id).toBe("abc123");
    expect(route.matched.map((r) => r.name)).toEqual(["library", "sound"]);
  });

  it("falls back to Library for unknown paths", async () => {
    expect((await go("/nope/at/all")).name).toBe("library");
  });

  it("gives each top level route a title key", async () => {
    expect((await go("/system")).matched[0]?.meta.titleKey).toBe("nav.system");
    expect((await go("/sounds/x")).matched[0]?.meta.titleKey).toBe("nav.library");
  });
});

describe("scrollBehavior", () => {
  const router = createAppRouter(createMemoryHistory());
  const location = (path: string) => router.resolve(path) as unknown as RouteLocationNormalized;
  const scroll = (to: string, from: string) =>
    router.options.scrollBehavior!(location(to), location(from), null);
  const stubMotion = (reduce: boolean) =>
    vi.stubGlobal("matchMedia", (query: string) => ({ matches: reduce && query.includes("reduced-motion") }));
  afterEach(() => vi.unstubAllGlobals());

  it("scrolls to anchors smoothly by default", async () => {
    stubMotion(false);
    expect(await scroll("/system#import", "/")).toEqual({ el: "#import", behavior: "smooth" });
  });

  it("jumps instead of animating when the user prefers reduced motion", async () => {
    stubMotion(true);
    expect(await scroll("/system#import", "/")).toEqual({ el: "#import", behavior: "auto" });
  });

  it("keeps Library's scroll when the editor opens, closes or the query changes", async () => {
    expect(await scroll("/sounds/a", "/")).toBe(false);
    expect(await scroll("/", "/sounds/a")).toBe(false);
    expect(await scroll("/?c=doors", "/")).toBe(false);
    expect(await scroll("/upload", "/")).toEqual({ top: 0 });
  });
});
