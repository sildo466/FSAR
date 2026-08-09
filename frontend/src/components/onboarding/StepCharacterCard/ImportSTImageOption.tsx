// SPDX-License-Identifier: MIT
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useWizardState } from '../../../stores/onboarding'

function readPngTextChunks(buf: ArrayBuffer): Record<string, string> {
  const view = new DataView(buf)
  const out: Record<string, string> = {}
  if (view.getUint32(0) !== 0x89504e47 || view.getUint32(4) !== 0x0d0a1a0a) return null as never
  let offset = 8
  while (offset < buf.byteLength) {
    const len = view.getUint32(offset)
    const type = String.fromCharCode(
      view.getUint8(offset + 4), view.getUint8(offset + 5),
      view.getUint8(offset + 6), view.getUint8(offset + 7),
    )
    if (type === 'tEXt' || type === 'iTXt') {
      const data = new Uint8Array(buf, offset + 8, len)
      const text = new TextDecoder('utf-8').decode(data)
      const sep = text.indexOf('\0')
      const keyword = sep >= 0 ? text.slice(0, sep) : text
      const value = sep >= 0 ? text.slice(sep + 1) : ''
      if (keyword === 'chara') out.chara = value
    }
    if (type === 'IEND') break
    offset += 12 + len
  }
  return out
}

export function ImportSTImageOption() {
  const { t } = useTranslation();
  const set = useWizardState(s => s.setCharacterCardField)
  const newCard = useWizardState(s => s.data.character_card.new_card)
  const [err, setErr] = useState<string | null>(null)

  const onChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setErr(null)
    try {
      const buf = await file.arrayBuffer()
      const head = new DataView(buf)
      if (head.getUint32(0) !== 0x89504e47 || head.getUint32(4) !== 0x0d0a1a0a) {
        setErr(t("onboarding.characterCard.notPng"))
        return
      }
      const chunks = readPngTextChunks(buf)
      if (!chunks.chara) {
        setErr(t("onboarding.characterCard.noCharaMeta"))
        return
      }
      const meta = JSON.parse(chunks.chara)
      const data = (meta.data || meta)
      set('mode', 'create_new')
      set('new_card', {
        ...newCard,
        name: data.name || '',
        personality: data.personality || '',
        system_prompt_override: data.system_prompt || '',
      })
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : String(e)
      setErr(t("onboarding.characterCard.parseFailed", { message }))
    }
  }

  return (
    <div data-testid="import-st-option" className="flex flex-col gap-2 max-w-xl">
      <input
        type="file"
        accept=".png"
        onChange={onChange}
        data-testid="st-image-input"
        className="border border-border px-2 py-1 bg-surface text-body"
      />
      {err && <div className="text-caption" data-testid="st-image-error">{err}</div>}
    </div>
  )
}