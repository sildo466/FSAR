// SPDX-License-Identifier: MIT
import { useEffect, useState } from "react";
import { Play, Save } from "lucide-react";
import { useSpeechStore } from "../../stores/speech";
import { useTranslation } from "react-i18next";
import { ttsPresets } from "../../lib/speech-presets";

export interface TtsProvider {
  id: string;
  preset_id: string;
  label: string;
  family: string;
  base_url: string;
  api_key: string;
  voice: string;
  model: string;
  enabled: boolean;
  extra?: Record<string, unknown>;
  [key: string]: unknown;
}

interface Props {
  provider: TtsProvider;
  active: boolean;
  onChange: (provider: TtsProvider) => void | Promise<void>;
}

export function TtsProviderCard({ provider, active, onChange }: Props) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState(provider);
  const [status, setStatus] = useState("");
  const playText = useSpeechStore((state) => state.playText);
  const preset = ttsPresets.find((item) => item.id === draft.preset_id);

  useEffect(() => setDraft(provider), [provider]);

  const update = (key: string, value: unknown) => {
    setDraft((current) => ({ ...current, [key]: value }));
  };

  const testVoice = async () => {
    await onChange(draft);
    setStatus(t("speech.tts.synthesizing"));
    try {
      await playText("Hello, this is a test of the voice.", undefined, {
        voiceOverride: draft.voice,
        instructionsOverride: String(draft.extra?.instructions ?? ""),
        bypassCache: true,
      });
      setStatus(t("speech.tts.playbackComplete"));
    } catch (error) {
      setStatus(error instanceof Error ? error.message : t("speech.tts.voiceTestFailed"));
    }
  };

  return (
    <article className={`rounded-[24px] border p-5 ${active ? "border-text/45 bg-text/[0.03]" : "border-border bg-bg/20"}`}>
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="font-display text-lg italic">{draft.label}</h3>
            {active && <span className="rounded-full bg-text px-2 py-0.5 font-mono text-[9px] uppercase tracking-wider text-bg">{t("common.active")}</span>}
          </div>
          <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.12em] text-text-faint">{draft.family}</p>
        </div>
        <button type="button" onClick={() => void onChange(draft)} className="flex items-center gap-1 rounded-full border border-border px-3 py-1.5 text-[11px] hover:bg-glass">
          <Save size={12} /> {t("common.save")}
        </button>
      </div>
      <div className="mt-5 grid gap-4 md:grid-cols-2">
        {draft.family !== "edge" && (
          <label className="text-[11px] text-text-muted">{t("speech.field.baseUrl")}
            <input value={draft.base_url} onChange={(event) => update("base_url", event.target.value)} className="mt-1 h-9 w-full rounded-xl border border-border bg-bg/60 px-3 font-mono text-xs text-text" />
          </label>
        )}
        {draft.family !== "edge" && (
          <label className="text-[11px] text-text-muted">{t("settings.embedding.apiKey")}
            <input type="password" value={draft.api_key} onChange={(event) => update("api_key", event.target.value)} className="mt-1 h-9 w-full rounded-xl border border-border bg-bg/60 px-3 font-mono text-xs text-text" />
          </label>
        )}
        <label className="text-[11px] text-text-muted">{t("speech.tts.voiceId")}
          <input value={draft.voice} onChange={(event) => update("voice", event.target.value)} list={`tts-voice-options-${draft.id}`} className="mt-1 h-9 w-full rounded-xl border border-border bg-bg/60 px-3 font-mono text-xs text-text" />
        </label>
        {preset?.voices && preset.voices.length > 0 && (
          <datalist id={`tts-voice-options-${draft.id}`}>
            {preset.voices.map((voice) => <option key={voice} value={voice} />)}
          </datalist>
        )}
        {!(["edge", "azure", "volcengine"].includes(draft.family)) && (
          <label className="text-[11px] text-text-muted">{t("speech.field.model")}
            <input value={draft.model} onChange={(event) => update("model", event.target.value)} className="mt-1 h-9 w-full rounded-xl border border-border bg-bg/60 px-3 font-mono text-xs text-text" />
          </label>
        )}
        {draft.family === "volcengine" && (
          <label className="text-[11px] text-text-muted">{t("speech.tts.appId")}
            <input value={String(draft.extra?.appid ?? "")} onChange={(event) => update("extra", { ...(draft.extra ?? {}), appid: event.target.value })} className="mt-1 h-9 w-full rounded-xl border border-border bg-bg/60 px-3 font-mono text-xs text-text" />
          </label>
        )}
        {draft.family === "dashscope" && draft.model.trim().toLowerCase().startsWith("qwen") && (
          <label className="text-[11px] text-text-muted md:col-span-2">{t("speech.tts.instructions")}
            <textarea value={String(draft.extra?.instructions ?? "")} onChange={(event) => update("extra", { ...(draft.extra ?? {}), instructions: event.target.value })} rows={2} placeholder={t("speech.tts.instructionsPlaceholder")} className="mt-1 w-full rounded-xl border border-border bg-bg/60 px-3 py-2 font-mono text-xs text-text" />
          </label>
        )}
      </div>
      <div className="mt-4 flex items-center gap-3">
        <button type="button" onClick={testVoice} className="flex items-center gap-2 rounded-full bg-text px-4 py-2 text-xs font-medium text-bg disabled:opacity-40" disabled={!active || !draft.voice.trim()}>
          <Play size={13} fill="currentColor" /> {t("speech.tts.testVoice")}
        </button>
        <span aria-live="polite" className="text-[11px] text-text-muted">{status}</span>
      </div>
    </article>
  );
}
