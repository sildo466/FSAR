// SPDX-License-Identifier: MIT
import { create } from "zustand";
import type { ClientMsg, ServerMsg, WSClient } from "../lib/ws-client";
import { useWS } from "./ws";
import { stripThinkBlocks } from "../lib/thinking";
import { VrmLipsync } from "../lib/vrm-lipsync";
import profileJson from "../assets/lipsync/profile.json";
import type { Profile } from "wlipsync";

interface ModelCatalog {
  downloaded: string[];
  available: string[];
  sizes: Record<string, number>;
}

export type EndpointSource = "override" | "mirror" | "official";

export interface LastDownloadEndpoint {
  url: string;
  source: EndpointSource;
}

interface SpeechState {
  isTtsConfigured: boolean;
  isAsrConfigured: boolean;
  autoplay: boolean;
  playingMessageId: string | null;
  playbackProgress: number;
  downloadProgress: Record<string, number>;
  lastDownloadEndpoint: LastDownloadEndpoint | null;
  syncConfig: (config: Record<string, unknown> | null) => void;
  toggleAutoplay: () => void;
  playText: (text: string, messageId?: string, options?: { bypassCache?: boolean; voiceOverride?: string; instructionsOverride?: string }) => Promise<void>;
  stopAudio: () => void;
  subscribeAudioLevel: (cb: (level: number) => void) => () => void;
  subscribePlaying: (cb: (playing: boolean) => void) => () => void;
  transcribeAudio: (blob: Blob) => Promise<string>;
  listDownloadedModels: () => Promise<ModelCatalog>;
  downloadModel: (size: string) => Promise<void>;
  deleteModel: (size: string) => Promise<void>;
}

let finishCurrentAudio: (() => void) | null = null;

// Playback uses a single shared AudioContext. TTS audio is decoded into an
// AudioBuffer and played through AudioBufferSourceNode, which is also tapped
// into the wlipsync worklet for lip-sync and the analyser for the Live wave.
let audioContext: AudioContext | null = null;
let activeSource: AudioBufferSourceNode | null = null;
let analyser: AnalyserNode | null = null;
let analyserRaf: number | null = null;
let lipsyncRef: VrmLipsync | null = null;
const audioLevelSubscribers = new Set<(level: number) => void>();
const playingSubscribers = new Set<(playing: boolean) => void>();

function notifyPlaying(playing: boolean): void {
  for (const subscriber of playingSubscribers) subscriber(playing);
}

function getAudioContext(): AudioContext | null {
  try {
    if (!audioContext) audioContext = new AudioContext();
    return audioContext;
  } catch {
    return null;
  }
}

function notifyAudioLevel(level: number): void {
  for (const subscriber of audioLevelSubscribers) subscriber(level);
}

function stopAnalyser(): void {
  if (analyserRaf !== null) {
    cancelAnimationFrame(analyserRaf);
    analyserRaf = null;
  }
  if (analyser) {
    try {
      analyser.disconnect();
    } catch {
      /* ignore */
    }
    analyser = null;
  }
  notifyAudioLevel(0);
}

/** Lazy wlipsync node shared by all live avatars while audio plays. */
export function getActiveLipsync(): VrmLipsync | null {
  return lipsyncRef;
}

async function ensureLipsync(): Promise<VrmLipsync | null> {
  const ctx = getAudioContext();
  if (!ctx) return null;
  if (lipsyncRef) return lipsyncRef;
  try {
    const created = await VrmLipsync.create(ctx, profileJson as Profile);
    lipsyncRef = created;
  } catch {
    // Lip-sync is best-effort; audio must still play without it.
    lipsyncRef = null;
  }
  return lipsyncRef;
}

function attachAnalyser(source: AudioBufferSourceNode): void {
  const ctx = getAudioContext();
  if (!ctx) return;
  stopAnalyser();
  try {
    const a = ctx.createAnalyser();
    a.fftSize = 128;
    a.smoothingTimeConstant = 0.6;
    source.connect(a);
    a.connect(ctx.destination);
    analyser = a;
    const data = new Uint8Array(a.frequencyBinCount);
    const tick = () => {
      a.getByteFrequencyData(data);
      let sum = 0;
      for (let i = 0; i < data.length; i++) sum += data[i];
      notifyAudioLevel(sum / data.length / 255);
      analyserRaf = requestAnimationFrame(tick);
    };
    analyserRaf = requestAnimationFrame(tick);
  } catch {
    /* analyser is best-effort; playback must not fail because of it */
  }
}

