import { describe, expect, it } from "vitest";
import { addTag, slugifyTag } from "@/lib/tags";

describe("slugifyTag", () => {
  it("lowercases, strips accents and joins words with underscores like the backend slugify", () => {
    expect(slugifyTag("ES")).toBe("es");
    expect(slugifyTag("  León Infinito ")).toBe("leon_infinito");
    expect(slugifyTag("Intro / Entrada!!")).toBe("intro_entrada");
    expect(slugifyTag("a---b")).toBe("a_b");
  });

  it("trims separators and caps the length at 48", () => {
    expect(slugifyTag("__x__")).toBe("x");
    expect(slugifyTag("a".repeat(80))).toHaveLength(48);
    expect(slugifyTag("a".repeat(47) + "-b")).toBe("a".repeat(47)); // never ends in a separator
  });

  it("returns an empty string when nothing usable is left", () => {
    expect(slugifyTag("")).toBe("");
    expect(slugifyTag(" ¡¿ ")).toBe("");
  });
});

describe("addTag", () => {
  it("appends the slug and ignores empty or duplicate tags", () => {
    expect(addTag(["es"], "En")).toEqual(["es", "en"]);
    expect(addTag(["es"], " ES ")).toEqual(["es"]);
    expect(addTag(["es"], "!!!")).toEqual(["es"]);
  });
});
