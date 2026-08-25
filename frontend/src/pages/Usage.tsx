// SPDX-License-Identifier: MIT
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useWS } from "../stores/ws";

interface ToolRow {
  tool: string;
  calls: number;
  tokens_in: number;
  tokens_out: number;
  success_rate_pct: number;
  avg_latency_ms: number;
}

interface TimelineDay {
  date: string;
  prompt_tokens: number;
  completion_tokens: number;
  cache_read_tokens: number;
  cache_creation_tokens: number;
}

interface ProviderRow {
  provider: string;
  model: string;
  prompt_tokens: number;
  completion_tokens: number;
  cache_read_tokens: number;
  cache_creation_tokens: number;
  cache_hit_pct: number;
  cost_usd: number;
}

interface UsageSnapshot {
  kpis: {
    total_tokens: number;
    prompt_tokens: number;
    completion_tokens: number;
    cached_tokens: number;
    cache_creation_tokens: number;
    cache_hit_pct: number;
    estimated_cost_usd: number;
    forecast_monthly_usd: number;
    decision_rows: number;
    requests: number;
    from: string;
    to: string;
  };
  timeline: TimelineDay[];
  per_provider: ProviderRow[];
  per_tool: ToolRow[];
}

const CHART_DAYS = 14;

export function Usage() {
  const { t } = useTranslation();
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
          timeline: msg.timeline as unknown as TimelineDay[],
          per_provider: msg.per_provider as unknown as ProviderRow[],
          per_tool: msg.per_tool as unknown as ToolRow[],
        });
      }
    });
  }, [client]);

  const k = data?.kpis;
  const tools = data?.per_tool ?? [];
  const timeline = data?.timeline ?? [];
  const providers = data?.per_provider ?? [];
  const maxDay = Math.max(
    1,
    ...timeline.map(
      (d) =>
        d.prompt_tokens + d.completion_tokens +
        d.cache_read_tokens + d.cache_creation_tokens,
    ),
  );

  return (
    <div className="max-w-[960px] mx-auto px-8 py-10 flex flex-col gap-10">
      <header>
        <h1 className="font-display text-2xl font-semibold tracking-[-0.01em]">{t("usage.title")}</h1>
        <p className="text-text-muted">{t("usage.subtitle")}</p>
      </header>

      <section className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Kpi label={t("usage.totalTokens")} value={k ? k.total_tokens.toLocaleString() : "—"} />
        <Kpi
          label={t("usage.cachedTokens")}
          value={
            k ? `${k.cached_tokens.toLocaleString()} (${k.cache_hit_pct}%)` : "—"
          }
        />
        <Kpi
          label={t("usage.estimatedCost")}
          value={k ? `$${k.estimated_cost_usd.toFixed(4)}` : "—"}
        />
        <Kpi
          label={t("usage.decisionRows")}
          value={k ? k.decision_rows.toLocaleString() : "—"}
        />
      </section>

      <section>
        <SectionTitle>{t("usage.tokenTrend")}</SectionTitle>
        {timeline.length === 0 ? (
          <p className="text-text-muted text-sm">{t("usage.noUsage")}</p>
        ) : (
          <TokenTrendChart timeline={timeline} />
        )}
      </section>

      <section>
        <SectionTitle>{t("usage.dailyTokens")}</SectionTitle>
        {timeline.length === 0 ? (
          <p className="text-text-muted text-sm">{t("usage.noUsage")}</p>
        ) : (
          <div className="border border-border rounded p-4 flex flex-col gap-2">
            {timeline.slice(-14).map((d) => {
              const total =
                d.prompt_tokens + d.completion_tokens +
                d.cache_read_tokens + d.cache_creation_tokens;
              return (
                <div key={d.date} className="flex items-center gap-3 text-[12px]">
                  <span className="font-mono text-text-muted w-20 shrink-0">{d.date}</span>
                  <div className="flex-1 h-2 bg-bg border border-border rounded overflow-hidden">
                    <div
                      className="h-full bg-text"
                      style={{ width: `${(total / maxDay) * 100}%` }}
                    />
                  </div>
                  <span className="font-mono w-24 text-right">{total.toLocaleString()}</span>
                </div>
              );
            })}
          </div>
        )}
      </section>

      <section>
        <SectionTitle>{t("usage.perProvider")}</SectionTitle>
        {providers.length === 0 ? (
          <p className="text-text-muted text-sm">{t("usage.noProviderUsage")}</p>
        ) : (
          <div className="border border-border rounded overflow-hidden">
            <table className="w-full text-[13px]">
              <thead className="bg-bg text-text-muted font-mono text-[11px] uppercase tracking-[0.08em]">
                <tr>
                  <th className="text-left px-3 py-2">{t("usage.colProvider")}</th>
                  <th className="text-left px-3 py-2">{t("usage.colModel")}</th>
                  <th className="text-right px-3 py-2">{t("usage.colPrompt")}</th>
                  <th className="text-right px-3 py-2">{t("usage.colCompletion")}</th>
                  <th className="text-right px-3 py-2">{t("usage.colCacheRead")}</th>
                  <th className="text-right px-3 py-2">{t("usage.colCacheCreate")}</th>
                  <th className="text-right px-3 py-2">{t("usage.colHitRate")}</th>
                  <th className="text-right px-3 py-2">{t("usage.colCost")}</th>
                </tr>
              </thead>
              <tbody>
                {providers.map((p) => (
                  <tr key={p.provider} className="border-t border-border">
                    <td className="px-3 py-2 font-mono">{p.provider}</td>
                    <td className="px-3 py-2 font-mono">{p.model}</td>
                    <td className="px-3 py-2 text-right font-mono">
                      {p.prompt_tokens.toLocaleString()}
                    </td>
                    <td className="px-3 py-2 text-right font-mono">
                      {p.completion_tokens.toLocaleString()}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-text-muted">
                      {p.cache_read_tokens.toLocaleString()}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-text-muted">
                      {p.cache_creation_tokens.toLocaleString()}
                    </td>
                    <td className="px-3 py-2 text-right font-mono">
                      {p.cache_hit_pct}%
                    </td>
                    <td className="px-3 py-2 text-right font-mono">
                      ${p.cost_usd.toFixed(4)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section>
        <SectionTitle>{t("usage.perTool")}</SectionTitle>
        {tools.length === 0 ? (
          <p className="text-text-muted text-sm">{t("usage.noToolCalls")}</p>
        ) : (
          <div className="border border-border rounded overflow-hidden">
            <table className="w-full text-[13px]">
              <thead className="bg-bg text-text-muted font-mono text-[11px] uppercase tracking-[0.08em]">
                <tr>
                  <th className="text-left px-3 py-2">{t("usage.colTool")}</th>
                  <th className="text-right px-3 py-2">{t("usage.colCalls")}</th>
                  <th className="text-right px-3 py-2">{t("usage.colSuccess")}</th>
                  <th className="text-right px-3 py-2">{t("usage.colAvgLatency")}</th>
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
        <SectionTitle>{t("usage.costForecast")}</SectionTitle>
        <div className="border border-border rounded p-4">
          {k && k.forecast_monthly_usd > 0 ? (
            <p className="text-[13px]">
              {t("usage.forecastAmount", { amount: k.forecast_monthly_usd.toFixed(4) })}
            </p>
          ) : (
            <p className="text-[13px] text-text-muted">
              {t("usage.forecastHint")}
            </p>
          )}
        </div>
      </section>
    </div>
  );
}

function TokenTrendChart({ timeline }: { timeline: TimelineDay[] }) {
  const { t } = useTranslation();
  const days = timeline.slice(-CHART_DAYS);
  if (days.length === 0) return null;

  const W = 640;
  const H = 160;
  const PL = 44;
  const PR = 12;
  const PT = 12;
  const PB = 20;
  const innerW = W - PL - PR;
  const innerH = H - PT - PB;
  const maxVal = Math.max(
    1,
    ...days.map(
      (d) => d.prompt_tokens + d.cache_read_tokens + d.completion_tokens,
    ),
  );
  const x = (i: number) =>
    PL + (days.length === 1 ? innerW / 2 : (i / (days.length - 1)) * innerW);
  const y = (v: number) => PT + innerH - (v / maxVal) * innerH;

  const series: Array<{
    key: "prompt_tokens" | "cache_read_tokens" | "completion_tokens";
    stroke: string;
    label: string;
  }> = [
    { key: "prompt_tokens", stroke: "var(--text)", label: t("usage.chartInput") },
    { key: "cache_read_tokens", stroke: "var(--success)", label: t("usage.chartCacheRead") },
    { key: "completion_tokens", stroke: "var(--text-muted)", label: t("usage.chartOutput") },
  ];

  return (
    <div className="border border-border rounded p-4 flex flex-col gap-3">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
        {[0, 0.25, 0.5, 0.75, 1].map((f) => {
          const gy = PT + innerH - f * innerH;
          return (
            <line
              key={f}
              x1={PL}
              y1={gy}
              x2={W - PR}
              y2={gy}
              stroke="var(--border)"
              strokeDasharray="3 3"
            />
          );
        })}
        {series.map((s) => {
          const points = days
            .map((d, i) => `${x(i).toFixed(1)},${y(d[s.key]).toFixed(1)}`)
            .join(" ");
          return (
            <polyline
              key={s.key}
              points={points}
              fill="none"
              stroke={s.stroke}
              strokeWidth={1.5}
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          );
        })}
        {days.map((d, i) => (
          <text
            key={d.date}
            x={x(i)}
            y={H - 6}
            textAnchor="middle"
            className="font-mono text-text-faint"
            style={{ fontSize: 9 }}
          >
            {d.date.slice(5)}
          </text>
        ))}
        {[0, 0.25, 0.5, 0.75, 1].map((f) => (
          <text
            key={f}
            x={PL - 6}
            y={PT + innerH - f * innerH + 3}
            textAnchor="end"
            className="font-mono text-text-faint"
            style={{ fontSize: 9 }}
          >
            {Math.round(maxVal * (1 - f)).toLocaleString()}
          </text>
        ))}
      </svg>
      <div className="flex items-center gap-4">
        {series.map((s) => (
          <span key={s.key} className="flex items-center gap-1.5 text-[11px] text-text-muted">
            <span
              className="inline-block w-2.5 h-2.5 rounded-full"
              style={{ background: s.stroke }}
            />
            {s.label}
          </span>
        ))}
      </div>
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