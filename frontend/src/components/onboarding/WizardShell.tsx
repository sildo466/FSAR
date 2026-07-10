// SPDX-License-Identifier: Apache-2.0
import type { ReactNode } from 'react'
import { useWizardState } from '../../stores/onboarding'

const STEP_LABELS = ['Provider', 'User Card', 'Character Card']

export function WizardShell({ children }: { children: ReactNode }) {
  const current = useWizardState(s => s.current_step_index)
  return (
    <div className="fixed inset-0 bg-bg z-50 flex flex-col">
      <div className="px-8 py-6 border-b border-border flex items-center gap-6">
        <h1 className="text-h2">FSAR Setup</h1>
        <div data-testid="wizard-progress" className="flex items-center gap-3 ml-auto">
          {STEP_LABELS.map((label, i) => {
            const isActive = current === i
            const isDone = current > i
            return (
              <div key={i} className="flex items-center gap-2">
                <div
                  data-testid={`wizard-dot-${i}`}
                  data-active={isActive}
                  className={`w-3 h-3 rounded-full border ${
                    isActive ? 'bg-border-strong border-border-strong'
                    : isDone ? 'bg-text border-text'
                    : 'bg-bg border-border'
                  }`}
                />
                <span className="text-caption text-text-muted">{label}</span>
              </div>
            )
          })}
        </div>
      </div>
      <div className="flex-1 overflow-auto px-8 py-6">
        {children}
      </div>
    </div>
  )
}