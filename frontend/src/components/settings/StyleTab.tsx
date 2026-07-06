// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useWS } from "../../stores/ws";

type Theme = "light" | "dark" | "system";
type Density = "comfortable" | "compact";
type Motion = "subtle" | "full" | "none";

function getStyle(config: Record<string, unknown> | null): {
  theme: Theme;
  font_scale: number;
  density: Density;
  motion: Motion;
  per_page_overrides: Record<string, Record<string, unknown>>;
} {
  const s = ((config?.style ?? {}) as Record<string, unknown>) || {};
  return {
    theme: (s.theme as Theme) ?? "system",
    font_scale: Number(s.font_scale ?? 1.0),
    density: (s.density as Density) ?? "comfortable",
    motion: (s.motion as Motion) ?? "subtle",
    per_page_overrides: (s.per_page_overrides as Record<string, Record<string, unknown>>) ?? {},
  };
}

const PAGES = ["chat", "reflection", "memory", "library", "insights", "settings", "usage"];

export function StyleTab() {
  const send = useWS((s) => s.send);
  const config = useWS((s) => s.config);
  const s = getStyle(config);
  const [overridePage, setOverridePage] = useState<string>(PAGES[0]);

  function setTheme(theme: Theme) {
    send({ type: "style.set_theme", theme });
  }

  function patch(key: string, value: unknown) {
    send({ type: "style.patch", patch: { [key]: value } });
  }

  function setOverride(page: string, key: string, value: unknown) {
    const next = { ...s.per_page_overrides };
    next[page] = { ...(next[page] || {}), [key]: value };
    patch("per_page_overrides", next);
  }

  function clearOverride(page: string) {
    const next = { ...s.per_page_overrides };
    delete next[page];
    patch("per_page_overrides", next);
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <h2 className="font-display text-sm font-semibold">Theme</h2>
        <div className="flex items-center gap-2">
          {(["light", "dark", "system"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setTheme(m)}
              className={`h-7 px-3 text-[12px] border rounded font-mono uppercase tracking-[0.05em] ${
                s.theme === m ? "bg-text text-bg border-border" : "border-border text-text-muted hover:bg-surface"
              }`}
            >
              {m}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <h2 className="font-display text-sm font-semibold">Font scale ({s.font_scale.toFixed(2)})</h2>
        <input
          type="range"
          min="0.85"
          max="1.30"
          step="0.05"
          value={s.font_scale}
          onChange={(e) => patch("font_scale", Number(e.target.value))}
          className="w-full"
        />
      </div>

      <div className="flex flex-col gap-2">
        <h2 className="font-display text-sm font-semibold">Density</h2>
        <div className="flex items-center gap-2">
          {(["comfortable", "compact"] as const).map((m) => (
            <button
              key={m}
              onClick={() => patch("density", m)}
              className={`h-7 px-3 text-[12px] border rounded font-mono uppercase tracking-[0.05em] ${
                s.density === m ? "bg-text text-bg border-border" : "border-border text-text-muted hover:bg-surface"
              }`}
            >
              {m}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <h2 className="font-display text-sm font-semibold">Motion</h2>
        <div className="flex items-center gap-2">
          {(["subtle", "full", "none"] as const).map((m) => (
            <button
              key={m}
              onClick={() => patch("motion", m)}
              className={`h-7 px-3 text-[12px] border rounded font-mono uppercase tracking-[0.05em] ${
                s.motion === m ? "bg-text text-bg border-border" : "border-border text-text-muted hover:bg-surface"
              }`}
            >
              {m}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-col gap-3 border-t border-border pt-4">
        <h2 className="font-display text-sm font-semibold">Per-page overrides</h2>
        <div className="flex items-center gap-2">
          <span className="text-[12px] text-text-muted font-mono">page:</span>
          <select
            value={overridePage}
            onChange={(e) => setOverridePage(e.target.value)}
            className="bg-bg border border-border rounded px-2 h-7 text-[12px] font-mono"
          >
            {PAGES.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
          <button
            onClick={() => clearOverride(overridePage)}
            disabled={!s.per_page_overrides[overridePage]}
            className="h-7 px-2 text-[12px] border border-border rounded text-text-muted hover:bg-surface disabled:opacity-50"
          >
            Clear
          </button>
        </div>

        <div className="grid grid-cols-3 gap-2">
          {(["theme", "density", "motion"] as const).map((key) => {
            const v = s.per_page_overrides[overridePage]?.[key] as string | undefined;
            return (
              <label key={key} className="flex flex-col gap-1 text-[11px] font-mono">
                <span className="text-text-muted">{key}</span>
                <input
                  value={v ?? ""}
                  onChange={(e) => {
                    const val = e.target.value;
                    if (!val) {
                      const next = { ...s.per_page_overrides };
                      const inner = { ...(next[overridePage] || {}) };
                      delete inner[key];
                      if (Object.keys(inner).length === 0) delete next[overridePage];
                      else next[overridePage] = inner;
                      patch("per_page_overrides", next);
                    } else {
                      setOverride(overridePage, key, val);
                    }
                  }}
                  placeholder={`override ${key}`}
                  className="bg-bg border border-border rounded px-2 h-7 text-[12px] font-mono"
                />
              </label>
            );
          })}
        </div>
      </div>
    </div>
  );
}
