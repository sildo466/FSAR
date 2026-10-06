import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useWS } from "../../stores/ws";

function getAt<T>(config: Record<string, unknown> | null, path: string, fallback: T): T {
  const parts = path.split(".");
  let cur: unknown = config;
  for (const part of parts) {
    if (cur === null || typeof cur !== "object") return fallback;
    cur = (cur as Record<string, unknown>)[part];
  }
  return (cur === undefined || cur === null ? fallback : cur) as T;
}

const FIELDS = [
  { key: "memory.inject_budget_chars", labelKey: "settings.memory.injectBudget", fallback: 2400 },
  { key: "memory.inject_candidate_cap", labelKey: "settings.memory.injectCap", fallback: 40 },
  { key: "memory.inject_score_floor", labelKey: "settings.memory.injectFloor", fallback: 0.35 },
  { key: "memory.inject_max_item_chars", labelKey: "settings.memory.injectMaxItem", fallback: 600 },
] as const;

export function InjectionSection() {
  const { t } = useTranslation();
  const send = useWS((s) => s.send);
  const config = useWS((s) => s.config);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setDraft(
      Object.fromEntries(
        FIELDS.map((f) => [f.key, String(getAt(config, f.key, f.fallback))]),
      ),
    );
  }, [config]);

  function save() {
    const patch: Record<string, unknown> = {};
    for (const f of FIELDS) {
      const value = Number(draft[f.key]);
      if (Number.isFinite(value)) patch[f.key] = value;
    }
    send({ type: "settings.patch", patch });
    setSaved(true);
    window.setTimeout(() => setSaved(false), 2000);
  }

  return (
    <div className="pt-6 border-t border-border">
      <h3 className="font-display text-sm font-semibold">{t("settings.memory.injectTitle")}</h3>
      <p className="mt-1 max-w-[620px] text-[11px] leading-relaxed text-text-muted">
        {t("settings.memory.injectDesc")}
      </p>
      <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
        {FIELDS.map((f) => (
          <label key={f.key} className="flex items-center justify-between gap-3">
            <span className="text-[12px]">{t(f.labelKey)}</span>
            <input
              inputMode="decimal"
              value={draft[f.key] ?? ""}
              onChange={(e) => setDraft((d) => ({ ...d, [f.key]: e.target.value }))}
              className="w-28 rounded-lg border border-border bg-bg/30 px-3 py-1.5 text-[12px]"
            />
          </label>
        ))}
      </div>
      <div className="mt-3 flex items-center gap-3">
        <button onClick={save} className="rounded-full bg-[var(--button-bg)] text-[var(--button-text)] button-tex px-4 py-1.5 text-[12px]">
          {t("settings.memory.injectSave")}
        </button>
        {saved && <span className="text-[12px] text-text-muted">{t("settings.memory.injectSaved")}</span>}
      </div>
    </div>
  );
}
