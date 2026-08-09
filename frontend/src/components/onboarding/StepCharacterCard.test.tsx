// SPDX-License-Identifier: MIT
import { describe, expect, it, beforeEach, afterEach } from 'vitest'
import '@testing-library/jest-dom/vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { StepCharacterCard } from './StepCharacterCard'
import { useWizardState } from '../../stores/onboarding'

describe('StepCharacterCard', () => {
  afterEach(cleanup)

  beforeEach(() => {
    useWizardState.setState({
      step: 'character_card',
      current_step_index: 2,
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

  it('renders 4 mode tabs', () => {
    render(<StepCharacterCard />)
    expect(screen.getByTestId('character-mode-use_default')).toBeInTheDocument()
    expect(screen.getByTestId('character-mode-pick_existing')).toBeInTheDocument()
    expect(screen.getByTestId('character-mode-create_new')).toBeInTheDocument()
    expect(screen.getByTestId('character-mode-import_st')).toBeInTheDocument()
  })

  it('shows use_default option by default', () => {
    render(<StepCharacterCard />)
    expect(screen.getByTestId('use-default-option')).toBeInTheDocument()
  })

  it('shows create_new form when mode switched', () => {
    useWizardState.setState(s => ({
      data: {
        ...s.data,
        character_card: { ...s.data.character_card, mode: 'create_new' },
      },
    }))
    render(<StepCharacterCard />)
    expect(screen.getByTestId('create-new-form')).toBeInTheDocument()
  })
})
