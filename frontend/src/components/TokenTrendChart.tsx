// SPDX-License-Identifier: MIT
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

interface TrendDay {
  date: string;
  prompt_tokens: number;
  completion_tokens: number;
  cache_read_tokens: number;
  cache_creation_tokens: number;
}

function cssVar(name: string, fallback: string): string {
  if (typeof document === "undefined") return fallback;
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
  return value || fallback;
}

function TrendTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-border bg-[var(--surface)] px-3 py-2 text-[11px] shadow-lg">
      <div className="font-mono text-text-muted mb-1">{label}</div>
      {payload.map((p: any) => (
        <div key={p.dataKey} className="flex items-center justify-between gap-8">
          <span className="flex items-center gap-1.5 text-text-muted">
            <span
              className="inline-block w-2 h-2 rounded-full"
              style={{ background: p.color }}
            />
            {p.name}
          </span>
          <span className="font-mono">{Number(p.value).toLocaleString()}</span>
        </div>
      ))}
    </div>
  );
}

export default function TokenTrendChart({ timeline }: { timeline: TrendDay[] }) {
  const { t } = useTranslation();
  const data = useMemo(
    () =>
      timeline.slice(-14).map((d) => ({
        date: d.date,
        input: d.prompt_tokens,
        cacheRead: d.cache_read_tokens,
        cacheCreation: d.cache_creation_tokens,
        output: d.completion_tokens,
      })),
    [timeline],
  );

  const input = cssVar("--text", "#111111");
  const cacheRead = cssVar("--success", "#16865b");
  const cacheCreation = cssVar("--warning", "#ad7414");
  const output = cssVar("--text-muted", "#727272");
  const grid = cssVar("--border", "rgba(17,17,17,0.1)");
  const axis = cssVar("--text-faint", "#a5a5a5");

  const series = [
    { key: "input", name: t("usage.chartInput"), color: input },
    { key: "cacheRead", name: t("usage.chartCacheRead"), color: cacheRead },
    { key: "cacheCreation", name: t("usage.chartCacheCreate"), color: cacheCreation, dashed: true },
    { key: "output", name: t("usage.chartOutput"), color: output },
  ];

  return (
    <div className="border border-border rounded p-4">
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={grid} vertical={false} />
          <XAxis
            dataKey="date"
            tickFormatter={(v: string) => v.slice(5)}
            stroke={axis}
            fontSize={10}
            tickLine={false}
          />
          <YAxis stroke={axis} fontSize={10} tickLine={false} width={48} />
          <Tooltip content={<TrendTooltip />} />
          <Legend wrapperStyle={{ fontSize: 11, paddingTop: 8 }} />
          {series.map((s) => (
            <Line
              key={s.key}
              type="monotone"
              dataKey={s.key}
              name={s.name}
              stroke={s.color}
              strokeWidth={1.8}
              dot={false}
              strokeDasharray={s.dashed ? "4 3" : undefined}
              activeDot={{ r: 3 }}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}