// SPDX-License-Identifier: Apache-2.0
import type { Preset } from './types'

interface Props {
  preset: Preset
  selected: boolean
  onSelect: () => void
}

export function PresetCard({ preset, selected, onSelect }: Props) {
  const isDisabled = preset.deferred
  return (
    <button
      type="button"
      onClick={isDisabled ? undefined : onSelect}
      disabled={isDisabled}
      title={isDisabled ? 'Available in a future phase' : preset.homepage}
      data-testid={`preset-card-${preset.id}`}
      data-selected={selected}
      data-disabled={isDisabled}
      className={`w-60 h-30 p-3 border text-left transition-colors
        ${selected ? 'border-2 border-border-strong' : 'border-border'}
        ${isDisabled ? 'opacity-50 cursor-not-allowed' : 'hover:border-border-strong cursor-pointer'}
      `}
    >
      <div className="text-body-emphasis">{preset.label}</div>
      <div className="text-caption text-text-muted">{preset.family}</div>
    </button>
  )
}