import { createMemoryHistory } from "vue-router";
import { describe, expect, it } from "vitest";
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
