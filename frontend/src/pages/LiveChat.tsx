// SPDX-License-Identifier: MIT
import { useState } from "react";
import { Mic } from "lucide-react";
import { AvatarCanvas } from "../components/live/AvatarCanvas";
import { LiveBackground } from "../components/live/LiveBackground";
import { useSkinStore } from "../stores/skin";
import { resolveLiveScene } from "../lib/skin";
import type { LiveSessionConfig } from "./LiveLobby";

interface LiveChatProps {
  config: LiveSessionConfig;
  onExit: () => void;
}

export function LiveChat({ config, onExit }: LiveChatProps) {
  // Stage 1: media/mic always off; enabled in Stage 2 (VAD).
  const [muted] = useState(true);
  const activeSkin = useSkinStore((s) => s.skins.find((x) => x.id === s.activeId));
  const scene = resolveLiveScene(activeSkin?.background);

  const modelUrl =
    config.model === null ? null : `/api/models/${encodeURIComponent(config.model)}`;

  return (
    <div className="relative flex h-full flex-col overflow-hidden">
      <LiveBackground scene={scene} />
      <div className="relative min-h-0 flex-1">
        <AvatarCanvas model={modelUrl} />
      </div>

      <div className="relative flex items-center justify-between border-t border-border bg-bg/40 px-4 py-2 backdrop-blur">
        <div className="min-w-0 flex-1 px-2">
          <p className="text-xs text-text-faint">Live subtitles</p>
          {/* Stage 2: bubble stream fills this region */}
        </div>
        <div className="flex items-center gap-2">
          <button
            aria-label="Mic"
            className="rounded-full border border-border p-2 text-text-muted disabled:opacity-40"
            disabled={muted}
          >
            <Mic size={16} strokeWidth={1.5} />
          </button>
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
