// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useWS } from "../../stores/ws";
import { useUI, type Theme, type Density, type Motion } from "../../stores/ui";

const PAGES = ["chat", "reflection", "memory", "library", "insights", "settings", "usage"];

export function StyleTab() {
  const send = useWS((s) => s.send);
  const theme = useUI((s) => s.theme);
  const setThemeStore = useUI((s) => s.setTheme);
  const density = useUI((s) => s.density);
  const setDensityStore = useUI((s) => s.setDensity);
  const motion = useUI((s) => s.motion);
  const setMotionStore = useUI((s) => s.setMotion);
  const fontScale = useUI((s) => s.fontScale);
  const setFontScaleStore = useUI((s) => s.setFontScale);
  const overrides = useUI((s) => s.perPageOverrides);
  const setOverrideStore = useUI((s) => s.setOverride);
  const [overridePage, setOverridePage] = useState<string>(PAGES[0]);

  function setThemeBoth(t: Theme) {
    setThemeStore(t);
    send({ type: "style.set_theme", theme: t });
  }

  function setDensityBoth(d: Density) {
    setDensityStore(d);
    send({ type: "style.patch", patch: { density: d } });
  }

  function setMotionBoth(m: Motion) {
    setMotionStore(m);
    send({ type: "style.patch", patch: { motion: m } });
  }

  function setFontScaleBoth(s: number) {
    setFontScaleStore(s);
    send({ type: "style.patch", patch: { font_scale: s } });
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <h2 className="font-display text-sm font-semibold">Theme</h2>
        <div className="flex items-center gap-2">
          {(["light", "dark", "system"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setThemeBoth(m)}
              className={`h-7 px-3 text-[12px] border rounded font-mono uppercase tracking-[0.05em] ${
                theme === m ? "bg-text text-bg border-border" : "border-border text-text-muted hover:bg-surface"
              }`}
            >
              {m}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <h2 className="font-display text-sm font-semibold">Font scale ({fontScale.toFixed(2)})</h2>
        <input
          type="range"
          min="0.85"
          max="1.30"
          step="0.05"
          value={fontScale}
          onChange={(e) => setFontScaleBoth(Number(e.target.value))}
          className="w-full"
        />
      </div>

      <div className="flex flex-col gap-2">
        <h2 className="font-display text-sm font-semibold">Density</h2>
        <div className="flex items-center gap-2">
          {(["comfortable", "compact"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setDensityBoth(m)}
              className={`h-7 px-3 text-[12px] border rounded font-mono uppercase tracking-[0.05em] ${
                density === m ? "bg-text text-bg border-border" : "border-border text-text-muted hover:bg-surface"
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
              onClick={() => setMotionBoth(m)}
              className={`h-7 px-3 text-[12px] border rounded font-mono uppercase tracking-[0.05em] ${
                motion === m ? "bg-text text-bg border-border" : "border-border text-text-muted hover:bg-surface"
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
            onClick={() => {
              setOverrideStore(overridePage, "theme", null);
              setOverrideStore(overridePage, "density", null);
              setOverrideStore(overridePage, "motion", null);
            }}
            disabled={!overrides[overridePage]}
            className="h-7 px-2 text-[12px] border border-border rounded text-text-muted hover:bg-surface disabled:opacity-50"
          >
            Clear
          </button>
        </div>

        <div className="grid grid-cols-3 gap-2">
          {(["theme", "density", "motion"] as const).map((key) => {
            const v = overrides[overridePage]?.[key] as string | undefined;
            return (
              <label key={key} className="flex flex-col gap-1 text-[11px] font-mono">
                <span className="text-text-muted">{key}</span>
                <input
                  value={v ?? ""}
                  onChange={(e) => {
                    const val = (e.target.value || null) as Parameters<typeof setOverrideStore>[2];
                    setOverrideStore(overridePage, key, val);
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
