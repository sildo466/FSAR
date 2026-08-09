// SPDX-License-Identifier: MIT
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { AnimatePresence, motion } from "framer-motion";
import { Check, ChevronDown, Gauge } from "lucide-react";
import { useWS } from "../../stores/ws";
import { cn } from "../../lib/cn";

export type AgentTier = "low" | "medium" | "high" | "xhigh" | "max" | "ultra";

const TIERS: Array<{
  value: AgentTier;
  labelKey: string;
  descKey: string;
  level: number;
  warning?: boolean;
}> = [
  { value: "low", labelKey: "tier.low", descKey: "tier.lowDesc", level: 1 },
  { value: "medium", labelKey: "tier.medium", descKey: "tier.mediumDesc", level: 2 },
  { value: "high", labelKey: "tier.high", descKey: "tier.highDesc", level: 3 },
  { value: "xhigh", labelKey: "tier.xhigh", descKey: "tier.xhighDesc", level: 4 },
  { value: "max", labelKey: "tier.max", descKey: "tier.maxDesc", level: 5 },
  { value: "ultra", labelKey: "tier.ultra", descKey: "tier.ultraDesc", level: 6, warning: true },
];

function readTier(config: Record<string, unknown> | null): AgentTier {
  const agent = (config?.agent ?? {}) as Record<string, unknown>;
  const value = String(agent.tier ?? "medium").toLowerCase();
  return TIERS.some((tier) => tier.value === value) ? value as AgentTier : "medium";
}

export function TierSwitcher() {
  const { t } = useTranslation();
  const config = useWS((state) => state.config);
  const send = useWS((state) => state.send);
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const current = readTier(config);
  const active = TIERS.find((tier) => tier.value === current) ?? TIERS[1];

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const select = (tier: AgentTier) => {
    if (tier !== current) {
      send({ type: "settings.patch", patch: { "agent.tier": tier } });
    }
    setOpen(false);
  };

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        title={t("tier.title")}
        aria-label={t("tier.aria", { label: t(active.labelKey) })}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="glass flex h-8 items-center gap-2 rounded-full px-3 text-[11px] transition hover:bg-glass-strong"
      >
        <Gauge size={13} strokeWidth={1.7} />
        <span className="font-mono">{t(active.labelKey)}</span>
        <span className="hidden items-end gap-[2px] sm:flex" aria-hidden="true">
          {TIERS.map((tier) => (
            <i
              key={tier.value}
              className={cn(
                "block w-[2px] rounded-full bg-text-faint",
                tier.level <= active.level && "bg-text",
              )}
              style={{ height: `${3 + tier.level}px` }}
            />
          ))}
        </span>
        <ChevronDown size={11} strokeWidth={1.7} className={`transition-transform duration-200 ${open ? "rotate-180" : ""}`} />
      </button>
      <AnimatePresence>
        {open && (
        <motion.div
          initial={{ opacity: 0, y: -6, scale: 0.97 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: -6, scale: 0.97 }}
          transition={{ duration: 0.16, ease: "easeOut" }}
          className="glass-strong absolute right-0 top-10 z-50 w-72 overflow-hidden rounded-2xl p-1 shadow-[0_16px_44px_var(--glow-faint)]"
        >
          {TIERS.map((tier) => (
            <button
              type="button"
              key={tier.value}
              onClick={() => select(tier.value)}
              className={cn(
                "flex w-full items-start gap-3 rounded-xl px-3 py-2 text-left text-[11px] text-text-muted hover:bg-glass hover:text-text",
                tier.value === current && "bg-glass text-text",
              )}
            >
              <span className="mt-1 flex w-7 items-end gap-[2px]" aria-hidden="true">
                {TIERS.map((bar) => (
                  <i
                    key={bar.value}
                    className={cn(
                      "block w-[2px] rounded-full bg-text-faint/40",
                      bar.level <= tier.level && "bg-text-muted",
                    )}
                    style={{ height: `${3 + bar.level}px` }}
                  />
                ))}
              </span>
              <div className="flex min-w-0 flex-1 flex-col">
                <span className="font-mono text-text">{t(tier.labelKey)}</span>
                <span
                  className={cn(
                    "mt-0.5 text-[10px] leading-tight",
                    tier.warning ? "text-red-400" : "text-text-muted",
                  )}
                >
                  {tier.warning ? "⚠ " : ""}{t(tier.descKey)}
                </span>
              </div>
              {tier.value === current && <Check size={12} strokeWidth={2} className="mt-1 shrink-0" />}
            </button>
          ))}
        </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
