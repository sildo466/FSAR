// SPDX-License-Identifier: MIT
import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import type { ElectionCandidate } from "../../lib/ws-client";
import { ThinkingDot } from "../chat/ThinkingDot";

interface Props {
  candidates: ElectionCandidate[];
  running: boolean;
}

export function ElectionStrip({ candidates, running }: Props) {
  const { t } = useTranslation();
  if (candidates.length === 0 && !running) return null;

  return (
    <motion.div
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: "auto" }}
      role="region"
      aria-label={t("group.electionAria")}
      className="sticky top-0 z-20 border-b border-border bg-[color:var(--glass)]/35 px-4 py-2 backdrop-blur sm:px-8"
    >
      <div className="mx-auto flex max-w-[900px] items-center gap-2 overflow-x-auto">
        <div className="mr-1 flex shrink-0 items-center gap-2 font-mono text-[10px] uppercase text-text-faint">
          {running && (
            <span className="relative flex h-2 w-2">
              <span className="absolute inset-0 animate-ping rounded-full bg-warning/50" />
              <span className="relative h-2 w-2 rounded-full bg-warning" />
            </span>
          )}
          {t("group.election")}
        </div>
        {candidates.length === 0 && <ThinkingDot />}
        {candidates.map((c) => (
          <div
            key={c.character_id}
            className="flex shrink-0 items-center gap-2 border-l border-border px-3"
          >
            <span className="max-w-32 truncate text-[11px] font-medium text-text">
              {c.character_name}
            </span>
            <span className="font-mono text-[10px] text-text-muted">
              {c.eagerness}/10
            </span>
            <span className="max-w-40 truncate text-[10px] text-text-faint">
              {c.reason}
            </span>
          </div>
        ))}
      </div>
    </motion.div>
  );
}
