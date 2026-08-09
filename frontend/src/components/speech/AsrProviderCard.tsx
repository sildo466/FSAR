// SPDX-License-Identifier: MIT
import { useEffect, useState } from "react";
import { Mic, Save } from "lucide-react";
import { useSpeechStore } from "../../stores/speech";
import { useTranslation } from "react-i18next";
import { FasterWhisperModelPicker } from "./FasterWhisperModelPicker";

export interface AsrProvider {
  id: string;
  preset_id: string;
  label: string;
  family: string;
  base_url: string;
  api_key: string;
  model: string;
  language: string;
  enabled: boolean;
  [key: string]: unknown;
}

interface Props {
  provider: AsrProvider;
  active: boolean;
  onChange: (provider: AsrProvider) => void | Promise<void>;
}

export function AsrProviderCard({ provider, active, onChange }: Props) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState(provider);
  const [status, setStatus] = useState("");
  const transcribe = useSpeechStore((state) => state.transcribeAudio);

  useEffect(() => setDraft(provider), [provider]);

  const update = (key: string, value: unknown) => setDraft((current) => ({ ...current, [key]: value }));

  const testMic = async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      setStatus(t("speech.asr.micUnavailable"));
      return;
    }
    await onChange(draft);
    setStatus(t("speech.asr.listening"));
    let stream: MediaStream | null = null;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      const chunks: BlobPart[] = [];
      recorder.ondataavailable = (event) => chunks.push(event.data);
      const stopped = new Promise<void>((resolve) => { recorder.onstop = () => resolve(); });
      recorder.start();
      await new Promise((resolve) => window.setTimeout(resolve, 3000));
      recorder.stop();
      await stopped;
      const text = await transcribe(new Blob(chunks, { type: recorder.mimeType || "audio/webm" }));
      setStatus(text ? t("speech.asr.heard", { text }) : t("speech.asr.noSpeech"));
    } catch (error) {
      setStatus(error instanceof Error ? error.message : t("speech.asr.micTestFailed"));
    } finally {
      stream?.getTracks().forEach((track) => track.stop());
    }
  };

  return (
    <article className={`rounded-[24px] border p-5 ${active ? "border-text/45 bg-text/[0.03]" : "border-border bg-bg/20"}`}>
      <div className="flex items-start justify-between gap-4">
        <div><h3 className="font-display text-lg italic">{draft.label}</h3><p className="mt-1 font-mono text-[10px] uppercase tracking-[0.12em] text-text-faint">{draft.family === "local" ? t("speech.asr.privateLocal") : draft.family}</p></div>
        <button type="button" onClick={() => void onChange(draft)} className="flex items-center gap-1 rounded-full border border-border px-3 py-1.5 text-[11px] hover:bg-glass"><Save size={12} /> {t("common.save")}</button>
      </div>
      <div className="mt-5 grid gap-4 md:grid-cols-2">
        {draft.family !== "local" && <label className="text-[11px] text-text-muted">{t("speech.field.baseUrl")}<input value={draft.base_url} onChange={(event) => update("base_url", event.target.value)} className="mt-1 h-9 w-full rounded-xl border border-border bg-bg/60 px-3 font-mono text-xs text-text" /></label>}
        {draft.family !== "local" && <label className="text-[11px] text-text-muted">{t("settings.embedding.apiKey")}<input type="password" value={draft.api_key} onChange={(event) => update("api_key", event.target.value)} className="mt-1 h-9 w-full rounded-xl border border-border bg-bg/60 px-3 font-mono text-xs text-text" /></label>}
        {draft.family !== "local" && <label className="text-[11px] text-text-muted">{t("speech.field.model")}<input value={draft.model} onChange={(event) => update("model", event.target.value)} className="mt-1 h-9 w-full rounded-xl border border-border bg-bg/60 px-3 font-mono text-xs text-text" /></label>}
        <label className="text-[11px] text-text-muted">{t("speech.asr.language")}<input value={draft.language} onChange={(event) => update("language", event.target.value)} placeholder={t("speech.asr.languageAuto")} className="mt-1 h-9 w-full rounded-xl border border-border bg-bg/60 px-3 font-mono text-xs text-text" /></label>
      </div>
      {draft.family === "local" && <div className="mt-4"><FasterWhisperModelPicker selected={draft.model} onSelect={(model) => update("model", model)} /></div>}
      <div className="mt-4 flex items-center gap-3"><button type="button" disabled={!active || !draft.model} onClick={() => void testMic()} className="flex items-center gap-2 rounded-full bg-text px-4 py-2 text-xs font-medium text-bg disabled:opacity-40"><Mic size={13} /> {t("speech.asr.testMic")}</button><span aria-live="polite" className="text-[11px] text-text-muted">{status}</span></div>
    </article>
  );
}
