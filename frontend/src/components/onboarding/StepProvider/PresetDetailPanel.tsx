// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from 'react'
import { useWizardState } from '../../../stores/onboarding'
import { useWS } from '../../../stores/ws'
import { ApiKeyField } from './ApiKeyField'
import { BaseUrlField } from './BaseUrlField'
import { ModelField } from './ModelField'
import { TestConnectionButton } from './TestConnectionButton'
import type { Preset } from './types'

let cachedPresets: Preset[] | null = null

function findPreset(presets: Preset[] | null, presetId: string | null): Preset | null {
  if (!presets || !presetId) return null
  return presets.find(preset => preset.id === presetId) ?? null
}

export function PresetDetailPanel() {
  const presetId = useWizardState(s => s.data.provider.preset_id)
  const client = useWS(s => s.client)
  const [presets, setPresets] = useState<Preset[] | null>(cachedPresets)

  useEffect(() => {
    if (!client) return

    return client.on((msg) => {
      if (msg.type !== 'provider.presets') return
      const next = msg.presets as unknown as Preset[]
      cachedPresets = next
      setPresets(next)
    })
  }, [client])

  useEffect(() => {
    if (!presetId || cachedPresets) return
    useWS.getState().send({ type: 'provider.list_presets' })
  }, [client, presetId])

  if (!presetId) return <div className="text-text-muted">Select a preset to configure</div>

  const preset = findPreset(presets, presetId)
  if (!preset) return <div data-testid="preset-detail-loading">Loading preset...</div>

  return (
    <div className="border border-border p-4 flex flex-col gap-3" data-testid="preset-detail-panel">
      <div className="text-h2">{preset.label}</div>
      <ApiKeyField required={preset.api_key_required} />
      <BaseUrlField />
      <ModelField preset={preset} />
      <TestConnectionButton apiKeyRequired={preset.api_key_required} />
    </div>
  )
}
