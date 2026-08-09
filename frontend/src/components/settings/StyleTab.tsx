// SPDX-License-Identifier: MIT
import { useState } from "react";
import { useWS } from "../../stores/ws";
import { useUI, type Theme, type Density, type Motion, type FontSet } from "../../stores/ui";
import { Capsule, Input, Pill } from "../ui/primitives";
import { LanguageSection } from "./LanguageSection";
import { useTranslation } from "react-i18next";

const PAGES = ["chat", "reflection", "memory", "library", "insights", "settings", "usage"];

const FONT_SETS = [
  { key: "A", labelKey: "settings.style.fontSet.technical", detailKey: "settings.style.fontSet.geistMono" },
  { key: "B", labelKey: "settings.style.fontSet.companion", detailKey: "settings.style.fontSet.frauncesDmSans" },
  { key: "C", labelKey: "settings.style.fontSet.quiet", detailKey: "settings.style.fontSet.geistManrope" },
] as const;

export function StyleTab() {
  const { t } = useTranslation();
  const send = useWS((s) => s.send);
  const theme = useUI((s) => s.theme);
  const setThemeStore = useUI((s) => s.setTheme);
  const density = useUI((s) => s.density);
  const setDensityStore = useUI((s) => s.setDensity);
  const motion = useUI((s) => s.motion);
  const setMotionStore = useUI((s) => s.setMotion);
  const fontScale = useUI((s) => s.fontScale);
  const setFontScaleStore = useUI((s) => s.setFontScale);
  const fontSet = useUI((s) => s.fontSet);
  const setFontSet = useUI((s) => s.setFontSet);
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
    <div className="flex flex-col gap-5">
      <Capsule className="flex flex-col gap-3">
        <h2 className="font-display text-sm font-semibold">{t("settings.style.fontPersonality")}</h2>
        <div className="grid grid-cols-3 gap-2">
          {FONT_SETS.map(({ key, labelKey, detailKey }) => (
            <Pill key={key} variant={fontSet === key ? 'primary' : 'glass'} onClick={() => { setFontSet(key as FontSet); send({ type: 'style.patch', patch: { font_set: key } }); }} className="h-auto flex-col py-3">
              <span>{t(labelKey)}</span><span className="text-[9px] opacity-60">{t(detailKey)}</span>
            </Pill>
          ))}
        </div>
      </Capsule>
      <LanguageSection />
      <Capsule className="flex flex-col gap-2">
        <h2 className="font-display text-sm font-semibold">{t("settings.style.theme")}</h2>
        <div className="flex items-center gap-2">
          {(["light", "dark", "system"] as const).map((m) => (
            <Pill
              key={m}
              onClick={() => setThemeBoth(m)}
              variant={theme === m ? "primary" : "glass"}
              size="sm"
            >
              {t(`settings.style.theme.${m}`)}
            </Pill>
          ))}
        </div>
      </Capsule>

      <Capsule className="flex flex-col gap-2">
        <h2 className="font-display text-sm font-semibold">{t("settings.style.fontScale")} ({fontScale.toFixed(2)})</h2>
        <input
          type="range"
          min="0.85"
          max="1.30"
          step="0.05"
          value={fontScale}
          onChange={(e) => setFontScaleBoth(Number(e.target.value))}
          className="w-full"
        />
      </Capsule>

      <Capsule className="flex flex-col gap-2">
        <h2 className="font-display text-sm font-semibold">{t("settings.style.density")}</h2>
        <div className="flex items-center gap-2">
          {(["comfortable", "compact"] as const).map((m) => (
            <Pill
              key={m}
              onClick={() => setDensityBoth(m)}
              variant={density === m ? "primary" : "glass"} size="sm"
            >
              {t(`settings.style.density.${m}`)}
            </Pill>
          ))}
        </div>
      </Capsule>

      <Capsule className="flex flex-col gap-2">
        <h2 className="font-display text-sm font-semibold">{t("settings.style.motion")}</h2>
        <div className="flex items-center gap-2">
          {(["subtle", "full", "none"] as const).map((m) => (
            <Pill
              key={m}
              onClick={() => setMotionBoth(m)}
              variant={motion === m ? "primary" : "glass"} size="sm"
            >
              {t(`settings.style.motion.${m}`)}
            </Pill>
          ))}
        </div>
      </Capsule>

      <Capsule className="flex flex-col gap-3">
        <h2 className="font-display text-sm font-semibold">{t("settings.style.perPageOverrides")}</h2>
        <div className="flex items-center gap-2">
          <span className="text-[12px] text-text-muted font-mono">{t("settings.style.pageLabel")}:</span>
          <select
            value={overridePage}
            onChange={(e) => setOverridePage(e.target.value)}
            className="bg-bg border border-border rounded px-2 h-7 text-[12px] font-mono"
          >
            {PAGES.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
          <Pill
            onClick={() => {
              setOverrideStore(overridePage, "theme", null);
              setOverrideStore(overridePage, "density", null);
              setOverrideStore(overridePage, "motion", null);
            }}
            disabled={!overrides[overridePage]}
            variant="ghost" size="sm"
          >
            {t("common.clear")}
          </Pill>
        </div>

        <div className="grid grid-cols-3 gap-2">
          {(["theme", "density", "motion"] as const).map((key) => {
            const v = overrides[overridePage]?.[key] as string | undefined;
            return (
              <label key={key} className="flex flex-col gap-1 text-[11px] font-mono">
                <span className="text-text-muted">{key}</span>
                <Input
                  value={v ?? ""}
                  onChange={(e) => {
                    const val = (e.target.value || null) as Parameters<typeof setOverrideStore>[2];
                    setOverrideStore(overridePage, key, val);
                  }}
                  placeholder={t("settings.style.overridePlaceholder", { key })}
                  className="h-8 text-[12px] font-mono"
                />
              </label>
            );
          })}
        </div>
      </Capsule>
    </div>
  );
}
