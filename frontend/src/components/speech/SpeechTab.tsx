// SPDX-License-Identifier: MIT
import { useState } from "react";
import { AudioLines, Mic2, Plus, Trash2 } from "lucide-react";
import { useWS } from "../../stores/ws";
import { useSpeechStore } from "../../stores/speech";
import { useTranslation } from "react-i18next";
import { Switch } from "../ui/primitives";
import { asrPresets, ttsPresets, type SpeechPreset } from "../../lib/speech-presets";
import { TtsProviderCard, type TtsProvider } from "./TtsProviderCard";
import { AsrProviderCard, type AsrProvider } from "./AsrProviderCard";

function records<T>(config: Record<string, unknown> | null, key: "tts" | "asr"): T[] {
  const section = (config?.[key] ?? {}) as Record<string, unknown>;
  return Array.isArray(section.providers) ? section.providers as T[] : [];
}

function active(config: Record<string, unknown> | null, key: "tts" | "asr") {
  const section = (config?.[key] ?? {}) as Record<string, unknown>;
  return String(section.active ?? "");
}

function providerId(prefix: "t" | "a") {
  return `p_${prefix}_${crypto.randomUUID().slice(0, 8)}`;
}

function Catalog({ presets, onAdd }: { presets: SpeechPreset[]; onAdd: (preset: SpeechPreset) => void }) {
  const { t } = useTranslation();
  return (
    <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
      {presets.map((preset) => (
        <button key={preset.id} type="button" disabled={preset.deferred} onClick={() => onAdd(preset)} className="group rounded-2xl border border-border bg-bg/20 p-4 text-left transition hover:-translate-y-0.5 hover:border-text/35 hover:bg-glass disabled:cursor-not-allowed disabled:opacity-45">
          <div className="flex items-center justify-between gap-3"><span className="font-display text-sm italic">{preset.label}</span><Plus size={13} className="text-text-faint transition group-hover:text-text" /></div>
          <div className="mt-2 font-mono text-[9px] uppercase tracking-[0.12em] text-text-faint">{preset.api_key_required ? t("speech.catalog.apiKey") : t("speech.catalog.noApiKey")}{preset.deferred ? " · " + t("speech.catalog.deferred") : ""}</div>
        </button>
      ))}
    </div>
  );
}

