// SPDX-License-Identifier: MIT
import { AnimatePresence, motion } from "framer-motion";
import { Captions, CaptionsOff, X } from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";

export interface SubtitleItem {
  id: string;
  role: "user" | "assistant";
  text: string;
  streaming?: boolean;
}

interface SubtitleOverlayProps {
  items: SubtitleItem[];
  visible: boolean;
  onToggle: () => void;
}

export function SubtitleOverlay({ items, visible, onToggle }: SubtitleOverlayProps) {
  const { t } = useTranslation();

  return (
    <div className="pointer-events-none absolute bottom-4 right-4 top-1/2 z-20 flex w-64 -translate-y-1/2 flex-col items-end">
      <button
        aria-label={visible ? t("live.subtitles.hide") : t("live.subtitles.show")}
        className="pointer-events-auto mb-2 flex items-center gap-1 rounded-full border border-border/60 bg-bg/30 px-2 py-1 text-[11px] text-text-faint backdrop-blur-md transition-colors hover:text-text"
        onClick={onToggle}
      >
        {visible ? <Captions size={13} strokeWidth={1.5} /> : <CaptionsOff size={13} strokeWidth={1.5} />}
        <span>{visible ? t("live.subtitles.hide") : t("live.subtitles.show")}</span>
      </button>

      <AnimatePresence>
        {visible && (
          <motion.div
            initial={{ opacity: 0, x: 16 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 16 }}
            transition={{ duration: 0.25, ease: "easeOut" }}
            className="pointer-events-auto flex max-h-[60vh] w-full flex-col gap-2 overflow-hidden rounded-2xl border border-border/40 bg-bg/30 p-3 backdrop-blur-md"
          >
            <div className="flex flex-1 flex-col justify-end gap-2 overflow-y-auto">
              {items.length === 0 && (
                <p className="pb-2 text-center text-[11px] text-text-faint">
                  {t("live.subtitles")}
                </p>
              )}
              {items.map((item) => (
                <motion.div
                  key={item.id}
                  initial={{ opacity: 0, y: 8, scale: 0.97 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  transition={{ duration: 0.2, ease: "easeOut" }}
                  className={clsx(
                    "max-w-[92%] rounded-xl px-3 py-1.5 text-sm leading-snug",
                    item.role === "user"
                      ? "self-end bg-accent/25 text-text"
                      : "self-start bg-bg/50 text-text-muted"
                  )}
                >
                  {item.text}
                  {item.streaming && (
                    <span className="inline-block animate-pulse">▍</span>
                  )}
                </motion.div>
              ))}
            </div>
            <button
              aria-label={t("live.subtitles.hide")}
              className="absolute right-2 top-2 rounded-full p-1 text-text-faint transition-colors hover:text-text"
              onClick={onToggle}
            >
              <X size={14} strokeWidth={1.5} />
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
