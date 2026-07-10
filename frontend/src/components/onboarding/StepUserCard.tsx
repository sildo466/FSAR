// SPDX-License-Identifier: Apache-2.0
import { useWizardState } from '../../stores/onboarding'

export function StepUserCard() {
  const data = useWizardState(s => s.data.user_card)
  const set = useWizardState(s => s.setUserCardField)
  const err = useWizardState(s => s.errors.user_card)
  return (
    <div className="max-w-xl flex flex-col gap-4">
      <h2 className="text-h2">Tell FSAR about you</h2>
      <div className="flex flex-col gap-1">
        <label className="text-caption text-text-muted">Your name</label>
        <input
          type="text"
          value={data.name}
          onChange={e => set('name', e.target.value)}
          data-testid="user-name-input"
          className="border border-border px-2 py-1 bg-surface text-body"
        />
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-caption text-text-muted">About you</label>
        <textarea
          value={data.bio}
          onChange={e => set('bio', e.target.value)}
          rows={6}
          data-testid="user-bio-input"
          className="border border-border px-2 py-1 bg-surface text-body"
          placeholder="A short bio (hobbies, work, what kind of conversation you want)"
        />
      </div>
      {err && <div className="text-caption" data-testid="user-card-error">{err}</div>}
    </div>
  )
}
