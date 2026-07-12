// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it, beforeEach, afterEach } from 'vitest'
import '@testing-library/jest-dom/vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { StepUserCard } from './StepUserCard'
import { useWizardState } from '../../stores/onboarding'

describe('StepUserCard', () => {
  afterEach(cleanup)

  beforeEach(() => {
    cleanup()
    useWizardState.setState({
      step: 'user_card',
      current_step_index: 1,
      data: {
        provider: { preset_id: null, api_key: '', base_url: '', model: '', input_per_1m: '', output_per_1m: '', test_result: null },
        embedding: { provider: '', api_key: '', base_url: '', model: '', probe_result: null },
        user_card: { name: '', bio: '' },
        character_card: {
          mode: 'use_default',
          picked_card_id: null,
          new_card: { name: '', avatar_file: null, avatar_path: null, personality: '', system_prompt_override: '' },
          st_file: null,
        },
      },
      errors: {},
    })
  })

  it('renders name + bio inputs', () => {
    render(<StepUserCard />)
    expect(screen.getByTestId('user-name-input')).toBeInTheDocument()
    expect(screen.getByTestId('user-bio-input')).toBeInTheDocument()
  })

  it('shows error when set', () => {
    useWizardState.setState({ errors: { user_card: 'enter your name' } })
    render(<StepUserCard />)
    expect(screen.getByTestId('user-card-error')).toHaveTextContent('enter your name')
  })
})
