// SPDX-License-Identifier: MIT
import { useTokenMeter } from "../../stores/token-meter";

/** Compact live context gauge for the chat top bar: used/window tokens for
 * the current conversation, the GUI twin of the TUI status-bar readout. */
export function TokenMeter() {
  const used = useTokenMeter((s) => s.used);
  const windowTokens = useTokenMeter((s) => s.window);
  if (!windowTokens) return null;
  return (
    <span
      className="hidden items-center gap-1 rounded-full border border-border/60 bg-[var(--chip-bg)] px-2.5 py-1 font-mono text-[10px] leading-none text-text-muted md:flex"
      title={`context: ${used.toLocaleString()} / ${windowTokens.toLocaleString()} tokens`}
    >
      <span className="text-text">{used.toLocaleString()}</span>
      <span className="opacity-60">/ {windowTokens.toLocaleString()}</span>
      <span className="opacity-60">tk</span>
    </span>
  );
}