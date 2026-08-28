// SPDX-License-Identifier: MIT
import { useEffect, useRef } from "react";

const BARS = [0, 1, 2, 3, 4];

interface LevelMeterProps {
  subscribe: (cb: (level: number) => void) => () => void;
}

export function LevelMeter({ subscribe }: LevelMeterProps) {
  const barRefs = useRef<(HTMLSpanElement | null)[]>([]);

  useEffect(() => {
    return subscribe((level) => {
      barRefs.current.forEach((bar, i) => {
        if (!bar) return;
        const on = level >= (i + 1) / 5;
        bar.style.backgroundColor = on ? "var(--accent)" : "var(--border)";
      });
    });
  }, [subscribe]);

  return (
    <div className="flex h-3 items-end gap-[2px]" data-testid="live-level" aria-label="mic level">
      {BARS.map((bar) => (
        <span
          key={bar}
          ref={(el) => {
            barRefs.current[bar] = el;
          }}
          className="w-[3px] rounded-sm"
          style={{ height: `${(bar + 1) * 3}px`, backgroundColor: "var(--border)" }}
        />
      ))}
    </div>
  );
}
