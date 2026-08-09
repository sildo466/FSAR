// SPDX-License-Identifier: MIT
import { useState } from "react";
import { Check, Mic2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { asrPresets, type SpeechPreset } from "../../lib/speech-presets";
import { useWS } from "../../stores/ws";
import type { AsrProvider } from "../speech/AsrProviderCard";

export function StepAsr({ onNext, onSkip }: { onNext: () => void; onSkip: () => void }) {
  const { t } = useTranslation();
  const config = useWS((state) => state.config);
  const send = useWS((state) => state.send);
  const [selected, setSelected] = useState<SpeechPreset | null>(null);
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("");
  const [language, setLanguage] = useState("");
  const [error, setError] = useState("");

  const choose = (preset: SpeechPreset) => {
    if (preset.deferred) return;
    setSelected(preset);
    setBaseUrl(preset.default_base_url ?? "");
    setApiKey("");
    setModel("");
    setLanguage("");
    setError("");
  };

  const save = () => {
    if (!selected) return;
    if (!model.trim()) return setError(t("onboarding.asr.errModel"));
    if (selected.family !== "local" && !baseUrl.trim()) return setError(t("onboarding.asr.errBaseUrl"));
    if (selected.api_key_required && !apiKey.trim()) return setError(t("onboarding.asr.errApiKey"));
    const asr = (config?.asr ?? {}) as Record<string, unknown>;
    const providers = Array.isArray(asr.providers) ? asr.providers as AsrProvider[] : [];
    const now = new Date().toISOString();
    const provider: AsrProvider = {
      id: `p_a_${crypto.randomUUID().slice(0, 8)}`,
      preset_id: selected.id,
      label: selected.label,
      family: selected.family,
      base_url: baseUrl.trim(),
      api_key: apiKey,
      model: model.trim(),
      language: language.trim(),
      enabled: true,
      created_at: now,
      updated_at: now,
    };
    send({ type: "settings.patch", patch: { "asr.providers": [...providers, provider], "asr.active": provider.id } });
    send({ type: "onboarding.complete_step", step: "asr", data: { preset_id: selected.id } });
    onNext();
  };

  const skip = () => {
    send({ type: "onboarding.skip_step", step: "asr" });
    onSkip();
  };

  return (
    <div className="mx-auto max-w-5xl">
      <div className="flex items-start gap-4">
        <div className="rounded-2xl border border-border p-3"><Mic2 size={21} /></div>
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-text-faint">{t("onboarding.optional")}</p>
          <h2 className="font-display text-3xl italic">{t("onboarding.asr.title")}</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-text-muted">{t("onboarding.asr.description")}</p>
        </div>
      </div>
      <div className="mt-7 grid gap-3 sm:grid-cols-3">
        {asrPresets.map((preset) => (
          <button type="button" key={preset.id} disabled={preset.deferred} onClick={() => choose(preset)} className={`rounded-[22px] border p-4 text-left transition disabled:cursor-not-allowed disabled:opacity-40 ${selected?.id === preset.id ? "border-text bg-text text-bg" : "border-border bg-bg/25 hover:border-text/35"}`}>
            <div className="flex items-start justify-between gap-3"><span className="font-display text-sm italic">{preset.label}</span>{selected?.id === preset.id && <Check size={14} />}</div>
            <div className={`mt-3 font-mono text-[9px] uppercase tracking-wider ${selected?.id === preset.id ? "text-bg/65" : "text-text-faint"}`}>{preset.deferred ? t("speech.catalog.deferred") : preset.family === "local" ? t("onboarding.asr.localPrivate") : t("onboarding.asr.cloudApi")}</div>
          </button>
        ))}
      </div>
      {selected && (
        <div className="glass mt-6 rounded-[26px] p-5">
          <div className="grid gap-4 md:grid-cols-2">
            {selected.family !== "local" && (
              <label className="text-xs text-text-muted">{t("speech.field.baseUrl")}<input value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} className="mt-1 h-10 w-full rounded-xl border border-border bg-bg/60 px-3 font-mono text-xs text-text" /></label>
            )}
            {selected.api_key_required && (
              <label className="text-xs text-text-muted">{t("settings.embedding.apiKey")}<input type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} className="mt-1 h-10 w-full rounded-xl border border-border bg-bg/60 px-3 font-mono text-xs text-text" /></label>
            )}
            <label className="text-xs text-text-muted">{t("speech.field.model")}<input value={model} onChange={(event) => setModel(event.target.value)} placeholder={selected.model_placeholder} className="mt-1 h-10 w-full rounded-xl border border-border bg-bg/60 px-3 font-mono text-xs text-text" /></label>
            <label className="text-xs text-text-muted">{t("speech.asr.language")}<input value={language} onChange={(event) => setLanguage(event.target.value)} placeholder={selected.language_placeholder || t("speech.asr.languageAuto")} className="mt-1 h-10 w-full rounded-xl border border-border bg-bg/60 px-3 font-mono text-xs text-text" /></label>
          </div>
          {selected.family === "local" && <p className="mt-3 text-[11px] text-text-muted">{t("onboarding.asr.localHint")}</p>}
        </div>
      )}
      {error && <p role="alert" className="mt-4 text-xs text-red-400">{error}</p>}
      <div className="mt-7 flex gap-3">
        <button type="button" onClick={save} disabled={!selected} className="rounded-full bg-text px-5 py-2.5 text-sm text-bg disabled:opacity-35">{t("onboarding.saveAndFinish")}</button>
        <button type="button" onClick={skip} className="rounded-full border border-border px-5 py-2.5 text-sm text-text-muted hover:text-text">{t("onboarding.skip")}</button>
      </div>
    </div>
  );
}