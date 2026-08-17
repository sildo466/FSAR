// SPDX-License-Identifier: MIT
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, Clock3, FolderLock } from "lucide-react";
import { motion } from "framer-motion";
import type { SandboxEscapeRequest } from "../../lib/ws-client";

type Decision = "deny" | "allow_once" | "allow_session" | "allow_always";

export function EscapeModal({ request, onDecision }: { request: SandboxEscapeRequest; onDecision: (decision: Decision) => void }) {
  const { t } = useTranslation();
  const [seconds, setSeconds] = useState(60);

  useEffect(() => {
    setSeconds(60);
    const timer = window.setInterval(() => setSeconds((value) => {
      if (value <= 1) {
        window.clearInterval(timer);
        onDecision("deny");
        return 0;
      }
      return value - 1;
    }), 1000);
    return () => window.clearInterval(timer);
  }, [request.request_id, onDecision]);

  return (
    <div className="fixed inset-0 z-[100] grid place-items-center bg-black/65 px-5 backdrop-blur-md" role="dialog" aria-modal="true" aria-labelledby="sandbox-title">
      <motion.section initial={{ opacity: 0, y: 18, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} className="glass-strong w-full max-w-[620px] overflow-hidden rounded-[30px] shadow-[0_28px_100px_rgba(0,0,0,.45)]">
        <div className="flex items-start justify-between gap-4 border-b border-border px-6 py-5">
          <div className="flex gap-3">
            <div className="grid h-10 w-10 shrink-0 place-items-center rounded-2xl bg-warning/15 text-warning"><AlertTriangle size={20} /></div>
            <div>
              <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-warning">{t("escapeModal.tagline")}</p>
              <h2 id="sandbox-title" className="mt-1 font-display text-2xl italic">{t("escapeModal.title")}</h2>
            </div>
          </div>
          <div className="flex items-center gap-1.5 rounded-full border border-[var(--chip-border)] px-3 py-1.5 font-mono text-[11px] text-text-muted"><Clock3 size={12} /> {seconds}s</div>
        </div>
        <div className="space-y-5 px-6 py-5">
          <div className="grid grid-cols-[110px_1fr] gap-x-4 gap-y-2 text-[12px]">
            <span className="font-mono uppercase tracking-wider text-text-muted">{t("escapeModal.tool")}</span><span className="font-mono">{request.tool} · {request.operation}</span>
            <span className="font-mono uppercase tracking-wider text-text-muted">{t("escapeModal.reason")}</span><span>{request.reason}</span>
            <span className="font-mono uppercase tracking-wider text-text-muted">{t("escapeModal.workspace")}</span><span className="truncate font-mono text-text-muted">{request.context.workspace_root}</span>
          </div>
          <div className="rounded-2xl border border-warning/30 bg-warning/5 p-4">
            <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-warning"><FolderLock size={14} /> {t("escapeModal.requestedTarget")}</div>
            <code className="break-all font-mono text-[12px] leading-relaxed">{request.target_path || t("escapeModal.blockedPath")}</code>
          </div>
          <p className="text-[12px] leading-relaxed text-text-muted">{t("escapeModal.warning")}</p>
        </div>
        <div className="grid grid-cols-2 gap-2 border-t border-border bg-bg/35 px-6 py-5 sm:grid-cols-4">
          <button onClick={() => onDecision("deny")} className="rounded-full border border-border px-3 py-2 text-[12px] font-medium hover:bg-surface">{t("escapeModal.deny")}</button>
          <button onClick={() => onDecision("allow_once")} className="rounded-full border border-border px-3 py-2 text-[12px] font-medium hover:bg-surface">{t("escapeModal.allowOnce")}</button>
          <button onClick={() => onDecision("allow_session")} className="rounded-full border border-border px-3 py-2 text-[12px] font-medium hover:bg-surface">{t("escapeModal.thisSession")}</button>
          <button onClick={() => onDecision("allow_always")} className="rounded-full bg-text px-3 py-2 text-[12px] font-medium text-bg shadow-[0_0_24px_var(--glow-soft)]">{t("escapeModal.alwaysAllow")}</button>
        </div>
      </motion.section>
    </div>
  );
}
