// SPDX-License-Identifier: MIT
import { useTranslation } from 'react-i18next'

export function UseDefaultOption() {
  const { t } = useTranslation();
  return (
    <div data-testid="use-default-option" className="text-body">
      {t("onboarding.characterCard.useDefaultDesc")}
    </div>
  )
}
