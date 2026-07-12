// SPDX-License-Identifier: Apache-2.0
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import '@testing-library/jest-dom/vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { StepFooter } from './StepFooter'
import { useWizardState } from '../../stores/onboarding'

describe('StepFooter', () => {
  beforeEach(() => {
    useWizardState.getState().reset()
  })

  afterEach(cleanup)

  it('shows a prominent alert when required fields are missing', async () => {
    render(<StepFooter />)

    fireEvent.click(screen.getByRole('button', { name: 'Next' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Complete the required fields')
    expect(alert).toHaveTextContent('select a preset')
    expect(alert).toHaveClass('border-red-500', 'bg-red-500/10')
  })

  it('clears the alert when the user starts correcting the step', async () => {
    render(<StepFooter />)
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    await screen.findByRole('alert')

    act(() => {
      useWizardState.getState().setProviderField('preset_id', 'lmstudio')
    })

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
