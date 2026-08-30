// SPDX-License-Identifier: MIT
import { useEffect, useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";
import { AvatarCanvas } from "../components/live/AvatarCanvas";
import type { AvatarRenderer } from "../components/live/AvatarRenderer";
import { LiveBackground } from "../components/live/LiveBackground";
import { SubtitleOverlay, type SubtitleItem } from "../components/live/SubtitleOverlay";
import { MicToggle } from "../components/live/MicToggle";
import { LevelMeter } from "../components/live/LevelMeter";
import { AudioWave } from "../components/live/AudioWave";
import { useLiveVoice } from "../components/live/useLiveVoice";
import { useLiveEmotion } from "../hooks/useLiveEmotion";
import { useSpeechStore } from "../stores/speech";
import { useSkinStore } from "../stores/skin";
import { resolveLiveScene } from "../lib/skin";
import { useSessions } from "../stores/sessions";
import { useCardsStore } from "../stores/cards";
import { useLiveUi } from "../stores/live-ui";
import type { LiveSessionConfig } from "./LiveLobby";

interface LiveChatProps {
  config: LiveSessionConfig;
  onExit: () => void;
}

export function LiveChat({ config, onExit }: LiveChatProps) {
  const { t } = useTranslation();
  const character = useCardsStore((s) =>
    config.characterId ? s.characters.find((c) => c.id === config.characterId) : undefined
  );
  const voice = useLiveVoice({
    characterId: config.characterId,
    voiceOverride: String(character?.tts_voice ?? ""),
    instructionsOverride: String(character?.tts_instructions ?? ""),
  });
  const emotion = useLiveEmotion(config.characterId);
  const activeSkin = useSkinStore((s) => s.skins.find((x) => x.id === s.activeId));
  const scene = resolveLiveScene(activeSkin?.background);
  const liveHistory = useSessions((s) => s.liveHistory);
  const subtitlesVisible = useLiveUi((s) => s.subtitlesVisible);
  const toggleSubtitles = useLiveUi((s) => s.toggleSubtitles);
  const rendererRef = useRef<AvatarRenderer | null>(null);

  // Drive mouth animation while the reply is spoken; relax on stop.
  useEffect(() => {
    const renderer = rendererRef.current;
    if (!renderer) return;
    const unsubscribe = useSpeechStore.getState().subscribePlaying((playing) => {
      if (playing) renderer.speak();
      else renderer.stopSpeaking();
    });
    return unsubscribe;
  }, []);

  // Feed the emotion layer into the avatar whenever it changes.
  useEffect(() => {
    rendererRef.current?.setEmotion(emotion);
  }, [emotion]);

  const modelUrl =
    config.model === null ? null : `/api/models/${encodeURIComponent(config.model)}`;

  const assistantItems: SubtitleItem[] = useMemo(() => {
    const entries = Object.entries(liveHistory);
    if (entries.length === 0) return [];
    const [, msgs] = entries[entries.length - 1];
    return msgs
      .filter((m) => m.role === "assistant")
      .map((m) => ({
        id: m.id,
        role: "assistant" as const,
        text: m.content,
        streaming: m.streaming,
      }));
  }, [liveHistory]);

  const items: SubtitleItem[] = [...voice.userLines, ...assistantItems];

  return (
    <div className="relative flex h-full flex-col overflow-hidden">
      <LiveBackground scene={scene} />
      <div className="relative min-h-0 flex-1">
        <AudioWave className="absolute left-1/2 top-4 -translate-x-1/2" />
        <AvatarCanvas model={modelUrl} rendererRef={rendererRef} />
      </div>

      {voice.asrNotConfigured && (
        <div className="relative border-t border-border bg-bg/40 px-4 py-2 text-xs text-text-muted">
          {t("live.asrNotConfigured")}
        </div>
      )}
      {voice.vadError && (
        <div className="relative border-t border-border bg-bg/40 px-4 py-2 text-xs text-text-muted">
          {t("live.micUnavailable", {
            reason: voice.permissionDenied
              ? t("live.micPermissionDenied")
              : voice.vadError,
          })}{" "}
          <button className="underline" onClick={voice.retryVad}>
            {t("live.retry")}
          </button>
        </div>
      )}

      <SubtitleOverlay
        items={items}
        visible={subtitlesVisible}
        onToggle={toggleSubtitles}
      />

      <div className="relative flex items-center justify-between border-t border-border bg-bg/40 px-4 py-2 backdrop-blur">
        <div className="flex items-center gap-2 px-2">
          <span
            className={
              voice.userSpeaking
                ? "inline-block h-2 w-2 rounded-full bg-accent"
                : "inline-block h-2 w-2 rounded-full bg-border"
            }
          />
          <LevelMeter subscribe={voice.subscribeLevel} />
          <p className="text-[11px] text-text-faint">
            {voice.busy
              ? t("live.status.thinking")
              : voice.userSpeaking
                ? t("live.status.speaking")
                : voice.listening
                  ? t("live.status.listening")
                  : t("live.status.idle")}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <MicToggle
            muted={voice.muted}
            listening={voice.listening}
            userSpeaking={voice.userSpeaking}
            onToggle={voice.toggleMute}
          />
          <button
            aria-label={t("live.exit")}
            className="rounded-full border border-border px-3 py-1 text-sm"
            onClick={onExit}
          >
            {t("live.exit")}
          </button>
        </div>
      </div>
    </div>
  );
}
