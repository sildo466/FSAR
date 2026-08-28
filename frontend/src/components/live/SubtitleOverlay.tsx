// SPDX-License-Identifier: MIT
import { useEffect, useRef } from "react";
import { clsx } from "clsx";

export interface SubtitleItem {
  id: string;
  role: "user" | "assistant";
  text: string;
  streaming?: boolean;
}

export function SubtitleOverlay({ items }: { items: SubtitleItem[] }) {
  const bottomRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    // jsdom lacks scrollIntoView; guard so tests don't crash on mount.
    if (typeof bottomRef.current?.scrollIntoView === "function") {
      bottomRef.current.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [items.length]);

  if (items.length === 0) {
    return (
      <div className="min-w-0 flex-1 px-2">
        <p className="text-xs text-text-faint">Live subtitles</p>
      </div>
    );
  }

  return (
    <div className="min-w-0 flex-1 space-y-1 overflow-y-auto px-2">
      {items.map((item) => (
        <div
          key={item.id}
          className={clsx(
            "max-w-[85%] rounded-lg px-2 py-1 text-sm",
            item.role === "user"
              ? "ml-auto bg-accent/20 text-text"
              : "mr-auto bg-bg/40 text-text-muted"
          )}
        >
          {item.text}
          {item.streaming && <span className="animate-pulse">▍</span>}
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
