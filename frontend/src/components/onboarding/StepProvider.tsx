// SPDX-License-Identifier: MIT
import { useTranslation } from 'react-i18next'
import { PresetGrid } from './StepProvider/PresetGrid'
import { PresetDetailPanel } from './StepProvider/PresetDetailPanel'
import { useWizardState } from '../../stores/onboarding'
import { ArrowLeft } from 'lucide-react'
import { IconButton } from '../ui/primitives'

export function StepProvider() {
  const { t } = useTranslation();
  const selected = useWizardState(s => s.data.provider.preset_id)
  const set = useWizardState(s => s.setProviderField)
  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
      <div className="flex items-center gap-3">
        {selected && <IconButton aria-label={t("onboarding.provider.backAria")} onClick={() => set('preset_id', null)}><ArrowLeft size={16} /></IconButton>}
        <div><h2 className="font-display text-3xl italic">{selected ? t("onboarding.provider.configureTitle") : t("onboarding.provider.chooseTitle")}</h2><p className="mt-1 text-sm text-text-muted">{selected ? t("onboarding.provider.configureDesc") : t("onboarding.provider.chooseDesc")}</p></div>
      </div>
      {selected ? <div className="mx-auto w-full max-w-2xl"><PresetDetailPanel /></div> : <PresetGrid />}
    </div>
  )
}
