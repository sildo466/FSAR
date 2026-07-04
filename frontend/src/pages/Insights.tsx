// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { useWS } from "../stores/ws";

interface ToolStat {
  tool_name: string;
  total_uses: number;
  successes: number;
  failures: number;
  success_rate_pct: number;
  avg_latency_ms: number;
  avg_failure_latency_ms?: number | null;
}

interface RecentDecision {
  id: number;
  chosen_tool: string;
  success: boolean;
  latency_ms: number;
  prompt_tokens?: number;
  completion_tokens?: number;
  cached_tokens?: number;
  created_at: string;
  args_summary?: string;
}

interface InsightsSnapshot {
  kpis: {
    total_decisions: number;
    success_rate_pct: number;
    total_tokens: number;
    total_prompt_tokens: number;
    total_completion_tokens: number;
    total_cached_tokens: number;
  };
  tool_stats: ToolStat[];
  active_strategies_markdown: string;
  recent_decisions: RecentDecision[];
}

export function Insights() {
  const send = useWS((s) => s.send);
  const client = useWS((s) => s.client);
  const [data, setData] = useState<InsightsSnapshot | null>(null);

  useEffect(() => {
    send({ type: "insights.get" });
  }, [send]);

  useEffect(() => {
    return client?.on((msg) => {
      if (msg.type === "insights.snapshot") {
        setData({
          kpis: msg.kpis as InsightsSnapshot["kpis"],
          tool_stats: msg.tool_stats as unknown as ToolStat[],
          active_strategies_markdown: msg.active_strategies_markdown,
          recent_decisions: msg.recent_decisions as unknown as RecentDecision[],
        });
      }
    });
  }, [client]);

  const kpis = data?.kpis;
  const stats = data?.tool_stats ?? [];
  const recent = data?.recent_decisions ?? [];
  const strategies = data?.active_strategies_markdown ?? "";

  return (
    <div className="max-w-[960px] mx-auto px-8 py-10 flex flex-col gap-10">
      <header>
        <h1 className="font-display text-2xl font-semibold tracking-[-0.01em]">Insights</h1>
        <p className="text-text-muted">How FSAR uses tools, spends tokens, and learns.</p>
      </header>

      <section className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KpiCard label="Decisions" value={kpis ? kpis.total_decisions.toLocaleString() : "—"} />
        <KpiCard label="Success rate" value={kpis ? `${kpis.success_rate_pct}%` : "—"} />
        <KpiCard label="Total tokens" value={kpis ? kpis.total_tokens.toLocaleString() : "—"} />
        <KpiCard
          label="Cached tokens"
          value={kpis ? kpis.total_cached_tokens.toLocaleString() : "—"}
        />
      </section>

      <section>
        <SectionTitle>Tool usage</SectionTitle>
        {stats.length === 0 ? (
          <p className="text-text-muted text-sm">No tool calls yet.</p>
        ) : (
          <div className="border border-border rounded overflow-hidden">
            <table className="w-full text-[13px]">
              <thead className="bg-bg text-text-muted font-mono text-[11px] uppercase tracking-[0.08em]">
                <tr>
                  <th className="text-left px-3 py-2">Tool</th>
                  <th className="text-right px-3 py-2">Uses</th>
                  <th className="text-right px-3 py-2">Success</th>
                  <th className="text-right px-3 py-2">Avg latency</th>
                </tr>
              </thead>
              <tbody>
                {stats.map((s) => (
                  <tr key={s.tool_name} className="border-t border-border">
                    <td className="px-3 py-2 font-mono">#{s.tool_name}</td>
                    <td className="px-3 py-2 text-right font-mono">{s.total_uses}</td>
                    <td className="px-3 py-2 text-right font-mono">{s.success_rate_pct}%</td>
                    <td className="px-3 py-2 text-right font-mono">
                      {s.avg_latency_ms ? `${s.avg_latency_ms}ms` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section>
        <SectionTitle>Reflections</SectionTitle>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <KpiCard label="Active strategies" value={String(countStrategies(strategies))} />
          <KpiCard label="Total prompts" value={kpis ? kpis.total_prompt_tokens.toLocaleString() : "—"} />
          <KpiCard label="Total completions" value={kpis ? kpis.total_completion_tokens.toLocaleString() : "—"} />
          <KpiCard label="Cached share" value={kpis ? `${cachedShare(kpis)}%` : "—"} />
        </div>
        <div className="border border-border rounded p-4 mt-4">
          <pre className="font-mono text-[12.5px] whitespace-pre-wrap leading-[1.55]">
            {strategies || "_No active strategies yet._"}
          </pre>
        </div>
      </section>

      <section>
        <SectionTitle>Recent decisions</SectionTitle>
        {recent.length === 0 ? (
          <p className="text-text-muted text-sm">No decisions yet.</p>
        ) : (
          <ul className="border border-border rounded divide-y divide-border">
            {recent.map((d) => (
              <li key={d.id} className="px-4 py-3 flex items-center gap-4">
                <span
                  className={`inline-block w-2 h-2 rounded-full ${d.success ? "bg-text" : "bg-text-muted"}`}
                  aria-label={d.success ? "success" : "failure"}
                />
                <span className="font-mono text-[13px] flex-1">#{d.chosen_tool}</span>
                <span className="font-mono text-[11px] text-text-muted">{d.latency_ms}ms</span>
                <span className="font-mono text-[11px] text-text-muted">
                  {(d.prompt_tokens ?? 0) + (d.completion_tokens ?? 0)} tok
                </span>
                <span className="font-mono text-[11px] text-text-muted">
                  {new Date(d.created_at).toLocaleTimeString()}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function KpiCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="border border-border rounded p-4 flex flex-col gap-2">
      <div className="font-display text-[10px] font-bold uppercase tracking-[0.1em] text-text-muted">
        {label}
      </div>
      <div className="font-display text-2xl font-semibold tracking-[-0.01em]">{value}</div>
    </div>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div className="font-display text-[10px] font-bold uppercase tracking-[0.1em] text-text-muted mb-3">
      {children}
    </div>
  );
}

function countStrategies(markdown: string): number {
  if (!markdown) return 0;
  return markdown.split("\n").filter((l) => l.trim().startsWith("- **[")).length;
}

function cachedShare(k: InsightsSnapshot["kpis"]): string {
  if (!k.total_tokens) return "0";
  return ((100 * k.total_cached_tokens) / k.total_tokens).toFixed(0);
}
