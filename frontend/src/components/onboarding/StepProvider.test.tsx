// SPDX-License-Identifier: Apache-2.0
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import '@testing-library/jest-dom/vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { PresetCard } from './StepProvider/PresetCard'
import { useWizardState } from '../../stores/onboarding'
import type { Preset } from './StepProvider/types'

const samplePreset: Preset = {
  id: 'openai',
  label: 'OpenAI',
  family: 'openai_compat',
  default_base_url: 'https://api.openai.com/v1',
  default_headers: {},
  api_key_required: true,
  api_key_env: 'OPENAI_API_KEY',
  model_list_url_suffix: '/models',
  test_url_suffix: '/models',
  deferred: false,
  icon: 'openai',
  homepage: 'https://platform.openai.com',
  order: 1,
}

const deferredPreset: Preset = { ...samplePreset, id: 'google', label: 'Google', deferred: true }

describe('PresetCard', () => {
  beforeEach(() => {
    useWizardState.setState({
      step: 'provider',
      current_step_index: 0,
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

  afterEach(cleanup)

  it('renders label and family', () => {
    render(<PresetCard preset={samplePreset} selected={false} onSelect={() => {}} />)

    const card = screen.getByTestId('preset-card-openai')
    expect(card).toHaveTextContent('OpenAI')
    expect(card).toHaveTextContent('openai_compat')
  })

  it('marks selected', () => {
    render(<PresetCard preset={samplePreset} selected={true} onSelect={() => {}} />)

    expect(screen.getByTestId('preset-card-openai').dataset.selected).toBe('true')
  })

  it('disables deferred card', () => {
    render(<PresetCard preset={deferredPreset} selected={false} onSelect={() => {}} />)

    const card = screen.getByTestId('preset-card-google')
    expect(card.dataset.disabled).toBe('true')
    expect(card).toBeDisabled()
  })
})
