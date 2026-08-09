// SPDX-License-Identifier: MIT
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useLocale } from "./locale";

const send = vi.fn();

vi.mock("./ws", () => ({
  useWS: {
    getState: () => ({ send }),
  },
}));

import i18n, { initI18n } from "../lib/i18nSetup";

describe("useLocale store", () => {
  beforeEach(async () => {
    send.mockReset();
    await initI18n("en");
    await i18n.changeLanguage("en");
    useLocale.setState({ locale: "en", pendingLocale: null });
  });

  afterEach(() => {
    send.mockReset();
  });

  it("setLocale updates store and sends to backend", async () => {
    await useLocale.getState().setLocale("zh-Hans");
    expect(useLocale.getState().locale).toBe("zh-Hans");
    expect(send).toHaveBeenCalledWith({
      type: "style.set_locale",
      locale: "zh-Hans",
    });
  });

  it("unsupported locale is rejected", async () => {
    await expect(useLocale.getState().setLocale("klingon")).rejects.toThrow();
    expect(useLocale.getState().locale).toBe("en");
  });

  it("hydrateFromConfig updates locale", async () => {
    await useLocale.getState().hydrateFromConfig("ja");
    expect(useLocale.getState().locale).toBe("ja");
    expect(i18n.language).toBe("ja");
  });

  it("hydrateFromConfig ignores unsupported", async () => {
    await useLocale.getState().hydrateFromConfig("xx");
    expect(useLocale.getState().locale).toBe("en");
  });
});