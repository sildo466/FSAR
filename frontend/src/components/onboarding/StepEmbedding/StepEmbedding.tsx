// SPDX-License-Identifier: MIT
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useWizardState } from '../../../stores/onboarding'
import { useWS } from '../../../stores/ws'
import { AnimatePresence, motion } from 'framer-motion'
import { Capsule, Input, Pill } from '../../ui/primitives'

interface EmbedderDef {
  key: 'openai' | 'lmstudio' | 'ollama'
  label: string
  defaults: { base_url: string; model: string; needs_key: boolean }
}

const PROVIDERS: EmbedderDef[] = [
  { key: 'openai', label: 'OpenAI', defaults: { base_url: 'https://api.openai.com/v1', model: 'text-embedding-3-small', needs_key: true } },
  { key: 'lmstudio', label: 'LM Studio (local)', defaults: { base_url: 'http://localhost:1234/v1', model: 'text-embedding-embeddinggemma-300m-qat', needs_key: false } },
  { key: 'ollama', label: 'Ollama (local)', defaults: { base_url: 'http://localhost:11434/api', model: 'nomic-embed-text', needs_key: false } },
];

export function StepEmbedding() {
  const { t } = useTranslation();
  const data = useWizardState(s => s.data.embedding)
  const setField = useWizardState(s => s.setEmbeddingField)
  const send = useWS(s => s.send)
  const client = useWS(s => s.client)
  const [probing, setProbing] = useState(false)

  const choose = (key: EmbedderDef['key']) => {
    const def = PROVIDERS.find(p => p.key === key)
    if (!def) return
    setField('provider', key)
    setField('base_url', def.defaults.base_url)
    setField('model', def.defaults.model)
    setField('api_key', '')
    setField('probe_result', null)
  }

  const probe = () => {
    if (!data.provider) return
    setProbing(true)
    const onResult = (msg: any) => {
      if (msg.type !== 'embedding.probe_result') return
      setField('probe_result', { ok: msg.ok, error: msg.error ?? null, dim: msg.dim ?? null })
      setProbing(false)
    }
    const u = client?.on(onResult)
    send({
      type: 'embedding.probe',
      provider: data.provider,
      base_url: data.base_url || undefined,
      model: data.model || undefined,
      api_key: data.api_key || undefined,
    } as any)
    setTimeout(() => u?.(), 8000)
  }

  const def = PROVIDERS.find(p => p.key === data.provider)

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-5">
      <h2 className="font-display text-3xl italic">{t("onboarding.embedding.title")}</h2>
      <p className="text-caption text-text-muted max-w-2xl">
        {t("onboarding.embedding.description")}
      </p>

      <div className="glass flex gap-2 rounded-full p-1" data-testid="embedder-provider-tabs">
        {PROVIDERS.map(p => (
          <button
            key={p.key}
            type="button"
            onClick={() => choose(p.key)}
            data-testid={`embedder-provider-${p.key}`}
            data-active={data.provider === p.key}
            className={`relative flex-1 rounded-full px-4 py-2 text-center transition ${data.provider === p.key ? 'text-bg' : 'text-text-muted hover:text-text'}`}
          >
            {data.provider === p.key && <motion.span layoutId="embed-provider-pill" className="absolute inset-0 -z-10 rounded-full bg-text" />}
            <div className="text-body font-medium">{p.label}</div>
          </button>
        ))}
      </div>

      <AnimatePresence mode="wait">{data.provider && def && (
        <motion.div key={data.provider} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }}><Capsule className="flex flex-col gap-4" data-testid="embedder-detail-panel">
          {def.defaults.needs_key && (
            <div className="flex flex-col gap-1">
              <label className="text-caption text-text-muted" htmlFor="embedder-api-key">{t("settings.embedding.apiKey")}</label>
              <Input
                id="embedder-api-key"
                type="password"
                value={data.api_key}
                onChange={e => setField('api_key', e.target.value)}
                placeholder="sk-..."
                data-testid="embedder-api-key-input"
              />
            </div>
          )}
          <div className="flex flex-col gap-1">
            <label className="text-caption text-text-muted" htmlFor="embedder-base-url">{t("settings.embedding.baseUrl")}</label>
            <Input
              id="embedder-base-url"
              type="text"
              value={data.base_url}
              onChange={e => { setField('base_url', e.target.value); setField('probe_result', null) }}
              data-testid="embedder-base-url-input"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-caption text-text-muted" htmlFor="embedder-model">{t("settings.embedding.model")}</label>
            <Input
              id="embedder-model"
              type="text"
              value={data.model}
              onChange={e => { setField('model', e.target.value); setField('probe_result', null) }}
              data-testid="embedder-model-input"
            />
          </div>
          <div className="flex items-center gap-3 mt-1">
            <Pill
              type="button"
              onClick={probe}
              disabled={probing}
              data-testid="embedder-probe-button"
              variant="glass" loading={probing}
            >
              {probing ? t("settings.embedding.testing") : t("settings.embedding.testConnection")}
            </Pill>
            {data.probe_result && (
              <span className="text-caption" data-testid="embedder-probe-result">
                {data.probe_result.ok
                  ? t("onboarding.embedding.okDim", { dim: data.probe_result.dim ?? '?' })
                  : t("onboarding.embedding.failed", { error: data.probe_result.error ?? t("onboarding.embedding.unknownError") })}
              </span>
            )}
          </div>
        </Capsule></motion.div>
      )}</AnimatePresence>
    </div>
  )
}
