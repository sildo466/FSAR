// SPDX-License-Identifier: Apache-2.0
import { useWizardState } from '../../stores/onboarding'
import { AlertCircle } from 'lucide-react'
import { ArrowLeft, ArrowRight } from 'lucide-react'
import { IconButton, Pill } from '../ui/primitives'

interface StepFooterProps {
  onNext?: () => void
  onFinish?: () => void
  onSkip?: () => void
}

export function StepFooter({ onNext, onFinish, onSkip }: StepFooterProps = {}) {
  const step = useWizardState(s => s.step)
  const current = useWizardState(s => s.current_step_index)
  const errors = useWizardState(s => s.errors)
  const back = useWizardState(s => s.back)
  const next = useWizardState(s => s.next)
  const finish = useWizardState(s => s.finish)
  const handleNext = onNext ?? next
  const handleFinish = onFinish ?? finish
  const error = current === 0 ? errors.provider
    : current === 1 ? errors.embedding
    : current === 2 ? errors.character_card
    : errors.user_card

  return (
    <div className="mx-auto mt-8 flex w-full max-w-6xl flex-col items-start gap-3">
      {error && (
        <div
          role="alert"
          className="glass flex w-full max-w-2xl items-start gap-3 rounded-2xl border-red-500 bg-red-500/10 px-4 py-3 text-sm"
        >
          <AlertCircle size={18} className="mt-0.5 shrink-0 text-red-500" aria-hidden="true" />
          <div>
            <div className="font-semibold text-red-500">Complete the required fields</div>
            <div className="mt-0.5 text-text">{error}</div>
          </div>
        </div>
      )}
      <div className="flex items-center gap-3">
        {current > 0 && step !== 'submitting' && step !== 'completed' && (
          <IconButton onClick={back} aria-label="Back"><ArrowLeft size={16} /></IconButton>
        )}
        {(step === 'embedding' || step === 'character_card') && (
          <Pill onClick={onSkip} variant="ghost">Skip for now</Pill>
        )}
        {current < 3 && step !== 'submitting' && step !== 'completed' && (
          <Pill onClick={handleNext} variant="primary" size="lg" icon={<ArrowRight size={15} />}>Next</Pill>
        )}
        {current === 3 && step !== 'submitting' && step !== 'completed' && (
          <Pill onClick={handleFinish} variant="primary" size="lg" icon={<ArrowRight size={15} />}>Enter FSAR</Pill>
        )}
      </div>
    </div>
  )
}
