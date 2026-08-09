// SPDX-License-Identifier: MIT
import { useState } from "react";
import { AudioLines, Check, KeyRound } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ttsPresets, type SpeechPreset } from "../../lib/speech-presets";
import { useWS } from "../../stores/ws";
import type { TtsProvider } from "../speech/TtsProviderCard";

export function StepTts({ onNext, onSkip }: { onNext: () => void; onSkip: () => void }) {
  const { t } = useTranslation();
  const config = useWS((state) => state.config);
  const send = useWS((state) => state.send);
  const [selected, setSelected] = useState<SpeechPreset | null>(null);
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [voice, setVoice] = useState("");
  const [model, setModel] = useState("");
  const [error, setError] = useState("");

  const choose = (preset: SpeechPreset) => {
    setSelected(preset);
    setBaseUrl(preset.default_base_url ?? "");
    setApiKey("");
    setVoice("");
    setModel("");
    setError("");
  };

  const save = () => {
    if (!selected) return;
    const modelRequired = ["openai_compat", "elevenlabs", "dashscope", "minimax"].includes(selected.family);
    if (!voice.trim()) return setError(t("onboarding.tts.errVoice"));
    if (modelRequired && !model.trim()) return setError(t("onboarding.tts.errModel"));
    if (selected.family !== "edge" && !baseUrl.trim()) return setError(t("onboarding.tts.errBaseUrl"));
    if (selected.api_key_required && !apiKey.trim()) return setError(t("onboarding.tts.errApiKey"));
    const tts = (config?.tts ?? {}) as Record<string, unknown>;
    const providers = Array.isArray(tts.providers) ? tts.providers as TtsProvider[] : [];
    const now = new Date().toISOString();
    const provider: TtsProvider = {
      id: `p_t_${crypto.randomUUID().slice(0, 8)}`,
      preset_id: selected.id,
      label: selected.label,
      family: selected.family,
      base_url: baseUrl.trim(),
      api_key: apiKey,
      voice: voice.trim(),
      model: model.trim(),
      enabled: true,
      created_at: now,
      updated_at: now,
    };
    send({ type: "settings.patch", patch: { "tts.providers": [...providers, provider], "tts.active": provider.id } });
    send({ type: "onboarding.complete_step", step: "tts", data: { preset_id: selected.id } });
    onNext();
  };

  const skip = () => {
    send({ type: "onboarding.skip_step", step: "tts" });
    onSkip();
  };

  return (
    <div className="mx-auto max-w-5xl">
      <div className="flex items-start gap-4">
        <div className="rounded-2xl bg-text p-3 text-bg"><AudioLines size={21} /></div>
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-text-faint">{t("onboarding.optional")}</p>
          <h2 className="font-display text-3xl italic">{t("onboarding.tts.title")}</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-text-muted">{t("onboarding.tts.description")}</p>
        </div>
      </div>
      <div className="mt-7 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {ttsPresets.map((preset) => (
          <button type="button" key={preset.id} onClick={() => choose(preset)} className={`rounded-[22px] border p-4 text-left transition ${selected?.id === preset.id ? "border-text bg-text text-bg" : "border-border bg-bg/25 hover:border-text/35"}`}>
            <div className="flex items-start justify-between gap-3"><span className="font-display text-sm italic">{preset.label}</span>{selected?.id === preset.id && <Check size={14} />}</div>
            <div className={`mt-3 flex items-center gap-1 font-mono text-[9px] uppercase tracking-wider ${selected?.id === preset.id ? "text-bg/65" : "text-text-faint"}`}>{preset.api_key_required ? <><KeyRound size={10} /> {t("speech.catalog.apiKey")}</> : t("speech.catalog.noApiKey")}</div>
          </button>
        ))}
      </div>
      {selected && (
        <div className="glass mt-6 rounded-[26px] p-5">
          <div className="grid gap-4 md:grid-cols-2">
            {selected.family !== "edge" && (
              <label className="text-xs text-text-muted">{t("speech.field.baseUrl")}<input value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} className="mt-1 h-10 w-full rounded-xl border border-border bg-bg/60 px-3 font-mono text-xs text-text" /></label>
            )}
            {selected.api_key_required && (
              <label className="text-xs text-text-muted">{t("settings.embedding.apiKey")}<input type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} className="mt-1 h-10 w-full rounded-xl border border-border bg-bg/60 px-3 font-mono text-xs text-text" /></label>
            )}
            <label className="text-xs text-text-muted">{t("speech.tts.voiceId")}<input value={voice} onChange={(event) => setVoice(event.target.value)} placeholder={selected.voice_placeholder} className="mt-1 h-10 w-full rounded-xl border border-border bg-bg/60 px-3 font-mono text-xs text-text" /></label>
            {!["edge", "azure", "volcengine"].includes(selected.family) && (
              <label className="text-xs text-text-muted">{t("speech.field.model")}<input value={model} onChange={(event) => setModel(event.target.value)} placeholder={selected.model_placeholder} className="mt-1 h-10 w-full rounded-xl border border-border bg-bg/60 px-3 font-mono text-xs text-text" /></label>
            )}
          </div>
        </div>
      )}
      {error && <p role="alert" className="mt-4 text-xs text-red-400">{error}</p>}
      <div className="mt-7 flex gap-3">
        <button type="button" onClick={save} disabled={!selected} className="rounded-full bg-text px-5 py-2.5 text-sm text-bg disabled:opacity-35">{t("onboarding.saveAndNext")}</button>
        <button type="button" onClick={skip} className="rounded-full border border-border px-5 py-2.5 text-sm text-text-muted hover:text-text">{t("onboarding.skip")}</button>
      </div>
    </div>
  );
}