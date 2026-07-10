// SPDX-License-Identifier: Apache-2.0
import { afterEach, describe, expect, it } from 'vitest'
import '@testing-library/jest-dom/vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { WizardShell } from './WizardShell'
import { useWizardState } from '../../stores/onboarding'

describe('WizardShell', () => {
  afterEach(cleanup)

  it('renders 3 progress dots', () => {
    useWizardState.setState({ current_step_index: 0, step: 'provider' })
    render(<WizardShell><div>child</div></WizardShell>)
    expect(screen.getByTestId('wizard-progress')).toBeInTheDocument()
    expect(screen.getAllByTestId(/^wizard-dot-/)).toHaveLength(3)
  })

  it('marks active dot on current step', () => {
    useWizardState.setState({ current_step_index: 1, step: 'user_card' })
    render(<WizardShell><div>child</div></WizardShell>)
    const dot = screen.getByTestId('wizard-dot-1')
    expect(dot.dataset.active).toBe('true')
  })

  it('renders children inside', () => {
    useWizardState.setState({ current_step_index: 0, step: 'provider' })
    render(<WizardShell><span data-testid="child-content">hello</span></WizardShell>)
    expect(screen.getByTestId('child-content')).toHaveTextContent('hello')
  })
})