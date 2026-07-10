// SPDX-License-Identifier: Apache-2.0
import { useWizardState } from '../../../stores/onboarding'
import { AvatarUpload } from './AvatarUpload'

export function CreateNewForm() {
  const data = useWizardState(s => s.data.character_card.new_card)
  const set = useWizardState(s => s.setCharacterCardField)
  return (
    <div data-testid="create-new-form" className="flex flex-col gap-3 max-w-xl">
      <div className="flex flex-col gap-1">
        <label className="text-caption text-text-muted">Name</label>
        <input
          type="text"
          value={data.name}
          onChange={e => set('new_card', { ...data, name: e.target.value })}
          data-testid="character-name-input"
          className="border border-border px-2 py-1 bg-surface text-body"
        />
      </div>
      <AvatarUpload />
      <div className="flex flex-col gap-1">
        <label className="text-caption text-text-muted">Personality</label>
        <input
          type="text"
          value={data.personality}
          onChange={e => set('new_card', { ...data, personality: e.target.value })}
          data-testid="character-personality-input"
          className="border border-border px-2 py-1 bg-surface text-body"
        />
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-caption text-text-muted">System prompt override</label>
        <textarea
          value={data.system_prompt_override}
          onChange={e => set('new_card', { ...data, system_prompt_override: e.target.value })}
          rows={4}
          data-testid="character-prompt-input"
          className="border border-border px-2 py-1 bg-surface text-body"
        />
      </div>
    </div>
  )
}
