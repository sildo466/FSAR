// SPDX-License-Identifier: Apache-2.0
import { useState } from 'react'
import { useWizardState } from '../../../stores/onboarding'

const MAX_BYTES = 2 * 1024 * 1024
const ALLOWED = ['image/jpeg', 'image/png', 'image/webp']

export function AvatarUpload() {
  const data = useWizardState(s => s.data.character_card.new_card)
  const set = useWizardState(s => s.setCharacterCardField)
  const [err, setErr] = useState<string | null>(null)

  const onChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (!ALLOWED.includes(file.type)) { setErr('must be jpg/png/webp'); return }
    if (file.size > MAX_BYTES) { setErr('must be <= 2MB'); return }
    setErr(null)
    set('new_card', { ...data, avatar_file: file, avatar_path: null })
  }

  return (
    <div className="flex flex-col gap-1">
      <label className="text-caption text-text-muted">Avatar ({'<= 2MB'}, jpg/png/webp)</label>
      <input
        type="file"
        accept=".jpg,.jpeg,.png,.webp"
        onChange={onChange}
        data-testid="avatar-input"
        className="border border-border px-2 py-1 bg-surface text-body"
      />
      {err && <div className="text-caption" data-testid="avatar-error">{err}</div>}
      {data.avatar_file && <div className="text-caption text-text-muted">{data.avatar_file.name}</div>}
    </div>
  )
}
