// SPDX-License-Identifier: Apache-2.0
import { PresetGrid } from './StepProvider/PresetGrid'
import { PresetDetailPanel } from './StepProvider/PresetDetailPanel'

export function StepProvider() {
  return (
    <div className="grid grid-cols-[1fr_320px] gap-6">
      <PresetGrid />
      <PresetDetailPanel />
    </div>
  )
}