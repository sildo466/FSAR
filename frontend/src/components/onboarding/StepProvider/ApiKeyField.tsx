// SPDX-License-Identifier: MIT
import { useTranslation } from 'react-i18next'
import { useWizardState } from '../../../stores/onboarding'
import { Input } from '../../ui/primitives'

export function ApiKeyField({ required }: { required: boolean }) {
  const { t } = useTranslation();
  const value = useWizardState(s => s.data.provider.api_key)
  const setProviderField = useWizardState(s => s.setProviderField)

  if (!required) return null

  return (
    <div className="flex flex-col gap-1">
      <label className="text-caption text-text-muted" htmlFor="provider-api-key">{t("onboarding.provider.apiKey")}</label>
      <Input
        id="provider-api-key"
        type="password"
        value={value}
        onChange={e => setProviderField('api_key', e.target.value)}
        placeholder="sk-..."
        data-testid="api-key-input"
      />
    </div>
  )
}
