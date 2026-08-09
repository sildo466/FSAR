// SPDX-License-Identifier: MIT
import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import en from "../locales/en.json";
import zhHans from "../locales/zh-Hans.json";
import zhHant from "../locales/zh-Hant.json";
import ja from "../locales/ja.json";
import de from "../locales/de.json";
import fr from "../locales/fr.json";

export const LOCALES = ["en", "zh-Hans", "zh-Hant", "ja", "de", "fr"] as const;
export type Locale = (typeof LOCALES)[number];

export const LOCALE_LABELS: Record<Locale, string> = {
  en: "English",
  "zh-Hans": "简体中文",
  "zh-Hant": "繁體中文",
  ja: "日本語",
  de: "Deutsch",
  fr: "Français",
};

export const LOCALE_FLAGS: Record<Locale, string> = {
  en: "🇬🇧",
  "zh-Hans": "🇨🇳",
  "zh-Hant": "🇭🇰",
  ja: "🇯🇵",
  de: "🇩🇪",
  fr: "🇫🇷",
};

const RESOURCES = {
  en: { translation: en },
  "zh-Hans": { translation: zhHans },
  "zh-Hant": { translation: zhHant },
  ja: { translation: ja },
  de: { translation: de },
  fr: { translation: fr },
} as const;

let initPromise: Promise<typeof i18n> | null = null;

export function isSupportedLocale(value: string): value is Locale {
  return (LOCALES as readonly string[]).includes(value);
}

export async function initI18n(initialLocale: string): Promise<typeof i18n> {
  if (initPromise) return initPromise;
  initPromise = (async () => {
    const startLocale = isSupportedLocale(initialLocale) ? initialLocale : "en";
    await i18n
      .use(initReactI18next)
      .init({
        resources: RESOURCES,
        lng: startLocale,
        fallbackLng: "en",
        interpolation: { prefix: "{", suffix: "}", escapeValue: false },
        react: { useSuspense: false },
        saveMissing: import.meta.env.DEV,
        missingKeyHandler: (lng, _ns, key) => {
          if (import.meta.env.DEV) {
            console.warn(`[i18n] missing key "${key}" in "${lng}"`);
          }
        },
      });
    return i18n;
  })();
  return initPromise;
}

export default i18n;