// SPDX-License-Identifier: MIT
import { create } from "zustand";
import type { ClientMsg, ServerMsg, WSClient } from "../lib/ws-client";
import { useWS } from "./ws";
import { stripThinkBlocks } from "../lib/thinking";

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
  transcribeAudio: (blob: Blob) => Promise<string>;
  listDownloadedModels: () => Promise<ModelCatalog>;
  downloadModel: (size: string) => Promise<void>;
  deleteModel: (size: string) => Promise<void>;
}

let currentAudio: HTMLAudioElement | null = null;
let finishCurrentAudio: (() => void) | null = null;

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
        const audio = new Audio(`data:${result.mime};base64,${result.audio}`);
        currentAudio = audio;
        const finish = () => {
          if (currentAudio === audio) {
            currentAudio = null;
            finishCurrentAudio = null;
          }
          resolve();
        };
        const fail = (error: unknown) => {
          if (currentAudio === audio) {
            currentAudio = null;
            finishCurrentAudio = null;
          }
          reject(error instanceof Error ? error : new Error("Audio playback failed"));
        };
        finishCurrentAudio = finish;
        audio.ontimeupdate = () => {
          if (Number.isFinite(audio.duration) && audio.duration > 0) {
            set({ playbackProgress: Math.min(1, audio.currentTime / audio.duration) });
          }
        };
        audio.onended = finish;
        audio.onerror = () => fail(new Error("Audio playback failed"));
        void audio.play().catch(fail);
      });
    } finally {
      if (get().playingMessageId === playbackId) {
        set({ playingMessageId: null, playbackProgress: 0 });
      }
    }
  },
  stopAudio: () => {
    currentAudio?.pause();
    currentAudio = null;
    const finish = finishCurrentAudio;
    finishCurrentAudio = null;
    finish?.();
    set({ playingMessageId: null, playbackProgress: 0 });
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
