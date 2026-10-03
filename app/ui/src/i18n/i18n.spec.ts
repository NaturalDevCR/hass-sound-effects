import { beforeEach, describe, expect, it, vi } from "vitest";
import { en } from "@/i18n/en";
import { es } from "@/i18n/es";
import { detectLocale, translate, useI18n } from "@/i18n";

const placeholders = (text: string) => [...text.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();

describe("message catalogs", () => {
  it("has a Spanish entry for every English key and no extras", () => {
    const enKeys = Object.keys(en).sort();
    const esKeys = Object.keys(es).sort();
    expect(esKeys.filter((k) => !enKeys.includes(k))).toEqual([]);
    expect(enKeys.filter((k) => !esKeys.includes(k))).toEqual([]);
  });

  it("has no empty strings", () => {
    for (const [key, value] of [...Object.entries(en), ...Object.entries(es)]) {
      expect(value.trim(), key).not.toBe("");
    }
  });

  it("uses the same {placeholders} in both languages", () => {
    for (const key of Object.keys(en) as (keyof typeof en)[]) {
      expect(placeholders(es[key]), key).toEqual(placeholders(en[key]));
    }
  });

  it("uses flat dotted keys", () => {
    for (const key of Object.keys(en)) expect(key).toMatch(/^[a-z][A-Za-z0-9]*(\.[A-Za-z0-9]+)+$/);
  });
});

describe("useI18n", () => {
  beforeEach(() => {
    localStorage.clear();
    useI18n().setLocale("en");
  });

  it("interpolates {n}-style params and leaves unknown ones visible", () => {
    const { t } = useI18n();
    expect(t("jobs.active", { n: 3 })).toContain("3");
    expect(t("jobs.active", { n: 3 })).not.toContain("{n}");
    expect(translate("jobs.active")).toContain("{n}");
  });

  it("switches language reactively and persists the choice", () => {
    const { t, locale, setLocale } = useI18n();
    expect(t("nav.library")).toBe(en["nav.library"]);
    setLocale("es");
    expect(locale.value).toBe("es");
    expect(t("nav.library")).toBe(es["nav.library"]);
    expect(localStorage.getItem("sfx-locale")).toBe("es");
    expect(document.documentElement.lang).toBe("es");
  });

  it("survives a throwing localStorage", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(() => useI18n().setLocale("es")).not.toThrow();
    spy.mockRestore();
  });
});

describe("detectLocale", () => {
  beforeEach(() => localStorage.clear());

  it("prefers a stored choice", () => {
    localStorage.setItem("sfx-locale", "en");
    vi.spyOn(navigator, "language", "get").mockReturnValue("es-CR");
    expect(detectLocale()).toBe("en");
    vi.restoreAllMocks();
  });

  it("falls back to the browser language", () => {
    const lang = vi.spyOn(navigator, "language", "get");
    lang.mockReturnValue("es-CR");
    expect(detectLocale()).toBe("es");
    lang.mockReturnValue("ES");
    expect(detectLocale()).toBe("es");
    lang.mockReturnValue("en-US");
    expect(detectLocale()).toBe("en");
    lang.mockReturnValue("fr-FR");
    expect(detectLocale()).toBe("en");
    vi.restoreAllMocks();
  });

  it("ignores junk in storage", () => {
    localStorage.setItem("sfx-locale", "klingon");
    vi.spyOn(navigator, "language", "get").mockReturnValue("es-MX");
    expect(detectLocale()).toBe("es");
    vi.restoreAllMocks();
  });
});
