import { expectTypeOf, it } from "vitest";
import type { CategoryPatch, SeasonInput } from "./types";

it("excludes category ordering from PATCH input", () => {
  expectTypeOf<"sort_order">().not.toMatchTypeOf<keyof CategoryPatch>();
});

it("requires non-null dates when creating a season", () => {
  expectTypeOf<SeasonInput["start"]>().toEqualTypeOf<string>();
  expectTypeOf<SeasonInput["end"]>().toEqualTypeOf<string>();
});
