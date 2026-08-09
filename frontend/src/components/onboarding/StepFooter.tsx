// SPDX-License-Identifier: MIT
import { useTranslation } from 'react-i18next'
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
  const { t } = useTranslation();
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
    : current === 3 ? errors.user_card
    : undefined

  return (
    <div className="mx-auto mt-8 flex w-full max-w-6xl flex-col items-start gap-3">
      {error && (
        <div
          role="alert"
          className="glass flex w-full max-w-2xl items-start gap-3 rounded-2xl border-red-500 bg-red-500/10 px-4 py-3 text-sm"
        >
          <AlertCircle size={18} className="mt-0.5 shrink-0 text-red-500" aria-hidden="true" />
          <div>
            <div className="font-semibold text-red-500">{t("onboarding.footer.completeRequired")}</div>
            <div className="mt-0.5 text-text">{error}</div>
          </div>
        </div>
      )}
      <div className="flex items-center gap-3">
        {current > 0 && step !== 'submitting' && step !== 'completed' && (
          <IconButton onClick={back} aria-label={t("common.back")}><ArrowLeft size={16} /></IconButton>
        )}
        {(step === 'embedding' || step === 'character_card') && (
          <Pill onClick={onSkip} variant="ghost">{t("onboarding.footer.skipForNow")}</Pill>
        )}
        {current < 5 && step !== 'submitting' && step !== 'completed' && (
          <Pill onClick={handleNext} variant="primary" size="lg" icon={<ArrowRight size={15} />}>{t("onboarding.footer.next")}</Pill>
        )}
        {current === 5 && step !== 'submitting' && step !== 'completed' && (
          <Pill onClick={handleFinish} variant="primary" size="lg" icon={<ArrowRight size={15} />}>{t("onboarding.footer.enterFsar")}</Pill>
        )}
      </div>
    </div>
  )
}
