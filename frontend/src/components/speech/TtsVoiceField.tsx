// SPDX-License-Identifier: MIT
import { Lock, Volume2 } from "lucide-react";
import { ttsPresets } from "../../lib/speech-presets";
import { useSpeechStore } from "../../stores/speech";
import { useWS } from "../../stores/ws";
import { useTranslation } from "react-i18next";
import { Switch } from "../ui/primitives";

interface Props {
  value: string;
  onChange: (value: string) => void;
  instructions: string;
  onInstructionsChange: (value: string) => void;
  autoplay: boolean;
  onAutoplayChange: (value: boolean) => void;
}

export function TtsVoiceField({ value, onChange, instructions, onInstructionsChange, autoplay, onAutoplayChange }: Props) {
  const { t } = useTranslation();
  const configured = useSpeechStore((state) => state.isTtsConfigured);
  const config = useWS((state) => state.config);
  const tts = (config?.tts ?? {}) as Record<string, unknown>;
  const providers = Array.isArray(tts.providers) ? tts.providers as Array<Record<string, unknown>> : [];
  const provider = providers.find((item) => item.id === tts.active);
  const preset = ttsPresets.find((item) => item.id === provider?.preset_id);
  const placeholder = configured ? (preset?.voice_placeholder || t("speech.tts.providerVoicePlaceholder")) : t("speech.tts.configureFirst");
  return (
    <fieldset className="rounded-2xl border border-border bg-bg/20 p-4" aria-label={t("speech.tts.characterVoice")}>
      <legend className="px-2 font-mono text-[10px] uppercase tracking-[0.14em] text-text-faint">{t("speech.tts.characterVoice")}</legend>
      <label className="text-[11px] text-text-muted">{t("speech.tts.voiceId")}<div className="relative mt-1"><Volume2 size={13} className="absolute left-3 top-3 text-text-faint" /><input value={value} onChange={(event) => onChange(event.target.value)} disabled={!configured} list="tts-character-voice-options" placeholder={placeholder} className="h-10 w-full rounded-xl border border-border bg-bg/60 pl-9 pr-9 font-mono text-xs text-text disabled:cursor-not-allowed disabled:opacity-50" />{!configured && <Lock size={13} className="absolute right-3 top-3 text-text-faint" />}</div></label>
      {preset?.voices && preset.voices.length > 0 && (<datalist id="tts-character-voice-options">{preset.voices.map((voice) => <option key={voice} value={voice} />)}</datalist>)}
      <label className="mt-3 block text-[11px] text-text-muted">{t("speech.tts.characterInstructions")}<textarea value={instructions} onChange={(event) => onInstructionsChange(event.target.value)} disabled={!configured} rows={2} placeholder={t("speech.tts.instructionsPlaceholder")} className="mt-1 w-full rounded-xl border border-border bg-bg/60 px-3 py-2 font-mono text-xs text-text disabled:cursor-not-allowed disabled:opacity-50" /></label>
      <label className="mt-3 flex items-center gap-2 text-xs text-text-muted"><Switch checked={autoplay} onChange={onAutoplayChange} disabled={!configured} label={t("speech.tts.autoplay")} /> {t("speech.tts.autoplay")}</label>
      {!configured && <p className="mt-3 text-[11px] text-text-muted">{t("speech.tts.notConfigured")} <a href="/settings/speech" className="text-text underline underline-offset-2">{t("speech.tts.configureNow")}</a></p>}
    </fieldset>
  );
}
