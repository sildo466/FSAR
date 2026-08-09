// SPDX-License-Identifier: MIT
import { useTranslation } from 'react-i18next'
import { useWizardState } from '../../../stores/onboarding'

const DEFAULTS = [
  { id: 1, labelKey: 'onboarding.characterCard.presetFsarZh' },
  { id: 2, labelKey: 'onboarding.characterCard.presetFsarEn' },
  { id: 3, labelKey: 'onboarding.characterCard.presetCoachZh' },
  { id: 4, labelKey: 'onboarding.characterCard.presetCoachEn' },
  { id: 5, labelKey: 'onboarding.characterCard.presetAnalystZh' },
  { id: 6, labelKey: 'onboarding.characterCard.presetAnalystEn' },
];

export function PickExistingOption() {
  const { t } = useTranslation();
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
          {t(c.labelKey)}
        </button>
      ))}
    </div>
  )
}
