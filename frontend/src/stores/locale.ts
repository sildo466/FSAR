// SPDX-License-Identifier: MIT
import { create } from "zustand";
import i18n, { isSupportedLocale, type Locale } from "../lib/i18nSetup";
import { useWS } from "./ws";

interface LocaleState {
  locale: Locale;
  pendingLocale: Locale | null;
  setLocale: (next: string) => Promise<void>;
  hydrateFromConfig: (locale: string | undefined) => Promise<void>;
}

export const useLocale = create<LocaleState>((set, get) => ({
  locale: "en",
  pendingLocale: null,

  setLocale: async (next) => {
    if (!isSupportedLocale(next)) {
      throw new Error(`locale_unsupported: ${next}`);
    }
    const previous = get().locale;
    if (next === previous) return;
    set({ pendingLocale: next });
    await i18n.changeLanguage(next);
    if (typeof document !== "undefined") document.documentElement.lang = next;
    try {
      useWS.getState().send({ type: "style.set_locale", locale: next });
    } catch (err) {
      await i18n.changeLanguage(previous);
      if (typeof document !== "undefined") document.documentElement.lang = previous;
      set({ pendingLocale: null });
      throw new Error(`locale_change_failed: ${String(err)}`);
    }
    set({ locale: next, pendingLocale: null });
  },

  hydrateFromConfig: async (locale) => {
    if (!locale || !isSupportedLocale(locale)) return;
    const current = get().locale;
    if (locale === current) return;
    await i18n.changeLanguage(locale);
    if (typeof document !== "undefined") document.documentElement.lang = locale;
    set({ locale });
  },
}));