// SPDX-License-Identifier: Apache-2.0
import { useWizardState } from '../../../stores/onboarding'
import { Input } from '../../ui/primitives'

function lastSegment(url: string): string {
  return '/' + (url.split('/').filter(Boolean).pop() ?? 'v1')
}

export function BaseUrlField() {
  const value = useWizardState(s => s.data.provider.base_url)
  const setProviderField = useWizardState(s => s.setProviderField)

  return (
    <div className="flex flex-col gap-1">
      <label className="text-caption text-text-muted" htmlFor="provider-base-url">
        Base URL <span className="text-text">(fill to {lastSegment(value)})</span>
      </label>
      <Input
        id="provider-base-url"
        type="text"
        value={value}
        onChange={e => setProviderField('base_url', e.target.value)}
        placeholder="https://api.example.com/v1"
        data-testid="base-url-input"
      />
    </div>
  )
}
