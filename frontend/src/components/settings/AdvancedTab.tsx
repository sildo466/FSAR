// SPDX-License-Identifier: MIT
import { useEffect, useState } from "react";
import { AlertTriangle, FileCode2 } from "lucide-react";
import { fetchWSToken, useWS } from "../../stores/ws";
import { useWizardState } from "../../stores/onboarding";
import { useTranslation } from "react-i18next";

interface RecentDecision {
  task_id: string;
  chosen_tool?: string;
  args_summary?: string;
  success?: boolean;
  latency_ms?: number;
  error_class?: string;
  created_at: string;
}

export function AdvancedTab() {
  const { t } = useTranslation();
  const send = useWS((s) => s.send);
  const client = useWS((s) => s.client);
  const [decisions, setDecisions] = useState<RecentDecision[]>([]);
  const [yaml, setYaml] = useState<string>(t("settings.advanced.loading"));

  useEffect(() => {
    send({ type: "insights.get" });
    fetch("/health", { method: "GET" });  // ensure backend is reachable
    fetchRawYaml().then(setYaml).catch(() => setYaml(t("settings.advanced.failedToLoad")));
  }, [send]);

  useEffect(() => {
    return client?.on((msg) => {
      if (msg.type === "insights.snapshot") {
        setDecisions((msg.recent_decisions as unknown as RecentDecision[]) ?? []);
      }
    });
  }, [client]);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <h2 className="font-display text-sm font-semibold">{t("settings.advanced.recentDecisions")}</h2>
        <p className="text-[11px] text-text-muted">
          {t("settings.advanced.recentDecisionsDesc")}
        </p>
        {decisions.length === 0 ? (
          <div className="border border-border rounded p-4 text-[12px] text-text-muted text-center">
            {t("settings.advanced.noDecisions")}
          </div>
        ) : (
          <div className="border border-border rounded overflow-hidden">
            <table className="w-full text-[12px]">
              <thead className="bg-bg text-text-muted font-mono text-[10px] uppercase tracking-[0.1em]">
                <tr>
                  <th className="text-left px-3 py-2">{t("settings.advanced.colTime")}</th>
                  <th className="text-left px-3 py-2">{t("settings.advanced.colTool")}</th>
                  <th className="text-right px-3 py-2">{t("settings.advanced.colLatency")}</th>
                  <th className="text-center px-3 py-2">{t("settings.advanced.colOk")}</th>
                  <th className="text-left px-3 py-2">{t("settings.advanced.colArgs")}</th>
                </tr>
              </thead>
              <tbody>
                {decisions.map((d, i) => (
                  <tr key={`${d.task_id}-${i}`} className="border-t border-border">
                    <td className="px-3 py-2 font-mono text-text-muted">
                      {(d.created_at || "").slice(11, 19)}
                    </td>
                    <td className="px-3 py-2 font-mono">{d.chosen_tool || d.task_id?.slice(0, 8) || "—"}</td>
                    <td className="px-3 py-2 text-right font-mono">{d.latency_ms ?? "—"}ms</td>
                    <td className="px-3 py-2 text-center">
                      {d.success === false ? (
                        <span className="text-warning">✗</span>
                      ) : d.success === true ? (
                        <span className="text-success">✓</span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="px-3 py-2 font-mono text-text-muted truncate max-w-[300px]">
                      {d.args_summary || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="flex flex-col gap-2">
        <h2 className="font-display text-sm font-semibold flex items-center gap-2">
          <FileCode2 size={13} strokeWidth={1.5} /> {t("settings.advanced.rawYaml")}
        </h2>
        <pre className="border border-border rounded p-3 text-[11px] font-mono whitespace-pre-wrap overflow-x-auto bg-bg max-h-[320px] overflow-y-auto">
          {yaml}
        </pre>
      </div>

      <div className="flex flex-col gap-2 border-t border-border pt-4">
        <h2 className="font-display text-sm font-semibold flex items-center gap-2 text-warning">
          <AlertTriangle size={13} strokeWidth={1.5} /> {t("settings.advanced.dangerZone")}
        </h2>
        <p className="text-[11px] text-text-muted">
          {t("settings.advanced.dangerZoneDesc")}
        </p>
        <div className="flex items-center gap-2">
          <button
            disabled
            className="h-7 px-3 border border-border rounded text-[12px] text-warning disabled:opacity-50"
            title={t("settings.advanced.cliHint", { cmd: "/memory clear" })}
          >
            {t("settings.advanced.clearMemory")}
          </button>
          <button
            disabled
            className="h-7 px-3 border border-border rounded text-[12px] text-warning disabled:opacity-50"
            title={t("settings.advanced.cliHint", { cmd: "/perm reset" })}
          >
            {t("settings.advanced.resetPermissions")}
          </button>
          <button
            onClick={() => {
              useWizardState.getState().reset();
              useWS.getState().send({ type: "onboarding.reset" });
            }}
            data-testid="reset-onboarding-button"
            className="h-7 px-3 border border-border rounded text-[12px]"
            title={t("settings.advanced.resetOnboardingHint")}
          >
            {t("settings.advanced.resetOnboarding")}
          </button>
        </div>
      </div>
    </div>
  );
}

async function fetchRawYaml(): Promise<string> {
  const token = await fetchWSToken();
  const res = await fetch("/api/fsar_yaml", {
    credentials: "same-origin",
    cache: "no-store",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  return String(data.yaml ?? "");
}
