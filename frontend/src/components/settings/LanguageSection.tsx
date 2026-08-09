// SPDX-License-Identifier: MIT
import { useTranslation } from "react-i18next";
import { LOCALES, LOCALE_FLAGS, LOCALE_LABELS } from "../../lib/i18nSetup";
import { useLocale } from "../../stores/locale";
import { Capsule, Pill } from "../ui/primitives";

export function LanguageSection() {
  const { t } = useTranslation();
  const locale = useLocale((s) => s.locale);
  const setLocale = useLocale((s) => s.setLocale);

  return (
    <Capsule className="flex flex-col gap-2">
      <h2 className="font-display text-sm font-semibold">{t("settings.style.language")}</h2>
      <p className="text-[12px] text-text-muted">{t("settings.style.languageHint")}</p>
      <div className="grid grid-cols-3 gap-2">
        {LOCALES.map((code) => (
          <Pill
            key={code}
            data-active={locale === code ? "true" : undefined}
            onClick={() => void setLocale(code)}
            variant={locale === code ? "primary" : "glass"}
            size="sm"
            className="justify-start"
          >
            <span className="mr-1">{LOCALE_FLAGS[code]}</span>
            <span>{LOCALE_LABELS[code]}</span>
          </Pill>
        ))}
      </div>
    </Capsule>
  );
}