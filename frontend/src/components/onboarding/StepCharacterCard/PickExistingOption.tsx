// SPDX-License-Identifier: Apache-2.0
import { useWizardState } from '../../../stores/onboarding'

const DEFAULTS = [
  { id: 1, label: 'FSAR (zh)' },
  { id: 2, label: 'FSAR (en)' },
  { id: 3, label: 'Coding Coach (zh)' },
  { id: 4, label: 'Coding Coach (en)' },
  { id: 5, label: 'Research Analyst (zh)' },
  { id: 6, label: 'Research Analyst (en)' },
]

export function PickExistingOption() {
  const picked = useWizardState(s => s.data.character_card.picked_card_id)
  const set = useWizardState(s => s.setCharacterCardField)
  return (
    <div data-testid="pick-existing-option" className="flex flex-col gap-2 max-w-md">
      {DEFAULTS.map(c => (
        <button
          key={c.id}
          onClick={() => set('picked_card_id', c.id)}
          data-testid={`pick-card-${c.id}`}
          data-selected={picked === c.id}
          className={`text-left px-3 py-2 border text-body ${
            picked === c.id ? 'border-2 border-border-strong' : 'border-border'
          }`}
        >
          {c.label}
        </button>
      ))}
    </div>
  )
}
