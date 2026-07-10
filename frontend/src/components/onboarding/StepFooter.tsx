// SPDX-License-Identifier: Apache-2.0
import { useWizardState } from '../../stores/onboarding'

export function StepFooter() {
  const step = useWizardState(s => s.step)
  const current = useWizardState(s => s.current_step_index)
  const back = useWizardState(s => s.back)
  const next = useWizardState(s => s.next)
  const skip = useWizardState(s => s.skip)
  const finish = useWizardState(s => s.finish)
  return (
    <div className="flex items-center gap-3 mt-8">
      {current > 0 && step !== 'submitting' && step !== 'completed' && (
        <button onClick={back} className="px-4 py-2 border border-border">Back</button>
      )}
      {step === 'character_card' && (
        <button onClick={skip} className="px-4 py-2 border border-border">Skip</button>
      )}
      {current < 2 && step !== 'submitting' && step !== 'completed' && (
        <button onClick={next} className="px-4 py-2 border-2 border-border-strong bg-text text-bg">Next</button>
      )}
      {current === 2 && step !== 'submitting' && step !== 'completed' && (
        <button onClick={finish} className="px-4 py-2 border-2 border-border-strong bg-text text-bg">Finish</button>
      )}
    </div>
  )
}