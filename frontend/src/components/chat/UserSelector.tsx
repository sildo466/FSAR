// SPDX-License-Identifier: MIT
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { AnimatePresence, motion } from "framer-motion";
import { Check, ChevronDown } from "lucide-react";
import { useCardsStore } from "../../stores/cards";

export function UserSelector() {
  const { t } = useTranslation();
  const userCards = useCardsStore((s) => s.userCards);
  const setDefault = useCardsStore((s) => s.setDefault);
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  if (userCards.length === 0) return null

  const current = userCards.find((u) => u.is_default === 1) ?? userCards[0]

  const pick = (id: number) => {
    setDefault("user", id)
    setOpen(false)
  }

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        aria-label="user"
        aria-expanded={open}
        data-testid="user-selector"
        onClick={() => setOpen((v) => !v)}
        className="glass flex h-9 max-w-[150px] items-center gap-1.5 rounded-full px-3 font-mono text-[11px] text-text transition hover:bg-glass-strong"
      >
        <span className="truncate">
          {current.name}{current.is_default === 1 ? " (default)" : ""}
        </span>
        <ChevronDown size={11} className={`shrink-0 transition-transform duration-200 ${open ? "rotate-180" : ""}`} />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            role="listbox"
            initial={{ opacity: 0, y: -6, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -6, scale: 0.97 }}
            transition={{ duration: 0.16, ease: "easeOut" }}
            className="glass-strong absolute right-0 top-11 z-50 max-h-72 w-56 overflow-auto rounded-2xl p-1 shadow-[0_16px_44px_var(--glow-faint)]"
          >
            {userCards.map((u) => (
              <button
                type="button"
                key={u.id}
                role="option"
                aria-selected={u.id === current.id}
                title={t("cards.rightClickHint")}
                onClick={() => pick(u.id)}
                onContextMenu={(e) => {
                  e.preventDefault();
                  setDefault("user", u.id);
                }}
                className={`flex w-full items-center justify-between gap-2 rounded-xl px-3 py-2 text-left text-[12px] transition hover:bg-glass ${
                  u.id === current.id ? "bg-glass text-text" : "text-text-muted hover:text-text"
                }`}
              >
                <span className="truncate">
                  {u.name}{u.is_default === 1 ? " (default)" : ""}
                </span>
                {u.id === current.id && <Check size={12} className="shrink-0" />}
              </button>
            ))}
            <div className="border-t border-border/50 px-3 py-1.5 text-[10px] text-text-muted/70">
              {t("cards.rightClickHint")}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
