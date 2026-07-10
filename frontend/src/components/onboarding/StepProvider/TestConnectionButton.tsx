// SPDX-License-Identifier: Apache-2.0
import { useState } from 'react'
import { useWizardState } from '../../../stores/onboarding'
import { useWS } from '../../../stores/ws'

interface Props {
  apiKeyRequired: boolean
}

export function TestConnectionButton({ apiKeyRequired }: Props) {
  const data = useWizardState(s => s.data.provider)
  const setProviderField = useWizardState(s => s.setProviderField)
  const client = useWS(s => s.client)
  const [testing, setTesting] = useState(false)

  const onClick = () => {
    if (!data.preset_id || testing) return

    setTesting(true)
    setProviderField('test_result', null)
    let unsubscribe: (() => void) | undefined
    const timeout = window.setTimeout(() => {
      unsubscribe?.()
      setProviderField('test_result', { ok: false, error: 'timeout', latency_ms: null })
      setTesting(false)
    }, 6000)

    unsubscribe = client?.on((msg) => {
      if (msg.type !== 'provider.test_result') return
      window.clearTimeout(timeout)
      unsubscribe?.()
      setProviderField('test_result', { ok: msg.ok, error: msg.error, latency_ms: msg.latency_ms })
      setTesting(false)
    })

    useWS.getState().send({
      type: 'provider.test_connection',
      preset_id: data.preset_id,
      base_url: data.base_url,
      api_key: data.api_key,
      model: data.model,
    } as any)
  }

  const result = data.test_result
  const disabled = testing || !data.preset_id || !data.base_url || !data.model || (apiKeyRequired && !data.api_key)

  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        onClick={onClick}
        disabled={disabled}
        data-testid="test-connection-button"
        className="px-3 py-1 border border-border disabled:opacity-50"
      >
        {testing ? 'Testing...' : 'Test connection'}
      </button>
      {result?.ok && <span data-testid="test-result-ok" className="text-caption">✓ {result.latency_ms}ms</span>}
      {result && !result.ok && <span data-testid="test-result-error" className="text-caption">✗ {result.error}</span>}
    </div>
  )
}
