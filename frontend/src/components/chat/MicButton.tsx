// SPDX-License-Identifier: MIT
import { useEffect, useRef, useState } from "react";
import { LoaderCircle, Mic, MicOff } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useSpeechStore } from "../../stores/speech";

type MicState = "idle" | "recording" | "processing" | "error";

async function containsSpeech(blob: Blob): Promise<boolean> {
  if (!window.AudioContext) return true;
  const context = new AudioContext();
  try {
    const buffer = await context.decodeAudioData(await blob.arrayBuffer());
    const samples = buffer.getChannelData(0);
    if (samples.length === 0) return false;
    const rms = Math.sqrt(samples.reduce((sum, sample) => sum + sample * sample, 0) / samples.length);
    return rms >= 0.005;
  } catch {
    return true;
  } finally {
    void context.close();
  }
}

export function MicButton({ onTranscript }: { onTranscript: (text: string) => void }) {
  const { t } = useTranslation();
  const configured = useSpeechStore((state) => state.isAsrConfigured);
  const transcribe = useSpeechStore((state) => state.transcribeAudio);
  const [state, setState] = useState<MicState>("idle");
  const [error, setError] = useState("");
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const chunks = useRef<BlobPart[]>([]);
  const stopping = useRef(false);

  useEffect(() => {
    return () => {
      recorder.current?.stop();
      stream.current?.getTracks().forEach((track) => track.stop());
    };
  }, []);

  if (!configured) return null;

  const fail = (message: string) => {
    setError(message);
    setState("error");
    window.setTimeout(() => { setState("idle"); setError(""); }, 1500);
  };

  const start = async () => {
    if (state !== "idle") return;
    setState("recording");
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ audio: true });
      const preferred = "audio/webm;codecs=opus";
      const options = MediaRecorder.isTypeSupported?.(preferred) ? { mimeType: preferred } : undefined;
      recorder.current = new MediaRecorder(stream.current, options);
      chunks.current = [];
      recorder.current.ondataavailable = (event) => { if (event.data.size) chunks.current.push(event.data); };
      recorder.current.start();
    } catch (requestError) {
      stream.current?.getTracks().forEach((track) => track.stop());
      stream.current = null;
      fail(requestError instanceof Error ? requestError.message : "Microphone permission denied");
    }
  };

  const finish = async (active: MediaRecorder) => {
    if (stopping.current) return;
    stopping.current = true;
    setState("processing");
    const stopped = new Promise<void>((resolve) => { active.onstop = () => resolve(); });
    active.stop();
    await stopped;
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
    const blob = new Blob(chunks.current, { type: active.mimeType || "audio/webm" });
    try {
      if (!(await containsSpeech(blob))) {
        fail("No speech detected");
        return;
      }
      const text = await transcribe(blob);
      if (text) onTranscript(text);
      setState("idle");
    } catch (requestError) {
      fail(requestError instanceof Error ? requestError.message : "Transcription failed");
    } finally {
      stopping.current = false;
      recorder.current = null;
    }
  };

  const toggle = () => {
    if (state === "idle") void start();
    else if (state === "recording" && recorder.current) void finish(recorder.current);
  };

  const Icon = state === "processing" ? LoaderCircle : state === "error" ? MicOff : Mic;
  const label = state === "recording" ? t("mic.stopRecording") : state === "processing" ? t("mic.transcribing") : t("mic.startRecording");
  return <div className="relative"><button type="button" aria-label={label} aria-pressed={state === "recording"} onClick={toggle} disabled={state === "processing"} className={`flex h-9 w-9 items-center justify-center rounded-full transition ${state === "recording" ? "animate-pulse bg-red-500 text-white" : state === "processing" ? "bg-amber-500/15 text-amber-500" : state === "error" ? "bg-red-500/15 text-red-400" : "text-text-muted hover:bg-glass hover:text-text"}`}><Icon size={15} className={state === "processing" ? "animate-spin" : ""} /></button>{error && <span role="status" className="absolute bottom-11 right-0 w-max max-w-56 rounded-xl bg-bg px-3 py-2 text-[10px] text-red-400 shadow-lg">{error}</span>}</div>;
}
