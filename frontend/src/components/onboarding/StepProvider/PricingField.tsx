// SPDX-License-Identifier: MIT
import { useTranslation } from 'react-i18next'
import { useWizardState } from '../../../stores/onboarding'

export function PricingField() {
  const { t } = useTranslation();
  const inputPer1m = useWizardState(s => s.data.provider.input_per_1m)
  const outputPer1m = useWizardState(s => s.data.provider.output_per_1m)
  const setProviderField = useWizardState(s => s.setProviderField)

  return (
    <div className="flex flex-col gap-1">
      <label className="text-caption text-text-muted">
        {t("onboarding.provider.pricingLabel")}
      </label>
      <div className="flex items-center gap-2">
        <input
          id="provider-input-per-1m"
          type="number"
          inputMode="decimal"
          min="0"
          step="0.01"
          value={inputPer1m}
          onChange={e => setProviderField('input_per_1m', e.target.value)}
          placeholder="0.15"
          data-testid="provider-input-per-1m"
          className="w-24 border border-border px-2 py-1 bg-surface font-mono"
        />
        <span className="text-caption text-text-muted">{t("onboarding.provider.pricingIn")}</span>
        <input
          id="provider-output-per-1m"
          type="number"
          inputMode="decimal"
          min="0"
          step="0.01"
          value={outputPer1m}
          onChange={e => setProviderField('output_per_1m', e.target.value)}
          placeholder="0.60"
          data-testid="provider-output-per-1m"
          className="w-24 border border-border px-2 py-1 bg-surface font-mono"
        />
        <span className="text-caption text-text-muted">{t("onboarding.provider.pricingOut")}</span>
        <span className="text-caption text-text-muted">{t("onboarding.provider.pricingLeaveBlank")}</span>
      </div>
    </div>
  )
}
