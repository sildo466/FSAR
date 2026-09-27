// SPDX-License-Identifier: MIT
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useGroup } from "../../stores/group";

interface Props {
  onClose: () => void;
}

export function LanPanel({ onClose }: Props) {
  const { t } = useTranslation();
  const lan = useGroup((s) => s.lan);
  const send = useGroup((s) => s.send);
  const refreshStatus = useGroup((s) => s.refreshLanStatus);
  const refreshBlocklist = useGroup((s) => s.refreshLanBlocklist);
  const refreshAudit = useGroup((s) => s.refreshAuthAudit);
  const blockIp = useGroup((s) => s.blockIp);
  const unblockIp = useGroup((s) => s.unblockIp);
  const rebindIp = useGroup((s) => s.rebindIp);
  const [blockTarget, setBlockTarget] = useState("");

  useEffect(() => {
    refreshStatus();
    refreshBlocklist();
    refreshAudit(50);
  }, [refreshStatus, refreshBlocklist, refreshAudit]);

  const status = lan.status;

  return (
    <aside className="glass flex h-full w-96 shrink-0 flex-col gap-4 overflow-y-auto rounded-2xl p-4">
      <div className="flex items-center justify-between">
        <span className="font-display text-xs tracking-[0.08em] text-text-muted">
          {t("lan.title")}
        </span>
        <button
          data-testid="close-lan-panel"
          onClick={onClose}
          className="rounded-full p-1 text-text-muted transition hover:text-text"
        >
          ×
        </button>
      </div>

      <label className="flex items-start gap-2 rounded-xl border border-border bg-surface px-3 py-2">
        <input
          type="checkbox"
          data-testid="lan-master-switch"
          checked={Boolean(status?.listening)}
          onChange={(e) =>
            send({
              type: "settings.patch",
              patch: { "lan.enabled": e.target.checked },
            })
          }
          className="mt-0.5"
        />
        <span>
          <span className="block text-xs text-text">{t("lan.enabled")}</span>
          <span className="block text-[11px] text-text-faint">
            {t("lan.enabledHint")}
          </span>
        </span>
      </label>

      <p data-testid="lan-status" className="text-[11px] text-text-muted">
        {status?.listening ? t("lan.statusOpen") : t("lan.statusClosed")}
        {status ? ` · ${t("lan.roomCount", { count: status.lan_rooms })}` : ""}
      </p>

      {status?.error && (
        <p data-testid="lan-error" className="text-[11px] text-danger">
          {status.error}
        </p>
      )}

      {status?.addresses.map((url, index) => (
        <span
          key={url}
          data-testid={`lan-url-${index}`}
          className="font-mono text-[11px] text-text"
        >
          {url}
        </span>
      ))}

      {status?.fingerprint && (
        <span
          data-testid="lan-fingerprint"
          className="break-all font-mono text-[10px] text-text-faint"
        >
          {status.fingerprint}
        </span>
      )}

      {status && (
        <div className="flex flex-col gap-2">
          <span className="text-[11px] text-text-muted">{t("lan.handoff")}</span>
          <input
            readOnly
            data-testid="lan-handoff"
            value={status.agent_md_hint}
            className="w-full rounded-xl border border-border bg-surface px-3 py-2 font-mono text-[10px] text-text outline-none"
          />
          <p className="text-[10px] text-text-faint">{t("lan.handoffHint")}</p>
        </div>
      )}

      <div className="flex flex-col gap-2 border-t border-border pt-3">
        <span className="text-[11px] text-text-muted">{t("lan.blocklist")}</span>
        <div className="flex gap-2">
          <input
            data-testid="block-ip-input"
            value={blockTarget}
            onChange={(e) => setBlockTarget(e.target.value)}
            placeholder="192.168.1.20"
            className="min-w-0 flex-1 rounded-xl border border-border bg-surface px-3 py-2 text-xs text-text outline-none"
          />
          <button
            data-testid="block-ip-submit"
            onClick={() => {
              const ip = blockTarget.trim();
              if (!ip) return;
              blockIp(ip, "");
              setBlockTarget("");
            }}
            className="rounded-full border border-border px-3 py-1 text-[11px] text-text-muted transition hover:text-danger"
          >
            {t("lan.block")}
          </button>
        </div>
        {lan.blocklist.map((entry) => (
          <div
            key={entry.ip}
            data-testid={`blocked-ip-${entry.ip}`}
            className="flex items-center justify-between gap-2"
          >
            <span className="truncate font-mono text-[11px] text-text">
              {entry.ip}
            </span>
            <button
              data-testid={`unblock-${entry.ip}`}
              onClick={() => unblockIp(entry.ip)}
              className="shrink-0 text-[10px] text-text-muted transition hover:text-text"
            >
              {t("lan.unblock")}
            </button>
          </div>
        ))}
      </div>

      <div className="flex flex-col gap-2 border-t border-border pt-3">
        <span className="text-[11px] text-text-muted">
          {t("lan.recentDenials")}
        </span>
        {lan.audit.map((event) => (
          <div
            key={event.seq}
            data-testid={`audit-row-${event.seq}`}
            className="flex items-center justify-between gap-2"
          >
            <span className="truncate text-[10px] text-text-muted">
              {event.reason}
              {event.source_ip ? ` · ${event.source_ip}` : ""}
              {event.member_ref ? ` · ${event.member_ref}` : ""}
            </span>
            {event.reason === "ip_mismatch" &&
              event.token_id !== null &&
              event.source_ip && (
                <button
                  data-testid={`rebind-${event.seq}`}
                  onClick={() => rebindIp(event.token_id as number, event.source_ip as string)}
                  className="shrink-0 text-[10px] text-text-muted transition hover:text-text"
                >
                  {t("lan.rebind")}
                </button>
              )}
          </div>
        ))}
      </div>
    </aside>
  );
}
