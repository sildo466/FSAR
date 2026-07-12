// SPDX-License-Identifier: Apache-2.0
import { useState, type ReactNode } from 'react'
import { useWizardState } from '../../stores/onboarding'
import { Pill } from '../ui/primitives'
import { AnimatePresence, motion } from 'framer-motion'

const STEP_LABELS = ['Provider', 'Embedding', 'Character', 'You']

interface WizardShellProps {
  children: ReactNode
  onSkipSetup?: () => void
}

export function WizardShell({ children, onSkipSetup = () => {} }: WizardShellProps) {
  const current = useWizardState(s => s.current_step_index)
  const [confirmingSkip, setConfirmingSkip] = useState(false)
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
        <Pill variant="ghost" size="sm" onClick={() => setConfirmingSkip(true)}>Skip setup</Pill>
      </div>
      <div className="relative z-10 flex-1 overflow-auto px-8 py-6">
        {children}
      </div>
      <AnimatePresence>
        {confirmingSkip && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="absolute inset-0 z-20 flex items-center justify-center bg-bg/45 p-6 backdrop-blur-sm">
            <motion.div initial={{ scale: .96, y: 10 }} animate={{ scale: 1, y: 0 }} exit={{ scale: .96, y: 10 }} className="glass-strong w-full max-w-sm rounded-[28px] p-6 shadow-[0_24px_80px_var(--glow-faint)]">
              <p className="font-display text-2xl italic">Skip setup?</p>
              <p className="mt-3 text-sm leading-6 text-text-muted">You can add providers, memory, and cards later in Settings.</p>
              <div className="mt-6 flex justify-end gap-2"><Pill variant="ghost" onClick={() => setConfirmingSkip(false)}>Keep setting up</Pill><Pill variant="primary" onClick={onSkipSetup}>Skip setup</Pill></div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
