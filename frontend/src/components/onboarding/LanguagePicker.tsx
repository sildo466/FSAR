// SPDX-License-Identifier: MIT
import { useTranslation } from "react-i18next";
import { LOCALES, LOCALE_FLAGS, LOCALE_LABELS } from "../../lib/i18nSetup";
import { useLocale } from "../../stores/locale";

export function LanguagePicker() {
  const { t } = useTranslation();
  const locale = useLocale((s) => s.locale);
  const setLocale = useLocale((s) => s.setLocale);

  return (
    <div className="glass mt-9 w-full rounded-[24px] px-5 py-4 text-left">
      <span className="text-[10px] uppercase tracking-[0.16em] text-text-faint">
        {t("onboarding.welcome.language")}
      </span>
      <div className="mt-3 grid grid-cols-2 gap-2">
        {LOCALES.map((code) => (
          <button
            key={code}
            type="button"
            onClick={() => void setLocale(code)}
            data-active={locale === code ? "true" : undefined}
            className="flex items-center gap-2 rounded-xl px-3 py-2 text-sm transition hover:bg-glass"
          >
            <span>{LOCALE_FLAGS[code]}</span>
            <span>{LOCALE_LABELS[code]}</span>
            {locale === code && (
              <span className="ml-auto text-[10px] uppercase tracking-[0.16em] text-text-faint">
                ✓
              </span>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}