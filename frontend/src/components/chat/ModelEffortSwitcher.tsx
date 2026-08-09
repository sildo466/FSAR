// SPDX-License-Identifier: MIT
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { AnimatePresence, motion } from "framer-motion";
import { Brain, Check, ChevronDown } from "lucide-react";
import { cn } from "../../lib/cn";
import { useWS } from "../../stores/ws";

export type ModelEffort = "off" | "low" | "medium" | "high" | "xhigh" | "max";

const LEVELS: Array<{
  value: ModelEffort;
  labelKey: string;
  descKey: string;
}> = [
  { value: "off", labelKey: "effort.off", descKey: "effort.offDesc" },
  { value: "low", labelKey: "effort.low", descKey: "effort.lowDesc" },
  { value: "medium", labelKey: "effort.medium", descKey: "effort.mediumDesc" },
  { value: "high", labelKey: "effort.high", descKey: "effort.highDesc" },
  { value: "xhigh", labelKey: "effort.xhigh", descKey: "effort.xhighDesc" },
  { value: "max", labelKey: "effort.max", descKey: "effort.maxDesc" },
];

function readEffort(config: Record<string, unknown> | null): ModelEffort {
  const llm = (config?.llm ?? {}) as Record<string, unknown>;
  const value = String(llm.model_thinking_effort ?? "off").toLowerCase();
  return LEVELS.some((level) => level.value === value) ? value as ModelEffort : "off";
}

export function ModelEffortSwitcher() {
  const { t } = useTranslation();
  const config = useWS((state) => state.config);
  const send = useWS((state) => state.send);
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const current = readEffort(config);
  const active = LEVELS.find((level) => level.value === current) ?? LEVELS[0];

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

  const select = (value: ModelEffort) => {
    if (value !== current) {
      send({
        type: "settings.patch",
        patch: { "llm.model_thinking_effort": value },
      });
    }
    setOpen(false);
  };

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        title={t("effort.title")}
        aria-label={t("effort.aria", { label: t(active.labelKey) })}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="glass flex h-8 items-center gap-2 rounded-full px-3 text-[11px] transition hover:bg-glass-strong"
      >
        <Brain size={13} strokeWidth={1.7} />
        <span className="font-mono">{t("effort.label")} · {t(active.labelKey)}</span>
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
          {LEVELS.map((level) => (
            <button
              type="button"
              key={level.value}
              onClick={() => select(level.value)}
              className={cn(
                "flex w-full items-start gap-3 rounded-xl px-3 py-2 text-left hover:bg-glass",
                level.value === current && "bg-glass",
              )}
            >
              <div className="flex min-w-0 flex-1 flex-col">
                <span className="font-mono text-[11px] text-text">{t(level.labelKey)}</span>
                <span className="mt-0.5 text-[10px] leading-tight text-text-muted">
                  {t(level.descKey)}
                </span>
              </div>
              {level.value === current && (
                <Check size={12} strokeWidth={2} className="mt-1 shrink-0" />
              )}
            </button>
          ))}
        </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
