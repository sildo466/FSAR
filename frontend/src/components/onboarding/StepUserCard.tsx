// SPDX-License-Identifier: Apache-2.0
import { useWizardState } from '../../stores/onboarding'
import { Capsule, Input } from '../ui/primitives'

export function StepUserCard() {
  const data = useWizardState(s => s.data.user_card)
  const set = useWizardState(s => s.setUserCardField)
  const err = useWizardState(s => s.errors.user_card)
  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-5">
      <h2 className="font-display text-3xl italic">Tell FSAR about you</h2>
      <p className="text-caption text-text-muted">FSAR remembers who it's talking to — add your name and a short bio so replies feel personal.</p>
      <Capsule className="flex flex-col gap-4"><div className="flex flex-col gap-1">
        <label className="text-caption text-text-muted">Your name</label>
        <Input
          type="text"
          value={data.name}
          onChange={e => set('name', e.target.value)}
          data-testid="user-name-input"
        />
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-caption text-text-muted">About you</label>
        <textarea
          value={data.bio}
          onChange={e => set('bio', e.target.value)}
          rows={6}
          data-testid="user-bio-input"
          className="glass rounded-[20px] border-0 px-4 py-3 text-body outline-none"
          placeholder="A short bio (hobbies, work, what kind of conversation you want)"
        />
      </div></Capsule>
      {err && <div className="text-caption" data-testid="user-card-error">{err}</div>}
    </div>
  )
}
