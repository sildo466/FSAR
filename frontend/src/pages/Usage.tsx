// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { useWS } from "../stores/ws";

interface CacheStats {
  l1_entries: number;
  l1_capacity: number;
  l1_hit_rate: number;
  l2_entries: number;
  l2_size_bytes: number;
  l2_hit_rate: number;
}

interface ToolRow {
  tool: string;
  calls: number;
  tokens_in: number;
  tokens_out: number;
  success_rate_pct: number;
  avg_latency_ms: number;
}

interface UsageSnapshot {
  kpis: {
    total_tokens: number;
    prompt_tokens: number;
    completion_tokens: number;
    cached_tokens: number;
    cache_hit_pct: number;
    estimated_cost_usd: number;
    decision_rows: number;
    from: string;
    to: string;
  };
  timeline: unknown[];
  per_provider: unknown[];
  per_tool: ToolRow[];
  cache: CacheStats;
}

export function Usage() {
  const send = useWS((s) => s.send);
  const client = useWS((s) => s.client);
  const [data, setData] = useState<UsageSnapshot | null>(null);

  useEffect(() => {
    send({ type: "usage.range", from: "1970-01-01", to: "2099-12-31" });
  }, [send]);

  useEffect(() => {
    return client?.on((msg) => {
      if (msg.type === "usage.snapshot") {
        setData({
          kpis: msg.kpis as unknown as UsageSnapshot["kpis"],
          timeline: msg.timeline,
          per_provider: msg.per_provider,
          per_tool: msg.per_tool as unknown as ToolRow[],
          cache: msg.cache as unknown as CacheStats,
        });
      }
    });
  }, [client]);

  const k = data?.kpis;
  const cache = data?.cache;
  const tools = data?.per_tool ?? [];

  return (
    <div className="max-w-[960px] mx-auto px-8 py-10 flex flex-col gap-10">
      <header>
        <h1 className="font-display text-2xl font-semibold tracking-[-0.01em]">Usage</h1>
        <p className="text-text-muted">Tokens, cache efficiency, and projected cost.</p>
      </header>

      <section className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Kpi label="Total tokens" value={k ? k.total_tokens.toLocaleString() : "—"} />
        <Kpi
          label="Cached tokens"
          value={
            k ? `${k.cached_tokens.toLocaleString()} (${k.cache_hit_pct}%)` : "—"
          }
        />
        <Kpi
          label="Estimated cost"
          value={k ? `$${k.estimated_cost_usd.toFixed(4)}` : "—"}
        />
        <Kpi
          label="Decision rows"
          value={k ? k.decision_rows.toLocaleString() : "—"}
        />
      </section>

      <section>
        <SectionTitle>Cache breakdown</SectionTitle>
        {cache ? (
          <div className="border border-border rounded p-4 flex flex-col gap-3">
            <Bar
              label={`L1 (in-memory) · ${cache.l1_entries}/${cache.l1_capacity}`}
              value={cache.l1_hit_rate}
              fmt={(v) => `${(v * 100).toFixed(1)}% hit`}
            />
            <Bar
              label={`L2 (sqlite) · ${cache.l2_entries} entries · ${formatBytes(cache.l2_size_bytes)}`}
              value={cache.l2_hit_rate}
              fmt={(v) => `${(v * 100).toFixed(1)}% hit`}
            />
          </div>
        ) : (
          <p className="text-text-muted text-sm">No cache data.</p>
        )}
      </section>

      <section>
        <SectionTitle>Per-tool</SectionTitle>
        {tools.length === 0 ? (
          <p className="text-text-muted text-sm">No tool calls in range.</p>
        ) : (
          <div className="border border-border rounded overflow-hidden">
            <table className="w-full text-[13px]">
              <thead className="bg-bg text-text-muted font-mono text-[11px] uppercase tracking-[0.08em]">
                <tr>
                  <th className="text-left px-3 py-2">Tool</th>
                  <th className="text-right px-3 py-2">Calls</th>
                  <th className="text-right px-3 py-2">Success</th>
                  <th className="text-right px-3 py-2">Avg latency</th>
                </tr>
              </thead>
              <tbody>
                {tools.map((t) => (
                  <tr key={t.tool} className="border-t border-border">
                    <td className="px-3 py-2 font-mono">#{t.tool}</td>
                    <td className="px-3 py-2 text-right font-mono">{t.calls}</td>
                    <td className="px-3 py-2 text-right font-mono">
                      {t.success_rate_pct}%
                    </td>
                    <td className="px-3 py-2 text-right font-mono">
                      {t.avg_latency_ms}ms
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section>
        <SectionTitle>Cost forecast</SectionTitle>
        <div className="border border-border rounded p-4">
          <p className="text-[13px] text-text-muted">
            Forecast activates once at least one active LLM provider has its
            <code className="font-mono px-1">input_per_1k</code>/
            <code className="font-mono px-1">output_per_1k</code> rates
            configured and the GUI is wired to the live LLM (P7.11).
          </p>
        </div>
      </section>
    </div>
  );
}

function Kpi({ label, value }: { label: string; value: string }) {
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

function Bar({
  label,
  value,
  fmt,
}: {
  label: string;
  value: number;
  fmt: (v: number) => string;
}) {
  const pct = Math.max(0, Math.min(1, value || 0)) * 100;
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between text-[12px]">
        <span className="text-text-muted">{label}</span>
        <span className="font-mono text-text">{fmt(value || 0)}</span>
      </div>
      <div className="h-2 bg-bg border border-border rounded overflow-hidden">
        <div className="h-full bg-text" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function formatBytes(n: number): string {
  if (!n) return "0 B";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}
