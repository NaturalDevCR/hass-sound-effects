import { describe, expect, it } from "vitest";
import {
  IDENTITY,
  clampRecipe,
  clipLength,
  isIdentity,
  recipesEqual,
  validateRecipe,
} from "@/lib/recipe";
import type { Recipe } from "@/api/types";

const base = (patch: Partial<Recipe> = {}): Recipe => ({ ...IDENTITY, ...patch });

describe("IDENTITY / isIdentity", () => {
  it("is the documented identity recipe", () => {
    expect(IDENTITY).toEqual({
      trim_start: 0,
      trim_end: null,
      gain_db: 0,
      fade_in: 0,
      fade_out: 0,
      profile_id: null,
    });
    expect(isIdentity(IDENTITY)).toBe(true);
  });

  it("is false as soon as any field deviates", () => {
    expect(isIdentity(base({ trim_start: 0.5 }))).toBe(false);
    expect(isIdentity(base({ trim_end: 3 }))).toBe(false);
    expect(isIdentity(base({ gain_db: 1 }))).toBe(false);
    expect(isIdentity(base({ fade_in: 0.2 }))).toBe(false);
    expect(isIdentity(base({ fade_out: 0.2 }))).toBe(false);
    expect(isIdentity(base({ profile_id: "standard" }))).toBe(false);
  });

  it("cannot be mutated by accident", () => {
    expect(Object.isFrozen(IDENTITY)).toBe(true);
  });
});

describe("clipLength", () => {
  it("uses the full duration when trim_end is null", () => {
    expect(clipLength(IDENTITY, 10)).toBe(10);
    expect(clipLength(base({ trim_start: 2 }), 10)).toBe(8);
  });

  it("uses trim_end when set and never exceeds the file", () => {
    expect(clipLength(base({ trim_start: 2, trim_end: 5 }), 10)).toBe(3);
    expect(clipLength(base({ trim_end: 99 }), 10)).toBe(10);
  });

  it("never goes negative", () => {
    expect(clipLength(base({ trim_start: 7, trim_end: 4 }), 10)).toBe(0);
    expect(clipLength(base({ trim_start: 20 }), 10)).toBe(0);
  });
});

describe("validateRecipe", () => {
  it("accepts the identity recipe and a sensible edit", () => {
    expect(validateRecipe(IDENTITY, 10)).toEqual([]);
    expect(
      validateRecipe(base({ trim_start: 1, trim_end: 6, gain_db: 3, fade_in: 0.5, fade_out: 1 }), 10),
    ).toEqual([]);
  });

  it("flags start >= end", () => {
    expect(validateRecipe(base({ trim_start: 5, trim_end: 5 }), 10)).toContain("recipe.error.trimOrder");
    expect(validateRecipe(base({ trim_start: 6, trim_end: 2 }), 10)).toContain("recipe.error.trimOrder");
    expect(validateRecipe(base({ trim_start: 10 }), 10)).toContain("recipe.error.trimOrder");
  });

  it("flags a negative start and an end past the file", () => {
    expect(validateRecipe(base({ trim_start: -1 }), 10)).toContain("recipe.error.trimStart");
    expect(validateRecipe(base({ trim_end: 12 }), 10)).toContain("recipe.error.trimEnd");
  });

  it("flags fades that do not fit in the clip", () => {
    const r = base({ trim_start: 0, trim_end: 2, fade_in: 1.5, fade_out: 1 });
    expect(validateRecipe(r, 10)).toContain("recipe.error.fadeLong");
    expect(validateRecipe(base({ fade_in: -1 }), 10)).toContain("recipe.error.fadeNegative");
  });

  it("flags gain outside -24..+24 dB", () => {
    expect(validateRecipe(base({ gain_db: 25 }), 10)).toContain("recipe.error.gainRange");
    expect(validateRecipe(base({ gain_db: -24.5 }), 10)).toContain("recipe.error.gainRange");
    expect(validateRecipe(base({ gain_db: 24 }), 10)).toEqual([]);
  });

  it("flags non-finite numbers", () => {
    expect(validateRecipe(base({ gain_db: Number.NaN }), 10)).toContain("recipe.error.number");
  });
});

describe("clampRecipe", () => {
  it("keeps values in range without mutating the input", () => {
    const input = base({ trim_start: -3, trim_end: 99, gain_db: 40, fade_in: -1, fade_out: 0.5 });
    const out = clampRecipe(input, 10);
    expect(out).toEqual(base({ trim_start: 0, trim_end: 10, gain_db: 24, fade_in: 0, fade_out: 0.5 }));
    expect(input.gain_db).toBe(40);
    expect(validateRecipe(out, 10)).toEqual([]);
  });

  it("keeps trim_end after trim_start and fades inside the clip", () => {
    const out = clampRecipe(base({ trim_start: 8, trim_end: 3, fade_in: 4, fade_out: 4 }), 10);
    expect(out.trim_end).not.toBeNull();
    expect(out.trim_end as number).toBeGreaterThanOrEqual(out.trim_start);
    expect(out.trim_end as number).toBeLessThanOrEqual(10);
    expect(out.fade_in + out.fade_out).toBeLessThanOrEqual(clipLength(out, 10) + 1e-9);
  });

  it("leaves a null trim_end alone and preserves the profile", () => {
    const out = clampRecipe(base({ profile_id: "voice", trim_start: 20 }), 10);
    expect(out.trim_end).toBeNull();
    expect(out.trim_start).toBe(10);
    expect(out.profile_id).toBe("voice");
  });

  it("returns identity-equal output for already valid recipes", () => {
    const r = base({ trim_start: 1, trim_end: 4, gain_db: -2, fade_in: 0.3, fade_out: 0.3 });
    expect(clampRecipe(r, 10)).toEqual(r);
  });
});

describe("recipesEqual", () => {
  it("compares every field, treating null trim_end explicitly", () => {
    expect(recipesEqual(IDENTITY, base())).toBe(true);
    expect(recipesEqual(base({ trim_end: null }), base({ trim_end: 4 }))).toBe(false);
    expect(recipesEqual(base({ profile_id: "a" }), base({ profile_id: "b" }))).toBe(false);
  });

  it("ignores floating point noise", () => {
    expect(recipesEqual(base({ gain_db: 0.1 + 0.2 }), base({ gain_db: 0.3 }))).toBe(true);
    expect(recipesEqual(base({ gain_db: 0.5 }), base({ gain_db: 0.6 }))).toBe(false);
  });
});
