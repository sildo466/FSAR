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
  const navigate = useNavigate()
  const config = useWS(s => s.config) as Record<string, unknown> | null
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
    if (step === 'completed') {
      navigate('/chat', { replace: true })
    }
  }, [step, navigate])

  return (
    <WizardShell>
      <div data-testid={`step-${step}`}>
        {step === 'provider' && <StepProvider />}
        {step === 'user_card' && <StepUserCard />}
        {step === 'character_card' && <StepCharacterCard />}
      </div>
      <StepFooter />
    </WizardShell>
  )
}