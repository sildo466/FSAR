// SPDX-License-Identifier: Apache-2.0
import { useWizardState } from '../../../stores/onboarding'

export function PresetDetailPanel() {
  const presetId = useWizardState(s => s.data.provider.preset_id)
  if (!presetId) return <div className="text-text-muted">Select a preset to configure</div>
  return <div>Detail panel (Task 6.2 will fill this)</div>
}