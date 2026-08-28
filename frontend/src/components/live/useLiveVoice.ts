// SPDX-License-Identifier: MIT
import { useEffect, useRef, useState } from "react";
import { LiveVad } from "../../lib/vad";
import { useSpeechStore } from "../../stores/speech";
import { useWS } from "../../stores/ws";
import { useSessions } from "../../stores/sessions";
import { useCardsStore } from "../../stores/cards";

export interface UserLine {
  id: string;
  role: "user";
  text: string;
}

export interface LiveVoiceResult {
  muted: boolean;
  listening: boolean;
  userSpeaking: boolean;
  permissionDenied: boolean;
  vadError: string | null;
  asrNotConfigured: boolean;
  userLines: UserLine[];
  busy: boolean;
  toggleMute: () => void;
  retryVad: () => void;
}

export function useLiveVoice(config: {
  characterId: number | null;
  voiceOverride?: string;
  instructionsOverride?: string;
}): LiveVoiceResult {
  const [muted, setMuted] = useState(true);
  const [listening, setListening] = useState(false);
  const [userSpeaking, setUserSpeaking] = useState(false);
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [vadError, setVadError] = useState<string | null>(null);
  const [userLines, setUserLines] = useState<UserLine[]>([]);
  const [busy, setBusy] = useState(false);

  const vadRef = useRef<LiveVad | null>(null);
  const busyRef = useRef(false);
  const mutedRef = useRef(true);

  const { isAsrConfigured } = useSpeechStore.getState();
  const asrNotConfigured = !isAsrConfigured;

  const startVad = () => {
    const client = useWS.getState().client;
    if (!client) {
      setVadError("ws");
      return;
    }
    setVadError(null);
    setPermissionDenied(false);
    setMuted(false);
    mutedRef.current = false;

    const vad = new LiveVad({
      onSpeechEnd: (blob) => {
        void (async () => {
          if (busyRef.current || mutedRef.current) return;
          busyRef.current = true;
          setBusy(true);
          try {
            const text = await useSpeechStore.getState().transcribeAudio(blob);
            if (!text.trim()) {
              busyRef.current = false;
              setBusy(false);
              return;
            }
            const lineId = `user_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
            setUserLines((prev) => [...prev, { id: lineId, role: "user", text: text.trim() }]);
            client.send({
              type: "chat.send",
              mode: "companion",
              character_id: config.characterId ?? undefined,
              content: text.trim(),
            });
          } catch {
            busyRef.current = false;
            setBusy(false);
          }
        })();
      },
      onError: (error) => {
        const msg = error instanceof Error ? error.message : String(error);
        setVadError(msg.includes("Permission") ? "mic-permission" : "vad");
        setPermissionDenied(msg.includes("Permission"));
      },
    });
    vadRef.current = vad;
    vad
      .start()
      .then(() => {
        setListening(true);
        setUserSpeaking(false);
      })
      .catch((error: unknown) => {
        const msg = error instanceof Error ? error.message : String(error);
        setVadError(msg.includes("Permission") ? "mic-permission" : "vad");
        setPermissionDenied(msg.includes("Permission"));
        setListening(false);
      });
  };

  // Start listening on mount; tear down on unmount.
  useEffect(() => {
    if (asrNotConfigured) return;
    startVad();
    return () => {
      vadRef.current?.destroy();
      vadRef.current = null;
      useSpeechStore.getState().stopAudio();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [asrNotConfigured]);

  // Watch chat.done to speak the completed reply.
  useEffect(() => {
    const client = useWS.getState().client;
    if (!client) return;
    return client.on((msg) => {
      if (msg.type !== "chat.done" || msg.outcome !== "success") return;
      if (!msg.conversation_id) return;
      const convId = msg.conversation_id;
      const history = useSessions.getState().liveHistory[convId] ?? [];
      const lastAssistant = [...history]
        .reverse()
        .find((m) => m.role === "assistant");
      if (!lastAssistant || !lastAssistant.content.trim()) {
        busyRef.current = false;
        setBusy(false);
        return;
      }
      const character = useCardsStore
        .getState()
        .characters.find((c) => c.id === config.characterId);
      void useSpeechStore
        .getState()
        .playText(lastAssistant.content, lastAssistant.id, {
          voiceOverride: config.voiceOverride ?? String(character?.tts_voice ?? ""),
          instructionsOverride:
            config.instructionsOverride ?? String(character?.tts_instructions ?? ""),
        })
        .finally(() => {
          busyRef.current = false;
          setBusy(false);
        });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggleMute = () => {
    const vad = vadRef.current;
    if (!vad) return;
    if (mutedRef.current) {
      vad.resume();
      mutedRef.current = false;
      setMuted(false);
      setListening(true);
    } else {
      vad.pause();
      mutedRef.current = true;
      setMuted(true);
      setListening(false);
    }
  };

  const retryVad = () => {
    setVadError(null);
    startVad();
  };

  return {
    muted,
    listening,
    userSpeaking,
    permissionDenied,
    vadError,
    asrNotConfigured,
    userLines,
    busy,
    toggleMute,
    retryVad,
  };
}
