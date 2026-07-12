// SPDX-License-Identifier: Apache-2.0
import { useState, useEffect } from 'react'
import { useWS } from '../../../stores/ws'
import { useWizardState } from '../../../stores/onboarding'
import { PresetCard } from './PresetCard'
import type { Preset } from './types'

export function PresetGrid() {
  const [presets, setPresets] = useState<Preset[] | null>(null)
  const send = useWS(s => s.send)
  const client = useWS(s => s.client)
  const presetId = useWizardState(s => s.data.provider.preset_id)
  const setProviderField = useWizardState(s => s.setProviderField)

  useEffect(() => {
    send({ type: 'provider.list_presets' })
    if (!client) return
    return client.on((msg) => {
      if (msg.type === 'provider.presets') {
        setPresets(msg.presets as unknown as Preset[])
      }
    })
  }, [send, client])

  if (!presets) return <div data-testid="preset-grid-loading">Loading presets...</div>

  const sorted = [...presets].sort((a, b) => a.order - b.order)

  return (
    <div data-testid="preset-grid" className="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-4">
      {sorted.map(p => (
        <PresetCard
          key={p.id}
          preset={p}
          selected={presetId === p.id}
          onSelect={() => {
            setProviderField('preset_id', p.id)
            setProviderField('api_key_required', p.api_key_required)
            setProviderField('base_url', p.default_base_url)
            setProviderField('api_key', '')
            setProviderField('model', '')
            setProviderField('test_result', null)
          }}
        />
      ))}
    </div>
  )
}
