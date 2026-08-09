// SPDX-License-Identifier: MIT
import { afterEach, describe, expect, it } from "vitest";
import { initI18n } from "./i18nSetup";

describe("i18nSetup", () => {
  afterEach(async () => {
    const i18n = (await import("i18next")).default;
    await i18n.changeLanguage("en");
  });

  it("initializes with English by default", async () => {
    const i18n = await initI18n("en");
    expect(i18n.t("nav.chat")).toBe("Chat");
  });

  it("returns English fallback when key missing in chosen locale", async () => {
    const i18n = await initI18n("en");
    await i18n.changeLanguage("de");
    expect(i18n.t("nav.chat")).toBe("Chat");
  });

  it("init is idempotent", async () => {
    const a = await initI18n("en");
    const b = await initI18n("zh-Hans");
    expect(a).toBe(b);
  });

  it("interpolates single-brace placeholders", async () => {
    const i18n = await initI18n("en");
    expect(i18n.t("memory.msgsCount", { count: 3 })).toBe("3 msgs");
    expect(i18n.t("rateStars.rated", { score: 4 })).toBe("rated 4/5");
  });
});