// SPDX-License-Identifier: MIT
import type { Preset } from './types'
import { motion } from 'framer-motion'
import { useTranslation } from 'react-i18next'
import { springs } from '../../../lib/motion/springs'

interface Props {
  preset: Preset
  selected: boolean
  onSelect: () => void
}

export function PresetCard({ preset, selected, onSelect }: Props) {
  const { t } = useTranslation();
  const isDisabled = preset.deferred
  return (
    <motion.button
      whileHover={isDisabled ? undefined : { scale: 1.03, y: -2 }}
      whileTap={isDisabled ? undefined : { scale: 0.97 }}
      transition={springs.bouncy}
      type="button"
      onClick={isDisabled ? undefined : onSelect}
      disabled={isDisabled}
      title={isDisabled ? t("onboarding.provider.availableLaterAria") : preset.homepage}
      data-testid={`preset-card-${preset.id}`}
      data-selected={selected}
      data-disabled={isDisabled}
      className={`glass min-h-32 rounded-[24px] p-5 text-left transition-shadow
        ${selected ? 'shadow-[0_0_28px_var(--glow-soft)] ring-1 ring-border-strong' : ''}
        ${isDisabled ? 'cursor-not-allowed opacity-40' : 'cursor-pointer hover:shadow-[0_0_24px_var(--glow-faint)]'}
      `}
    >
      <div className="font-mono text-[9px] uppercase tracking-[0.18em] text-text-faint">{preset.family}</div>
      <div className="mt-1 font-display text-lg">{preset.label}</div>
      <div className="mt-4 text-[10px] text-text-muted">{isDisabled ? t("onboarding.provider.availableLater") : t("onboarding.provider.configureAccess")}</div>
    </motion.button>
  )
}