function speechConfig(config: Record<string, unknown> | null) {
  const tts = (config?.tts ?? {}) as Record<string, unknown>;
  const asr = (config?.asr ?? {}) as Record<string, unknown>;
  return {
    isTtsConfigured: String(tts.active ?? "") !== "",
    isAsrConfigured: String(asr.active ?? "") !== "",
    autoplay: Boolean(tts.autoplay ?? false),
  };
}

function client(): WSClient {
  const connected = useWS.getState().client;
  if (!connected) throw new Error("WebSocket is not connected");
  return connected;
}

function request<T extends ServerMsg>(
  message: ClientMsg,
  success: (incoming: ServerMsg) => incoming is T,
  timeoutMs = 60_000,
): Promise<T> {
  const socket = client();
  const requestId = "request_id" in message ? message.request_id : "";
  return new Promise((resolve, reject) => {
    const timeout = window.setTimeout(() => {
      detach();
      reject(new Error("Speech request timed out"));
    }, timeoutMs);
    const finish = () => {
      window.clearTimeout(timeout);
      detach();
    };
    const detach = socket.on((incoming) => {
      if (!("request_id" in incoming) || incoming.request_id !== requestId) return;
      if (incoming.type === "tts.error" || incoming.type === "asr.error" || incoming.type === "asr.model_download_error") {
        finish();
        reject(new Error(`${incoming.code}: ${incoming.message}`));
      } else if (success(incoming)) {
        finish();
        resolve(incoming);
      }
    });
    socket.send(message);
  });
}

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const value = String(reader.result ?? "");
      resolve(value.includes(",") ? value.slice(value.indexOf(",") + 1) : value);
    };
    reader.onerror = () => reject(new Error("Could not read recorded audio"));
    reader.readAsDataURL(blob);
  });
}

