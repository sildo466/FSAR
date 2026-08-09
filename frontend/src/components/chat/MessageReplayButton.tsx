// SPDX-License-Identifier: MIT
import { RotateCcw, Volume2 } from "lucide-react";
import { useSpeechStore } from "../../stores/speech";

interface Props { messageId: string; text: string; voiceOverride?: string; instructionsOverride?: string; onRegenerate?: () => void }

export function MessageReplayButton({ messageId, text, voiceOverride, instructionsOverride, onRegenerate }: Props) {
  const configured = useSpeechStore((state) => state.isTtsConfigured);
  const playing = useSpeechStore((state) => state.playingMessageId === messageId);
  const progress = useSpeechStore((state) => state.playbackProgress);
  const play = useSpeechStore((state) => state.playText);
  if (!configured && !onRegenerate) return null;
  return <div className="relative flex items-center gap-1 overflow-hidden rounded-full border border-border bg-bg/30 p-0.5"><div className="absolute inset-y-0 left-0 bg-text/[0.08]" style={{ width: `${playing ? progress * 100 : 0}%` }} />{configured && <button type="button" aria-label={playing ? "Playing message" : "Play message"} disabled={playing} onClick={() => void play(text, messageId, { voiceOverride, instructionsOverride })} className={`relative rounded-full p-1.5 ${playing ? "animate-pulse text-text" : "text-text-muted hover:text-text"}`}><Volume2 size={12} /></button>}{onRegenerate && <button type="button" aria-label="Regenerate response" onClick={onRegenerate} className="relative rounded-full p-1.5 text-text-muted hover:text-text"><RotateCcw size={11} /></button>}</div>;
}
