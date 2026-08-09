// SPDX-License-Identifier: MIT
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { ChevronRight, Plus, RotateCcw, ShieldAlert, X } from "lucide-react";
import { useWorkspace } from "../../stores/workspace";
import { useWS } from "../../stores/ws";

export function SandboxSecurityPanels() {
  const { t } = useTranslation();
  const send = useWS((state) => state.send);
  const config = useWS((state) => state.config);
  const hardline = useWorkspace((state) => state.hardlineClasses);
  const sensitive = useWorkspace((state) => state.sensitiveClasses);
  const custom = useWorkspace((state) => state.customSensitive);
  const workspaces = useWorkspace((state) => state.workspaces);
  const events = useWorkspace((state) => state.auditEvents);
  const defaultId = useWorkspace((state) => state.defaultId);
  const [pattern, setPattern] = useState("");
  const security = (config?.security ?? {}) as { power_user_mode?: boolean };

  useEffect(() => {
    send({ type: "hardline.list_classes" });
    send({ type: "sensitive.list" });
    send({ type: "workspace.list" });
    send({ type: "sandbox_audit.list", since: new Date(Date.now() - 86400000).toISOString(), limit: 20 });
  }, [send]);

  function toggleClass(id: string, enabled: boolean) {
    const disabled = hardline.filter((item) => !item.enabled).map((item) => item.id);
    send({ type: "hardline.set_disabled", classes: enabled ? Array.from(new Set([...disabled, id])) : disabled.filter((item) => item !== id) });
  }
  function addPattern() {
    const value = pattern.trim();
    if (!value || value === "**") return;
    send({ type: "sensitive.add_custom", pattern: value });
    setPattern("");
  }

  return (
    <>
      <section className="flex flex-col gap-3 border-t border-border pt-6">
        <div className="flex items-center justify-between"><div><h2 className="font-display text-sm font-semibold">{t("sandbox.hardline")}</h2><p className="text-[11px] text-text-muted">{t("sandbox.hardlineDesc")}</p></div><button onClick={() => send({ type: "hardline.restore_all" })} className="flex items-center gap-1 text-[11px] text-text-muted hover:text-text"><RotateCcw size={12} /> {t("sandbox.restoreAll")}</button></div>
        <div className="rounded-xl border border-warning/25 bg-warning/5 px-3 py-2 text-[11px] text-warning"><ShieldAlert size={13} className="mr-2 inline" />{t("sandbox.warning")}</div>
        <div className="grid gap-2 sm:grid-cols-2">
          {hardline.map((item) => <label key={item.id} className="flex cursor-pointer items-center justify-between rounded-xl border border-border px-3 py-2 hover:bg-surface"><span className="min-w-0"><span className="block text-[12px] font-medium">{item.id}. {item.label}</span><span className="font-mono text-[9px] text-text-muted">{t("sandbox.patternsCount", { count: item.pattern_count })}</span></span><input type="checkbox" checked={item.enabled} onChange={(event) => toggleClass(item.id, !event.target.checked)} className="accent-current" /></label>)}
        </div>
      </section>
      <section className="flex flex-col gap-3 border-t border-border pt-6">
        <h2 className="font-display text-sm font-semibold">{t("sandbox.sensitive")}</h2>
        <div className="grid grid-cols-2 gap-2">{sensitive.map((item) => <div key={item.id} className="rounded-xl border border-border px-3 py-2"><p className="text-[12px] font-medium">{item.id}. {item.label}</p><p className="font-mono text-[9px] text-text-muted">{t("sandbox.rulesCount", { count: item.pattern_count })} · {t("sandbox.alwaysConfirm")}</p></div>)}</div>
        <div className="flex gap-2"><input value={pattern} onChange={(event) => setPattern(event.target.value)} onKeyDown={(event) => event.key === "Enter" && addPattern()} placeholder={t("sandbox.patternPlaceholder")} className="h-8 flex-1 bg-bg px-3 font-mono text-[11px]" /><button onClick={addPattern} className="flex items-center gap-1 rounded-full border border-border px-3 text-[11px]"><Plus size={12} /> {t("common.add")}</button></div>
        {custom.length > 0 && <div className="flex flex-wrap gap-2">{custom.map((item) => <span key={item} className="flex items-center gap-2 rounded-full bg-bg px-3 py-1.5 font-mono text-[10px]">{item}<button onClick={() => send({ type: "sensitive.remove_custom", pattern: item })}><X size={11} /></button></span>)}</div>}
      </section>
      <section className="flex flex-col gap-3 border-t border-border pt-6">
        <div className="flex items-center justify-between"><h2 className="font-display text-sm font-semibold">{t("sandbox.workspaces")}</h2><Link to="/settings/workspace" className="flex items-center text-[11px] text-text-muted hover:text-text">{t("sandbox.manage")} <ChevronRight size={12} /></Link></div>
        <div className="divide-y divide-border overflow-hidden rounded-xl border border-border">{workspaces.map((item) => <div key={item.id} className="flex items-center justify-between px-3 py-2"><span><span className="block text-[12px] font-medium">{item.name}</span><span className="block max-w-[430px] truncate font-mono text-[9px] text-text-muted">{item.root_path}</span></span>{item.id === defaultId && <span className="font-mono text-[9px] uppercase text-success">default</span>}</div>)}</div>
        <label className="flex items-center justify-between rounded-xl border border-border px-3 py-2"><span><span className="block text-[12px] font-medium">{t("sandbox.powerUser")}</span><span className="text-[10px] text-text-muted">{t("sandbox.powerUserDesc")}</span></span><input type="checkbox" checked={security.power_user_mode === true} onChange={(event) => send({ type: "permissions.patch", patch: { "security.power_user_mode": event.target.checked } })} /></label>
      </section>
      <section className="flex flex-col gap-3 border-t border-border pt-6">
        <h2 className="font-display text-sm font-semibold">{t("sandbox.recent")}</h2>
        {events.length === 0 ? <p className="text-[12px] text-text-muted">{t("sandbox.noEvents")}</p> : <div className="max-h-64 divide-y divide-border overflow-auto rounded-xl border border-border">{events.map((event) => <div key={event.id} className="grid grid-cols-[100px_1fr] gap-3 px-3 py-2"><span className={`font-mono text-[9px] uppercase ${event.verdict.includes("blocked") || event.verdict === "denied" ? "text-danger" : "text-success"}`}>{event.verdict}</span><span className="min-w-0"><span className="block truncate font-mono text-[10px]">{event.tool} · {event.target_path || event.command || event.operation}</span><span className="block truncate text-[10px] text-text-muted">{event.reason}</span></span></div>)}</div>}
      </section>
    </>
  );
}
