// SPDX-License-Identifier: MIT
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useWS } from '../stores/ws'
import { useWizardState } from '../stores/onboarding'
import { WizardShell } from '../components/onboarding/WizardShell'
import { StepProvider } from '../components/onboarding/StepProvider'
import { StepEmbedding } from '../components/onboarding/StepEmbedding'
import { StepUserCard } from '../components/onboarding/StepUserCard'
import { StepCharacterCard } from '../components/onboarding/StepCharacterCard'
import { StepTts } from '../components/onboarding/StepTts'
import { StepAsr } from '../components/onboarding/StepAsr'
import { StepFooter } from '../components/onboarding/StepFooter'
import { LanguagePicker } from '../components/onboarding/LanguagePicker'
import { AnimatePresence, motion } from 'framer-motion'
import { ArrowRight } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { BreathGlow, Pill } from '../components/ui/primitives'

const STEP_ORDER = ['provider', 'embedding', 'character_card', 'user_card', 'tts', 'asr'] as const
type WizardStepName = typeof STEP_ORDER[number]

export function Onboarding() {
  const { t } = useTranslation();
  const [welcomed, setWelcomed] = useState(false)
  const [finishing, setFinishing] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const restored = useRef(false)
  const step = useWizardState(s => s.step)
  const currentIndex = useWizardState(s => s.current_step_index)
  const data = useWizardState(s => s.data)
  const providerSelected = data.provider.preset_id !== null
  const navigate = useNavigate()
  const config = useWS(s => s.config) as Record<string, unknown> | null
  const send = useWS(s => s.send)
  const client = useWS(s => s.client)
  const onboardingState = config?.onboarding as
    | { current_step: string | null; required: boolean; completed: boolean; completed_steps: string[] }
    | undefined

  useEffect(() => {
    if ((onboardingState?.completed_steps?.length ?? 0) > 0) {
      setWelcomed(true)
    }
  }, [onboardingState?.completed_steps])

  useEffect(() => {
    if (restored.current) return
    const current = onboardingState?.current_step
    if (current && (STEP_ORDER as readonly string[]).includes(current)) {
      const idx = STEP_ORDER.indexOf(current as WizardStepName)
      useWizardState.setState({
        current_step_index: idx,
        step: current as WizardStepName,
      })
      restored.current = true
    }
  }, [onboardingState?.current_step])

  useEffect(() => {
    return client?.on((msg) => {
      if (msg.type === 'onboarding.completed') {
        setFinishing(true)
        window.setTimeout(() => navigate('/chat', { replace: true }), 650)
      } else if (msg.type === 'onboarding.error') {
        setFinishing(false)
        setSubmitError(msg.message)
      }
    })
  }, [client, navigate])

  const handleProviderNext = async () => {
    const p = data.provider
    const advanced = await useWizardState.getState().next()
    if (!advanced) return
    const inNum = parseFloat(p.input_per_1m)
    const outNum = parseFloat(p.output_per_1m)
    const pricing = Number.isFinite(inNum) || Number.isFinite(outNum)
      ? {
          input_per_1m: Number.isFinite(inNum) ? inNum : 0,
          output_per_1m: Number.isFinite(outNum) ? outNum : 0,
        }
      : undefined
    send({
      type: 'provider.create_builtin',
      preset_id: p.preset_id ?? '',
      label: p.preset_id ?? '',
      api_key: p.api_key,
      base_url: p.base_url,
      model: p.model,
      pricing,
    })
    send({ type: 'onboarding.complete_step', step: 'provider', data: { preset_id: p.preset_id } })
  }

  const handleEmbeddingNext = () => {
    const e = data.embedding
    if (e.provider) {
      send({
        type: 'embedding.upsert',
        provider: e.provider,
        base_url: e.base_url,
        model: e.model,
        api_key: e.provider === 'openai' ? e.api_key : '',
      })
    }
    send({ type: 'onboarding.complete_step', step: 'embedding', data: { provider: e.provider || 'skipped' } })
    useWizardState.getState().next()
  }

  const saveUserCard = () => {
    const u = data.user_card
    send({
      type: 'card.upsert',
      kind: 'user',
      card: { name: u.name, description: u.bio },
    })
    send({ type: 'onboarding.complete_step', step: 'user_card', data: { name: u.name } })
  }

  const handleCharacterNext = () => {
    const c = data.character_card
    if (c.mode === 'use_default') {
      send({ type: 'card.set_default', kind: 'character', id: 1 })
    } else if (c.mode === 'pick_existing' && c.picked_card_id) {
      send({ type: 'card.set_default', kind: 'character', id: c.picked_card_id })
    } else if (c.mode === 'create_new') {
      send({
        type: 'card.upsert',
        kind: 'character',
        card: {
          name: c.new_card.name,
          description: c.new_card.personality,
          personality: c.new_card.personality,
          system_prompt_override: c.new_card.system_prompt_override,
          tts_voice: c.new_card.tts_voice,
          tts_autoplay_on_card: c.new_card.tts_autoplay_on_card ? 1 : 0,
        },
      })
    }
    send({ type: 'onboarding.complete_step', step: 'character_card', data: { mode: c.mode } })
    useWizardState.getState().next()
  }

  const handleUserNext = async () => {
    const u = data.user_card
    const advanced = await useWizardState.getState().next()
    if (!advanced || !u.name.trim() || !u.bio.trim()) return
    saveUserCard()
  }

  const finishSpeech = () => {
    setSubmitError(null)
    send({ type: 'onboarding.complete' })
  }

  const handleSkipSetup = () => {
    setSubmitError(null)
    send({ type: 'onboarding.skip' } as never)
  }

  if (!welcomed) {
    return <div className="fixed inset-0 z-50 flex items-center justify-center overflow-hidden bg-bg px-6"><div className="app-backdrop" aria-hidden="true"><div className="app-orb one" /><div className="app-orb two" /><div className="app-orb three" /></div><motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="relative z-10 flex max-w-xl flex-col items-center text-center"><BreathGlow className="mb-10 flex h-16 w-16 items-center justify-center rounded-full glass"><img src="/assets/icons/blackhole.svg" alt="FSAR" className="h-12 w-auto" /></BreathGlow><p className="mb-4 font-mono text-[10px] uppercase tracking-[0.24em] text-text-faint">{t("onboarding.welcome.tagline")}</p><h1 className="font-display text-5xl italic sm:text-6xl">{t("onboarding.welcome.title")}</h1><p className="mt-5 max-w-md text-sm leading-6 text-text-muted">{t("onboarding.welcome.subtitle")}</p><LanguagePicker /><Pill onClick={() => setWelcomed(true)} variant="primary" size="lg" icon={<ArrowRight size={16} />} className="mt-7">{t("onboarding.welcome.start")}</Pill></motion.div></div>
  }

  if (finishing) {
    return <div className="fixed inset-0 z-50 flex items-center justify-center bg-bg"><BreathGlow className="text-center"><div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-text text-bg">✓</div><p className="font-display text-2xl italic">{t("onboarding.complete.title")}</p><p className="mt-2 text-sm text-text-muted">{t("onboarding.complete.loading")}</p></BreathGlow></div>
  }

  return (
    <WizardShell onSkipSetup={handleSkipSetup}>
      <AnimatePresence mode="wait"><motion.div key={step} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} data-testid={`step-${step}`}>
        {step === 'provider' && <StepProvider />}
        {step === 'embedding' && <StepEmbedding />}
        {step === 'user_card' && <StepUserCard />}
        {step === 'character_card' && <StepCharacterCard />}
        {step === 'tts' && <StepTts onNext={() => { void useWizardState.getState().next() }} onSkip={() => { void useWizardState.getState().next() }} />}
        {step === 'asr' && <StepAsr onNext={finishSpeech} onSkip={finishSpeech} />}
      </motion.div></AnimatePresence>
      {submitError && <div role="alert" className="glass mx-auto mb-4 max-w-6xl rounded-2xl border-red-500 bg-red-500/10 px-4 py-3 text-sm text-red-500">{submitError}</div>}
      {currentIndex < 4 && !(currentIndex === 0 && !providerSelected) && <StepFooter
        onNext={
          currentIndex === 0 ? handleProviderNext
          : currentIndex === 1 ? handleEmbeddingNext
          : currentIndex === 2 ? handleCharacterNext
          : currentIndex === 3 ? handleUserNext
          : undefined
        }
        onSkip={currentIndex === 1 ? handleEmbeddingNext : currentIndex === 2 ? handleCharacterNext : undefined}
      />}
    </WizardShell>
  )
}
