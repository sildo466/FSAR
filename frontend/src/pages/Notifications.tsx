// SPDX-License-Identifier: MIT
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, RotateCcw, ShieldOff, Trash2 } from "lucide-react";
import { cn } from "../lib/cn";
import type {
  ContentQuarantineInfo,
  ContentScanReport,
  ContentWhitelistInfo,
} from "../lib/ws-client";
import { useWS } from "../stores/ws";

type FeedFilter = "all" | "review" | "release" | "announcement";

export function Notifications() {
  const { t } = useTranslation();
  const send = useWS((s) => s.send);
  const client = useWS((s) => s.client);
  const notifications = useWS((s) => s.notifications);
  const [items, setItems] = useState<ContentQuarantineInfo[]>([]);
  const [whitelist, setWhitelist] = useState<ContentWhitelistInfo[]>([]);
  const [report, setReport] = useState<ContentScanReport>({});
  const [enabled, setEnabled] = useState(true);
  const [filterKind, setFilterKind] = useState<FeedFilter>("all");
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);

  useEffect(() => {
    send({ type: "content_guard.list" });
    send({ type: "notifications.list" });
    return client?.on((msg) => {
      if (msg.type === "content_guard.list_result") {
        setItems(msg.items);
        setWhitelist(msg.whitelist);
        setReport(msg.report);
        setEnabled(msg.enabled);
      }
    });
  }, [send, client]);

  const unavailable = report.unavailable ?? 0;
  const visible = notifications.filter(
    (n) => (filterKind === "all" || n.kind === filterKind) && (!unreadOnly || n.read === 0),
  );

  return (
    <div className="flex flex-col gap-6 p-6">
      <h1 className="font-display text-sm font-semibold">{t("notifications.title")}</h1>

      {!enabled && (
        <p data-testid="screening-disabled" className="text-[12px] text-text-muted">
          {t("notifications.disabled")}
        </p>
      )}

      {enabled && unavailable > 0 && (
        <div
          data-testid="screening-unavailable"
          className="flex items-start gap-2 rounded-lg border border-warning/40 bg-warning/10 px-3 py-2.5"
        >
          <AlertTriangle size={14} strokeWidth={1.5} className="mt-0.5 text-warning" />
          <div className="text-[11px] leading-relaxed text-text-muted">
            {t("notifications.unavailable", { n: unavailable })}
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {(["all", "review", "release", "announcement"] as const).map((kind) => (
          <button
            key={kind}
            data-testid={`filter-kind-${kind}`}
            onClick={() => setFilterKind(kind)}
            className={cn(
              "h-7 rounded-full border border-border px-3 text-[12px] hover:bg-surface",
              filterKind === kind && "bg-[var(--button-bg)] text-[var(--button-text)]",
            )}
          >
            {kind === "all" ? t("notifications.filter.all") : t(`notifications.kind.${kind}`)}
          </button>
        ))}
        <button
          data-testid="filter-unread"
          onClick={() => setUnreadOnly((v) => !v)}
          className={cn(
            "h-7 rounded-full border border-border px-3 text-[12px] hover:bg-surface",
            unreadOnly && "bg-[var(--button-bg)] text-[var(--button-text)]",
          )}
        >
          {t("notifications.filter.unread")}
        </button>
        <button
          data-testid="mark-all-read"
          onClick={() => send({ type: "notifications.mark_read" })}
          className="ml-auto h-7 rounded border border-border px-2 text-[12px] hover:bg-surface"
        >
          {t("notifications.markAllRead")}
        </button>
        <button
          data-testid="clear-all"
          onClick={() => setConfirmClear(true)}
          className="h-7 rounded border border-border px-2 text-[12px] hover:bg-surface"
        >
          {t("notifications.clearAll")}
        </button>
      </div>

      {confirmClear && (
        <div className="flex items-center gap-2 rounded border border-warning/40 bg-warning/10 px-3 py-2">
          <span className="text-[11px] text-text-muted">
            {t("notifications.clearAllConfirm")}
          </span>
          <button
            data-testid="clear-all-confirm"
            onClick={() => {
              send({ type: "notifications.clear" });
              setConfirmClear(false);
            }}
            className="h-7 rounded border border-border px-2 text-[12px]"
          >
            {t("common.delete")}
          </button>
          <button
            onClick={() => setConfirmClear(false)}
            className="h-7 rounded border border-border px-2 text-[12px]"
          >
            {t("common.cancel")}
          </button>
        </div>
      )}

      <ul className="border border-border rounded overflow-hidden">
        {visible.map((n) => {
          const payload = n.payload ?? {};
          const version = String(payload.tag ?? "").replace(/^v/, "");
          const heading =
            n.kind === "release"
              ? t(
                  payload.channel === "beta"
                    ? "notifications.betaTitle"
                    : "notifications.releaseTitle",
                  { version },
                )
              : n.title;
          return (
            <li
              key={n.id}
              data-testid={`notification-${n.id}`}
              className="flex flex-col gap-1.5 border-b border-border px-3 py-2.5 last:border-b-0"
            >
              <div className="flex items-center gap-2">
                <span className="font-mono text-[9px] uppercase tracking-[0.14em] text-text-muted">
                  {t(`notifications.kind.${n.kind}`)}
                </span>
                <span className="text-[13px]">{heading}</span>
                {n.read === 0 && <span className="h-1.5 w-1.5 rounded-full bg-red-500" />}
                <span className="ml-auto normal-case text-[10px] text-text-muted">
                  {n.created_at}
                </span>
              </div>
              {n.body && (
                <pre className="whitespace-pre-wrap break-words bg-surface px-2 py-1.5 font-mono text-[11px]">
                  {n.body}
                </pre>
              )}
            </li>
          );
        })}
      </ul>

      <h2 className="font-mono text-[9px] uppercase tracking-[0.14em] text-text-muted">
        {t("notifications.quarantineSection")}
      </h2>

      {items.length === 0 ? (
        <p className="text-[12px] text-text-muted">{t("notifications.empty")}</p>
      ) : (
        <ul className="border border-border rounded overflow-hidden">
          {items.map((row) => (
            <li
              key={row.id}
              className="flex flex-col gap-2 border-b border-border px-3 py-2.5 last:border-b-0"
            >
              <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.1em] text-text-muted">
                <span>{row.store}</span>
                <span>#{row.record_ref}</span>
                <span>{row.verdict_confidence.toFixed(2)}</span>
                <span>{row.screened_by}</span>
                <span className="ml-auto normal-case tracking-normal">{row.created_at}</span>
              </div>
              <pre className="whitespace-pre-wrap break-words bg-surface px-2 py-1.5 font-mono text-[11px]">
                {row.text}
              </pre>
              <div className="flex gap-2">
                <button
                  data-testid={`restore-${row.id}`}
                  onClick={() => send({ type: "content_guard.restore", id: row.id })}
                  className="flex items-center gap-1 h-7 px-2 border border-border rounded text-[12px] hover:bg-surface"
                >
                  <RotateCcw size={12} strokeWidth={1.5} /> {t("notifications.restore")}
                </button>
                <button
                  data-testid={`purge-${row.id}`}
                  onClick={() => send({ type: "content_guard.purge", id: row.id })}
                  className="flex items-center gap-1 h-7 px-2 border border-border rounded text-[12px] hover:bg-surface"
                >
                  <Trash2 size={12} strokeWidth={1.5} /> {t("notifications.purge")}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {whitelist.length > 0 && (
        <div className="flex flex-col gap-2">
          <h2 className="font-mono text-[9px] uppercase tracking-[0.14em] text-text-muted">
            {t("notifications.whitelist")}
          </h2>
          <ul className="border border-border rounded overflow-hidden">
            {whitelist.map((row) => (
              <li
                key={row.sha256}
                className="flex items-center justify-between gap-2 border-b border-border px-3 py-2 last:border-b-0"
              >
                <span className="truncate font-mono text-[10px] text-text-muted">
                  {row.sha256}
                </span>
                <button
                  data-testid={`unwhitelist-${row.sha256}`}
                  onClick={() =>
                    send({ type: "content_guard.unwhitelist", sha256: row.sha256 })
                  }
                  className="flex shrink-0 items-center gap-1 h-7 px-2 border border-border rounded text-[12px] hover:bg-surface"
                >
                  <ShieldOff size={12} strokeWidth={1.5} /> {t("notifications.unwhitelist")}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
