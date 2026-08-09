// SPDX-License-Identifier: MIT
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useWizardState } from '../../../stores/onboarding'
import { useWS } from '../../../stores/ws'
import type { Preset } from './types'

export function ModelField({ preset }: { preset: Preset }) {
  const { t } = useTranslation();
  const value = useWizardState(s => s.data.provider.model)
  const setProviderField = useWizardState(s => s.setProviderField)
  const client = useWS(s => s.client)
  const [models, setModels] = useState<string[]>([])
  const [loading, setLoading] = useState(false)

  const canLoad = preset.model_list_url_suffix !== null

  useEffect(() => {
    setModels([])
    setLoading(false)
  }, [preset.id])

  const onLoad = () => {
    if (!canLoad || loading) return

    setLoading(true)
    const provider = useWizardState.getState().data.provider
    let unsubscribe: (() => void) | undefined
    const timeout = window.setTimeout(() => {
      unsubscribe?.()
      setLoading(false)
    }, 6000)

    unsubscribe = client?.on((msg) => {
      if (msg.type !== 'provider.models') return
      window.clearTimeout(timeout)
      unsubscribe?.()
      setModels(msg.models || [])
      setLoading(false)
    })

    useWS.getState().send({
      type: 'provider.fetch_models',
      preset_id: preset.id,
      base_url: provider.base_url,
      api_key: provider.api_key,
    } as any)
  }

  return (
    <div className="flex flex-col gap-1">
      <label className="text-caption text-text-muted" htmlFor="provider-model">{t("settings.embedding.model")}</label>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onLoad}
          disabled={!canLoad || loading}
          title={!canLoad ? t("onboarding.provider.noModelListApi") : undefined}
          data-testid="load-models-button"
          className="px-3 py-1 border border-border disabled:opacity-50"
        >
          {loading ? t("onboarding.provider.loadingModelList") : t("onboarding.provider.loadModelList")}
        </button>
        {models.length > 0 && (
          <select
            data-testid="model-select"
            value={value}
            onChange={e => setProviderField('model', e.target.value)}
            className="border border-border px-2 py-1 bg-surface"
          >
            <option value="">{t("onboarding.provider.pickModel")}</option>
            {models.map(model => <option key={model} value={model}>{model}</option>)}
          </select>
        )}
        <input
          id="provider-model"
          type="text"
          value={value}
          onChange={e => setProviderField('model', e.target.value)}
          placeholder={t("onboarding.provider.modelIdPlaceholder")}
          data-testid="model-input"
          className="border border-border px-2 py-1 bg-surface flex-1"
        />
      </div>
    </div>
  )
}
