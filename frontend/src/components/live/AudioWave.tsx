// SPDX-License-Identifier: MIT
import { useEffect, useRef } from "react";
import { useSpeechStore } from "../../stores/speech";

const BARS = 24;
const BAR_HEIGHT = 28; // px max

interface AudioWaveProps {
  className?: string;
}

export function AudioWave({ className }: AudioWaveProps) {
  const barRefs = useRef<(HTMLSpanElement | null)[]>([]);

  useEffect(() => {
    return useSpeechStore.getState().subscribeAudioLevel((level) => {
      barRefs.current.forEach((bar, i) => {
        if (!bar) return;
        // Alternate bar heights for a wave feel; scale by level.
        const base = 0.35 + 0.65 * Math.abs(Math.sin(i * 0.6));
        const height = Math.max(2, Math.round(BAR_HEIGHT * base * (0.15 + level)));
        bar.style.height = `${height}px`;
        bar.style.opacity = String(0.35 + 0.65 * level);
      });
    });
  }, []);

  return (
    <div
      className={`pointer-events-none flex items-end justify-center gap-[3px] ${className ?? ""}`}
      data-testid="live-wave"
      aria-hidden="true"
    >
      {Array.from({ length: BARS }, (_, i) => (
        <span
          key={i}
          ref={(el) => {
            barRefs.current[i] = el;
          }}
          className="w-[3px] rounded-full bg-accent"
          style={{ height: "3px", opacity: 0.35 }}
        />
      ))}
    </div>
  );
}