export const useSpeechStore = create<SpeechState>((set, get) => ({
  isTtsConfigured: false,
  isAsrConfigured: false,
  autoplay: false,
  playingMessageId: null,
  playbackProgress: 0,
  downloadProgress: {},
  lastDownloadEndpoint: null,
  syncConfig: (config) => set(speechConfig(config)),
  toggleAutoplay: () => {
    const next = !get().autoplay;
    useWS.getState().send({
      type: "settings.patch",
      patch: { "tts.autoplay": next },
    });
  },
  playText: async (text, messageId, options = {}) => {
    const speakable = stripThinkBlocks(text ?? "");
    if (!get().isTtsConfigured || !speakable.trim()) return;
    get().stopAudio();
    notifyPlaying(true);
    const requestId = crypto.randomUUID();
    const playbackId = messageId ?? requestId;
    set({ playingMessageId: playbackId, playbackProgress: 0 });
    try {
      const result = await request(
        {
          type: "tts.synthesize",
          request_id: requestId,
          text: speakable,
          message_id: messageId,
          voice_override: options.voiceOverride,
          instructions_override: options.instructionsOverride,
          bypass_cache: options.bypassCache,
        },
        (incoming): incoming is Extract<ServerMsg, { type: "tts.audio" }> => incoming.type === "tts.audio",
      );
      await new Promise<void>((resolve, reject) => {
        const ctx = getAudioContext();
        if (!ctx) {
          reject(new Error("Web Audio is unavailable"));
          return;
        }
        void (async () => {
          let source: AudioBufferSourceNode;
          const fail = (error: unknown) => {
            if (source && activeSource === source) {
              activeSource = null;
              finishCurrentAudio = null;
            }
            reject(error instanceof Error ? error : new Error("Audio playback failed"));
          };
          try {
            const audioBuffer = await ctx.decodeAudioData(
              await (await fetch(`data:${result.mime};base64,${result.audio}`)).arrayBuffer(),
            );
            source = ctx.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(ctx.destination);
            activeSource = source;
            attachAnalyser(source);
            const lipsync = await ensureLipsync();
            if (lipsync) lipsync.connect(source);
            const finish = () => {
              if (activeSource === source) {
                activeSource = null;
                finishCurrentAudio = null;
              }
              stopAnalyser();
              resolve();
            };
            finishCurrentAudio = finish;
            const duration = audioBuffer.duration;
            let playbackStartedAt = 0;
            const progressTimer = window.setInterval(() => {
              const elapsed = ctx.currentTime - playbackStartedAt;
              if (Number.isFinite(duration) && duration > 0) {
                set({ playbackProgress: Math.min(1, Math.max(0, elapsed) / duration) });
              }
            }, 100);
            source.onended = () => {
              window.clearInterval(progressTimer);
              finish();
            };
            await ctx.resume().catch(() => undefined);
            playbackStartedAt = ctx.currentTime;
            source.start();
          } catch (error) {
            fail(error);
          }
        })();
      });
    } finally {
      notifyPlaying(false);
      if (get().playingMessageId === playbackId) {
        set({ playingMessageId: null, playbackProgress: 0 });
      }
    }
  },
  stopAudio: () => {
    activeSource?.stop();
    activeSource = null;
    const finish = finishCurrentAudio;
    finishCurrentAudio = null;
    finish?.();
    stopAnalyser();
    notifyPlaying(false);
    set({ playingMessageId: null, playbackProgress: 0 });
  },
  subscribeAudioLevel: (cb) => {
    audioLevelSubscribers.add(cb);
    return () => audioLevelSubscribers.delete(cb);
  },
  subscribePlaying: (cb) => {
    playingSubscribers.add(cb);
    return () => playingSubscribers.delete(cb);
  },
  transcribeAudio: async (blob) => {
    if (!get().isAsrConfigured) return "";
    const requestId = crypto.randomUUID();
    const audio = await blobToBase64(blob);
    const result = await request(
      {
        type: "asr.transcribe",
        request_id: requestId,
        audio,
        mime_type: blob.type || "audio/webm",
        language: "auto",
      },
      (incoming): incoming is Extract<ServerMsg, { type: "asr.text" }> => incoming.type === "asr.text",
    );
    return result.text;
  },
  listDownloadedModels: async () => {
    const requestId = crypto.randomUUID();
    const result = await request(
      { type: "asr.model_list", request_id: requestId },
      (incoming): incoming is Extract<ServerMsg, { type: "asr.model_list_result" }> => incoming.type === "asr.model_list_result",
    );
    return {
      downloaded: result.downloaded,
      available: result.available,
      sizes: result.sizes,
    };
  },
  downloadModel: async (size) => {
    const socket = client();
    const requestId = crypto.randomUUID();
    set((state) => ({
      downloadProgress: { ...state.downloadProgress, [size]: 0 },
      lastDownloadEndpoint: null,
    }));
    await new Promise<void>((resolve, reject) => {
      const timeout = window.setTimeout(() => {
        detach();
        reject(new Error("Model download timed out"));
      }, 30 * 60_000);
      const finish = () => {
        window.clearTimeout(timeout);
        detach();
      };
      const detach = socket.on((incoming) => {
        if (!("request_id" in incoming) || incoming.request_id !== requestId) return;
        if (incoming.type === "asr.model_download_started") {
          if (incoming.endpoint && incoming.endpoint_source) {
            set({
              lastDownloadEndpoint: {
                url: incoming.endpoint,
                source: incoming.endpoint_source,
              },
            });
          }
        } else if (incoming.type === "asr.model_download_progress") {
          set((state) => ({
            downloadProgress: { ...state.downloadProgress, [size]: incoming.percent },
          }));
        } else if (incoming.type === "asr.model_download_done") {
          finish();
          set((state) => ({
            downloadProgress: { ...state.downloadProgress, [size]: 100 },
            lastDownloadEndpoint: null,
          }));
          resolve();
        } else if (incoming.type === "asr.model_download_error") {
          finish();
          set({ lastDownloadEndpoint: null });
          reject(new Error(`${incoming.code}: ${incoming.message}`));
        }
      });
      socket.send({ type: "asr.model_download", request_id: requestId, size });
    });
  },
  deleteModel: async (size) => {
    const requestId = crypto.randomUUID();
    await request(
      { type: "asr.model_delete", request_id: requestId, size },
      (incoming): incoming is Extract<ServerMsg, { type: "asr.model_deleted" }> => incoming.type === "asr.model_deleted",
    );
    set((state) => {
      const progress = { ...state.downloadProgress };
      delete progress[size];
      return { downloadProgress: progress };
    });
  },
}));