export function SpeechTab() {
  const { t } = useTranslation();
  const config = useWS((state) => state.config);
  const client = useWS((state) => state.client);
  const send = useWS((state) => state.send);
  const ttsConfigured = useSpeechStore((state) => state.isTtsConfigured);
  const asrConfigured = useSpeechStore((state) => state.isAsrConfigured);
  const autoplay = useSpeechStore((state) => state.autoplay);
  const toggleAutoplay = useSpeechStore((state) => state.toggleAutoplay);
  const [configureTts, setConfigureTts] = useState(false);
  const [configureAsr, setConfigureAsr] = useState(false);
  const ttsProviders = records<TtsProvider>(config, "tts");
  const asrProviders = records<AsrProvider>(config, "asr");
  const ttsActive = active(config, "tts");
  const asrActive = active(config, "asr");
  const tts = (config?.tts ?? {}) as Record<string, unknown>;

  const patch = (values: Record<string, unknown>) => send({ type: "settings.patch", patch: values });
  const patchAndWait = (values: Record<string, unknown>) => {
    if (!client) {
      patch(values);
      return Promise.resolve();
    }
    return new Promise<void>((resolve) => {
      let detach = () => {};
      const timeout = window.setTimeout(() => { detach(); resolve(); }, 2000);
      detach = client.on((message) => {
        if (message.type !== "settings.changed") return;
        if (!Object.keys(values).some((key) => key in message.patch)) return;
        window.clearTimeout(timeout);
        detach();
        resolve();
      });
      patch(values);
    });
  };

  const addTts = (preset: SpeechPreset) => {
    const now = new Date().toISOString();
    const provider: TtsProvider = {
      id: providerId("t"), preset_id: preset.id, label: preset.label, family: preset.family,
      base_url: preset.default_base_url ?? "", api_key: "", voice: "", model: "", enabled: true,
      created_at: now, updated_at: now,
    };
    patch({ "tts.providers": [...ttsProviders, provider], "tts.active": provider.id });
    setConfigureTts(false);
  };

  const addAsr = (preset: SpeechPreset) => {
    const now = new Date().toISOString();
    const provider: AsrProvider = {
      id: providerId("a"), preset_id: preset.id, label: preset.label, family: preset.family,
      base_url: preset.default_base_url ?? "", api_key: "", model: "", language: "", enabled: true,
      created_at: now, updated_at: now,
    };
    patch({ "asr.providers": [...asrProviders, provider], "asr.active": provider.id });
    setConfigureAsr(false);
  };

  const updateTts = (provider: TtsProvider) => patchAndWait({ "tts.providers": ttsProviders.map((item) => item.id === provider.id ? { ...provider, updated_at: new Date().toISOString() } : item) });
  const updateAsr = (provider: AsrProvider) => patchAndWait({ "asr.providers": asrProviders.map((item) => item.id === provider.id ? { ...provider, updated_at: new Date().toISOString() } : item) });
  const removeTts = (id: string) => patch({ "tts.providers": ttsProviders.filter((item) => item.id !== id), ...(ttsActive === id ? { "tts.active": "" } : {}) });
  const removeAsr = (id: string) => patch({ "asr.providers": asrProviders.filter((item) => item.id !== id), ...(asrActive === id ? { "asr.active": "" } : {}) });

  return (
    <div className="space-y-8">
      <section className="rounded-[26px] border border-border bg-bg/15 p-5">
        <div className="flex items-start gap-3"><div className="rounded-2xl bg-text p-2 text-bg"><AudioLines size={17} /></div><div className="flex-1"><h2 className="font-display text-xl italic">{t("speech.tab.ttsTitle")}</h2><p className="mt-1 text-xs leading-5 text-text-muted">{t("speech.tab.ttsDesc")}</p></div></div>
        {!ttsConfigured && !configureTts ? (
          <div className="mt-5 flex items-center justify-between rounded-2xl border border-dashed border-border px-4 py-3"><span className="text-xs text-text-muted">{t("speech.tab.ttsNotConfigured")}</span><button type="button" onClick={() => setConfigureTts(true)} className="rounded-full bg-text px-4 py-2 text-xs text-bg">{t("speech.tts.configureNow")}</button></div>
        ) : (
          <div className="mt-5 space-y-4">
            {ttsProviders.length > 0 && <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-border px-4 py-3"><label className="text-[11px] text-text-muted">{t("speech.tab.activeProvider")} <select value={ttsActive} onChange={(event) => patch({ "tts.active": event.target.value })} className="ml-2 rounded-full border border-border bg-bg px-3 py-1.5 text-xs text-text"><option value="">{t("common.none")}</option>{ttsProviders.map((provider) => <option key={provider.id} value={provider.id}>{provider.label}</option>)}</select></label><label className="ml-auto flex items-center gap-2 text-xs"><Switch checked={autoplay} onChange={toggleAutoplay} label={t("speech.tab.autoplayReplies")} /></label><label className="w-full text-[11px] text-text-muted">{t("speech.tab.globalFallbackVoice")}<input value={String(tts.default_voice ?? "")} onChange={(event) => patch({ "tts.default_voice": event.target.value })} placeholder={t("speech.tab.fallbackVoicePlaceholder")} className="mt-1 h-9 w-full rounded-xl border border-border bg-bg/60 px-3 font-mono text-xs text-text" /></label></div>}
            {ttsProviders.map((provider) => <div key={provider.id} className="relative"><TtsProviderCard provider={provider} active={provider.id === ttsActive} onChange={updateTts} /><button type="button" aria-label={t("common.remove") + " " + provider.label} onClick={() => removeTts(provider.id)} className="absolute bottom-5 right-5 rounded-full p-2 text-text-faint hover:bg-red-500/10 hover:text-red-400"><Trash2 size={13} /></button></div>)}
            <div><div className="mb-3 font-mono text-[10px] uppercase tracking-[0.14em] text-text-faint">{t("speech.tab.addTtsProvider")}</div><Catalog presets={ttsPresets} onAdd={addTts} /></div>
          </div>
        )}
      </section>

      <section className="rounded-[26px] border border-border bg-bg/15 p-5">
        <div className="flex items-start gap-3"><div className="rounded-2xl border border-border p-2 text-text"><Mic2 size={17} /></div><div className="flex-1"><h2 className="font-display text-xl italic">{t("speech.tab.asrTitle")}</h2><p className="mt-1 text-xs leading-5 text-text-muted">{t("speech.tab.asrDesc")}</p></div></div>
        {!asrConfigured && !configureAsr ? (
          <div className="mt-5 flex items-center justify-between rounded-2xl border border-dashed border-border px-4 py-3"><span className="text-xs text-text-muted">{t("speech.tab.asrNotConfigured")}</span><button type="button" onClick={() => setConfigureAsr(true)} className="rounded-full bg-text px-4 py-2 text-xs text-bg">{t("speech.tts.configureNow")}</button></div>
        ) : (
          <div className="mt-5 space-y-4">
            {asrProviders.length > 0 && <div className="rounded-2xl border border-border px-4 py-3"><label className="text-[11px] text-text-muted">{t("speech.tab.activeProvider")} <select value={asrActive} onChange={(event) => patch({ "asr.active": event.target.value })} className="ml-2 rounded-full border border-border bg-bg px-3 py-1.5 text-xs text-text"><option value="">{t("common.none")}</option>{asrProviders.map((provider) => <option key={provider.id} value={provider.id}>{provider.label}</option>)}</select></label></div>}
            {asrProviders.map((provider) => <div key={provider.id} className="relative"><AsrProviderCard provider={provider} active={provider.id === asrActive} onChange={updateAsr} /><button type="button" aria-label={t("common.remove") + " " + provider.label} onClick={() => removeAsr(provider.id)} className="absolute bottom-5 right-5 rounded-full p-2 text-text-faint hover:bg-red-500/10 hover:text-red-400"><Trash2 size={13} /></button></div>)}
            <div><div className="mb-3 font-mono text-[10px] uppercase tracking-[0.14em] text-text-faint">{t("speech.tab.addAsrProvider")}</div><Catalog presets={asrPresets} onAdd={addAsr} /></div>
          </div>
        )}
      </section>
    </div>
  );
}
