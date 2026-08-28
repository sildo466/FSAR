// SPDX-License-Identifier: MIT
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { AvatarCanvas } from "../components/live/AvatarCanvas";
import { LiveBackground } from "../components/live/LiveBackground";
import { SubtitleOverlay, type SubtitleItem } from "../components/live/SubtitleOverlay";
import { MicToggle } from "../components/live/MicToggle";
import { useLiveVoice } from "../components/live/useLiveVoice";
import { useSkinStore } from "../stores/skin";
import { resolveLiveScene } from "../lib/skin";
import { useSessions } from "../stores/sessions";
import { useCardsStore } from "../stores/cards";
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
  const activeSkin = useSkinStore((s) => s.skins.find((x) => x.id === s.activeId));
  const scene = resolveLiveScene(activeSkin?.background);
  const liveHistory = useSessions((s) => s.liveHistory);

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
        <AvatarCanvas model={modelUrl} />
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

      <div className="relative flex items-center justify-between border-t border-border bg-bg/40 px-4 py-2 backdrop-blur">
        <SubtitleOverlay items={items} />
        <div className="flex items-center gap-2">
          <MicToggle
            muted={voice.muted}
            listening={voice.listening}
            userSpeaking={voice.userSpeaking}
            onToggle={voice.toggleMute}
          />
          <button
            aria-label="Exit"
            className="rounded-full border border-border px-3 py-1 text-sm"
            onClick={onExit}
          >
            Exit
          </button>
        </div>
      </div>
    </div>
  );
}
