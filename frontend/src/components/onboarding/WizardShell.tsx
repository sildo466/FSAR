// SPDX-License-Identifier: Apache-2.0
import type { ReactNode } from 'react'
import { useWizardState } from '../../stores/onboarding'
import { useWS } from '../../stores/ws'
import { Pill } from '../ui/primitives'

const STEP_LABELS = ['Provider', 'Embedding', 'Character', 'You']

export function WizardShell({ children }: { children: ReactNode }) {
  const current = useWizardState(s => s.current_step_index)
  const send = useWS(s => s.send)
  return (
    <div className="fixed inset-0 z-50 flex flex-col overflow-hidden bg-bg/95 before:absolute before:inset-0 before:bg-[radial-gradient(circle_at_15%_10%,var(--glow-soft),transparent_34%),radial-gradient(circle_at_85%_90%,var(--glow-faint),transparent_36%)] before:content-['']">
      <div className="relative z-10 flex items-center gap-6 px-8 py-6">
        <div className="flex flex-col gap-1">
          <h1 className="font-display text-xl italic">Shape your companion</h1>
          <p className="text-caption text-text-muted">A few thoughtful choices, then the space is yours.</p>
        </div>
        <div data-testid="wizard-progress" className="ml-auto flex items-center gap-3">
          {STEP_LABELS.map((label, i) => {
            const isActive = current === i
            const isDone = current > i
            return (
              <div key={i} className="flex items-center gap-2">
                <div
                  data-testid={`wizard-dot-${i}`}
                  data-active={isActive}
                  className={`h-2 w-2 rounded-full transition-all ${
                    isActive ? 'scale-125 bg-text shadow-[0_0_14px_var(--glow-soft)]'
                    : isDone ? 'bg-text/60'
                    : 'bg-text/15'
                  }`}
                />
                <span className="text-caption text-text-muted">{label}</span>
              </div>
            )
          })}
        </div>
        <Pill variant="ghost" size="sm" onClick={() => { if (confirm('Skip setup? You can configure later in Settings.')) { send({ type: 'onboarding.complete' }) } }}>Skip setup</Pill>
      </div>
      <div className="relative z-10 flex-1 overflow-auto px-8 py-6">
        {children}
      </div>
    </div>
  )
}
