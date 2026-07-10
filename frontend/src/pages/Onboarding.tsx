// SPDX-License-Identifier: Apache-2.0
import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useWS } from '../stores/ws'
import { useWizardState } from '../stores/onboarding'
import { WizardShell } from '../components/onboarding/WizardShell'
import { StepProvider } from '../components/onboarding/StepProvider'
import { StepUserCard } from '../components/onboarding/StepUserCard'
import { StepCharacterCard } from '../components/onboarding/StepCharacterCard'
import { StepFooter } from '../components/onboarding/StepFooter'

const STEP_ORDER = ['provider', 'user_card', 'character_card'] as const
type WizardStepName = typeof STEP_ORDER[number]

export function Onboarding() {
  const step = useWizardState(s => s.step)
  const currentIndex = useWizardState(s => s.current_step_index)
  const data = useWizardState(s => s.data)
  const navigate = useNavigate()
  const config = useWS(s => s.config) as Record<string, unknown> | null
  const send = useWS(s => s.send)
  const client = useWS(s => s.client)
  const onboardingState = config?.onboarding as
    | { current_step: string | null; required: boolean; completed: boolean; completed_steps: string[] }
    | undefined

  useEffect(() => {
    const current = onboardingState?.current_step
    if (current && (STEP_ORDER as readonly string[]).includes(current)) {
      const idx = STEP_ORDER.indexOf(current as WizardStepName) as 0 | 1 | 2
      useWizardState.setState({
        current_step_index: idx,
        step: current as WizardStepName,
      })
    }
  }, [onboardingState?.current_step])

  useEffect(() => {
    return client?.on((msg) => {
      if (msg.type === 'onboarding.completed') {
        navigate('/chat', { replace: true })
      }
    })
  }, [client, navigate])

  const handleProviderNext = () => {
    const p = data.provider
    send({
      type: 'provider.create_builtin',
      preset_id: p.preset_id ?? '',
      label: p.preset_id ?? '',
      api_key: p.api_key,
      base_url: p.base_url,
      model: p.model,
    })
    send({ type: 'onboarding.complete_step', step: 'provider', data: { preset_id: p.preset_id } })
    useWizardState.getState().next()
  }

  const handleUserCardNext = () => {
    const u = data.user_card
    send({
      type: 'card.upsert',
      kind: 'user',
      card: { name: u.name, description: u.bio },
    })
    send({ type: 'onboarding.complete_step', step: 'user_card', data: { name: u.name } })
    useWizardState.getState().next()
  }

  const handleFinish = () => {
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
        },
      })
    }
    send({ type: 'onboarding.complete_step', step: 'character_card', data: { mode: c.mode } })
    send({ type: 'onboarding.complete' })
  }

  return (
    <WizardShell>
      <div data-testid={`step-${step}`}>
        {step === 'provider' && <StepProvider />}
        {step === 'user_card' && <StepUserCard />}
        {step === 'character_card' && <StepCharacterCard />}
      </div>
      <StepFooter
        onNext={currentIndex === 0 ? handleProviderNext : currentIndex === 1 ? handleUserCardNext : undefined}
        onFinish={currentIndex === 2 ? handleFinish : undefined}
      />
    </WizardShell>
  )
}
