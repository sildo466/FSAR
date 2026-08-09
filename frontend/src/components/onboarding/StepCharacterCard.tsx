// SPDX-License-Identifier: MIT
import { useTranslation } from 'react-i18next'
import { useWizardState } from '../../stores/onboarding'
import { UseDefaultOption } from './StepCharacterCard/UseDefaultOption'
import { PickExistingOption } from './StepCharacterCard/PickExistingOption'
import { CreateNewForm } from './StepCharacterCard/CreateNewForm'
import { ImportSTImageOption } from './StepCharacterCard/ImportSTImageOption'
import { AnimatePresence, motion } from 'framer-motion'

const MODES = [
  { key: 'use_default', labelKey: 'onboarding.characterCard.useDefault' },
  { key: 'pick_existing', labelKey: 'onboarding.characterCard.pickExisting' },
  { key: 'create_new', labelKey: 'onboarding.characterCard.createNew' },
  { key: 'import_st', labelKey: 'onboarding.characterCard.importSt' },
] as const

export function StepCharacterCard() {
  const { t } = useTranslation();
  const mode = useWizardState(s => s.data.character_card.mode)
  const set = useWizardState(s => s.setCharacterCardField)
  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <h2 className="font-display text-3xl italic">{t("onboarding.characterCard.title")}</h2>
      <p className="text-caption text-text-muted max-w-2xl">{t("onboarding.characterCard.description")}</p>
      <div className="glass flex items-center gap-1 rounded-full p-1" data-testid="character-mode-tabs">
        {MODES.map(m => (
          <button
            key={m.key}
            onClick={() => set('mode', m.key)}
            data-testid={`character-mode-${m.key}`}
            data-active={mode === m.key}
            className={`relative flex-1 rounded-full px-3 py-2 text-sm transition ${mode === m.key ? 'text-bg' : 'text-text-muted hover:text-text'}`}
          >
            {mode === m.key && <motion.span layoutId="character-mode-pill" className="absolute inset-0 -z-10 rounded-full bg-text" />}
            {t(m.labelKey)}
          </button>
        ))}
      </div>
      <AnimatePresence mode="wait"><motion.div key={mode} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} className="glass rounded-[28px] p-6">
        {mode === 'use_default' && <UseDefaultOption />}
        {mode === 'pick_existing' && <PickExistingOption />}
        {mode === 'create_new' && <CreateNewForm />}
        {mode === 'import_st' && <ImportSTImageOption />}
      </motion.div></AnimatePresence>
    </div>
  )
}
