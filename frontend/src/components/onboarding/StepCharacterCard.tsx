// SPDX-License-Identifier: Apache-2.0
import { useWizardState } from '../../stores/onboarding'
import { UseDefaultOption } from './StepCharacterCard/UseDefaultOption'
import { PickExistingOption } from './StepCharacterCard/PickExistingOption'
import { CreateNewForm } from './StepCharacterCard/CreateNewForm'
import { ImportSTImageOption } from './StepCharacterCard/ImportSTImageOption'

const MODES = [
  { key: 'use_default', label: 'Use default' },
  { key: 'pick_existing', label: 'Pick existing' },
  { key: 'create_new', label: 'Create new' },
  { key: 'import_st', label: 'Import ST image' },
] as const

export function StepCharacterCard() {
  const mode = useWizardState(s => s.data.character_card.mode)
  const set = useWizardState(s => s.setCharacterCardField)
  return (
    <div className="flex flex-col gap-6">
      <h2 className="text-h2">Choose your character</h2>
      <div className="flex items-center gap-2" data-testid="character-mode-tabs">
        {MODES.map(m => (
          <button
            key={m.key}
            onClick={() => set('mode', m.key)}
            data-testid={`character-mode-${m.key}`}
            data-active={mode === m.key}
            className={`px-3 py-1 border text-body ${
              mode === m.key ? 'border-2 border-border-strong' : 'border-border'
            }`}
          >
            {m.label}
          </button>
        ))}
      </div>
      <div>
        {mode === 'use_default' && <UseDefaultOption />}
        {mode === 'pick_existing' && <PickExistingOption />}
        {mode === 'create_new' && <CreateNewForm />}
        {mode === 'import_st' && <ImportSTImageOption />}
      </div>
    </div>
  )
}
