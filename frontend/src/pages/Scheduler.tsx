// SPDX-License-Identifier: MIT
import { useEffect, useState } from "react";
import { Plus, Play, Trash2, Pencil, Power, PowerOff, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";

interface Job {
  id: number;
  name: string;
  description: string;
  enabled: boolean;
  schedule_kind: "cron" | "interval" | "at" | "startup";
  schedule_expr: string;
  job_kind: "system" | "agent";
  prompt: string;
  tools_allow: string[];
  timeout_seconds: number;
  delivery_mode: "db_only" | "social";
  delivery_target: string;
  last_run_at: string | null;
  last_status: "ok" | "error" | "skipped" | "missed" | null;
  last_error: string;
  consecutive_errors: number;
}

interface Run {
  id: number;
  job_id: number;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  result_text: string;
  error: string;
  delivery_status: string;
}

type Tab = "jobs" | "runs" | "system";

const FIELD_LABEL = "font-mono text-[10px] uppercase tracking-[0.14em] text-text-muted";
const FIELD_INPUT =
  "mt-1 w-full bg-[var(--input-bg)] px-3 py-2 text-sm text-text outline-none placeholder:text-text-faint";
const PANEL = "glass rounded-[24px] p-5";
const TABLE_HEAD =
  "border-b border-[var(--border)] bg-[var(--chip-bg)] text-left text-text-muted";
const BTN_GHOST =
  "glass flex items-center gap-2 rounded-full px-4 py-1.5 text-sm text-text-muted transition hover:text-text";

const EMPTY_DRAFT = {
  name: "",
  description: "",
  schedule_kind: "cron",
  schedule_expr: "0 9 * * *",
  prompt: "",
  timeout_seconds: 60,
  delivery_mode: "db_only",
  delivery_target: "",
};

export function Scheduler() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<Tab>("jobs");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [systemJobs, setSystemJobs] = useState<Job[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [handlers, setHandlers] = useState<string[]>([]);
  const [showNew, setShowNew] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [draft, setDraft] = useState(EMPTY_DRAFT);
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => {
    try {
      const [jr, sr, ru, hr] = await Promise.all([
        fetch("/api/scheduler/jobs").then((r) => r.json()),
        fetch("/api/scheduler/system-jobs").then((r) => r.json()),
        fetch("/api/scheduler/runs?limit=50").then((r) => r.json()),
        fetch("/api/scheduler/handlers").then((r) => r.json()),
      ]);
      setJobs((jr.jobs || []).filter((j: Job) => j.job_kind === "agent"));
      setSystemJobs(sr.jobs || []);
      setRuns(ru.runs || []);
      setHandlers(hr.handlers || []);
    } catch (e) {
      setError(String(e));
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const submit = async () => {
    setError(null);
    const body = JSON.stringify({
      name: draft.name,
      description: draft.description,
      schedule_kind: draft.schedule_kind,
      schedule_expr: draft.schedule_expr,
      prompt: draft.prompt,
      timeout_seconds: draft.timeout_seconds,
      delivery_mode: draft.delivery_mode,
      delivery_target: draft.delivery_target,
    });
    try {
      const r = await fetch(
        editingId !== null ? `/api/scheduler/jobs/${editingId}` : "/api/scheduler/jobs",
        {
          method: editingId !== null ? "PATCH" : "POST",
          headers: { "Content-Type": "application/json" },
          body,
        },
      );
      if (!r.ok) {
        const e = await r.json();
        setError(e.detail || `HTTP ${r.status}`);
        return;
      }
      setShowNew(false);
      setEditingId(null);
      setDraft(EMPTY_DRAFT);
      refresh();
    } catch (e) {
      setError(String(e));
    }
  };

  const startEdit = (j: Job) => {
    setDraft({
      name: j.name,
      description: j.description,
      schedule_kind: j.schedule_kind,
      schedule_expr: j.schedule_expr,
      prompt: j.prompt,
      timeout_seconds: j.timeout_seconds,
      delivery_mode: j.delivery_mode,
      delivery_target: j.delivery_target,
    });
    setEditingId(j.id);
    setShowNew(true);
    setError(null);
  };

  const closeForm = () => {
    setShowNew(false);
    setEditingId(null);
    setDraft(EMPTY_DRAFT);
    setError(null);
  };

  const startCreate = () => {
    setEditingId(null);
    setDraft(EMPTY_DRAFT);
    setShowNew(true);
    setError(null);
  };

  const toggle = async (j: Job) => {
    await fetch(`/api/scheduler/jobs/${j.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: !j.enabled }),
    });
    refresh();
  };

  const runNow = async (j: Job) => {
    await fetch(`/api/scheduler/jobs/${j.id}/run`, { method: "POST" });
    refresh();
  };

  const remove = async (j: Job) => {
    if (!confirm(t("scheduler.delete.confirm", { name: j.name }))) return;
    await fetch(`/api/scheduler/jobs/${j.id}`, { method: "DELETE" });
    refresh();
  };

  const toggleSystem = async (j: Job) => {
    await fetch(`/api/scheduler/system-jobs/${j.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: !j.enabled }),
    });
    refresh();
  };

  const schedulePlaceholder = () => {
    switch (draft.schedule_kind) {
      case "cron": return t("scheduler.field.schedule.cron.placeholder");
      case "interval": return t("scheduler.field.schedule.interval.placeholder");
      case "at": return t("scheduler.field.schedule.at.placeholder");
      default: return "";
    }
  };

  return (
    <div className="mx-auto flex h-full max-w-[1100px] flex-col gap-6 p-8">
      <div className="flex items-center justify-between">
        <header>
          <h1 className="font-display text-2xl font-semibold tracking-[-0.01em]">{t("nav.scheduler")}</h1>
          <p className="text-text-muted">{t("scheduler.subtitle")}</p>
        </header>
        <button onClick={refresh} className={BTN_GHOST}>
          <RefreshCw className="h-4 w-4" /> {t("scheduler.refresh")}
        </button>
      </div>

      <div className="flex gap-2 border-b border-[var(--border)]">
        {(["jobs", "runs", "system"] as Tab[]).map((tk) => (
          <button
            key={tk}
            onClick={() => setTab(tk)}
            className={`border-b-2 px-4 py-2 text-sm transition ${
              tab === tk
                ? "border-[var(--text)] text-text"
                : "border-transparent text-text-muted hover:text-text"
            }`}
          >
            {tk === "jobs" ? t("scheduler.tab.jobs") : tk === "runs" ? t("scheduler.tab.runs") : t("scheduler.tab.system")}
          </button>
        ))}
      </div>

      {error && (
        <div className="rounded-2xl border border-[var(--danger)]/30 bg-[var(--danger)]/10 p-3 text-sm text-[var(--danger)]">
          {error}
        </div>
      )}

      {tab === "jobs" && (
        <div className="flex flex-col gap-4">
          <div className="flex justify-end">
            <button
              onClick={() => (showNew ? closeForm() : startCreate())}
              className="flex items-center gap-2 rounded-full bg-text px-4 py-2 text-sm font-medium text-bg shadow-[0_8px_24px_var(--glow-faint)] transition hover:scale-[1.02]"
            >
              <Plus className="h-4 w-4" /> {t("scheduler.new")}
            </button>
          </div>

          {showNew && (
            <div className={PANEL}>
              <h3 className="mb-4 font-display text-lg font-semibold">
                {editingId !== null ? t("scheduler.edit") : t("scheduler.create")}
              </h3>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <label className={FIELD_LABEL}>
                  {t("scheduler.label.name")}
                  <input
                    className={FIELD_INPUT}
                    placeholder={t("scheduler.field.name")}
                    value={draft.name}
                    onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                  />
                </label>
                <label className={FIELD_LABEL}>
                  {t("scheduler.label.description")}
                  <input
                    className={FIELD_INPUT}
                    placeholder={t("scheduler.field.name.short")}
                    value={draft.description}
                    onChange={(e) => setDraft({ ...draft, description: e.target.value })}
                  />
                </label>
                <label className={FIELD_LABEL}>
                  {t("scheduler.label.scheduleKind")}
                  <select
                    className={FIELD_INPUT}
                    value={draft.schedule_kind}
                    onChange={(e) =>
                      setDraft({ ...draft, schedule_kind: e.target.value as Job["schedule_kind"] })
                    }
                  >
                    <option value="cron">{t("scheduler.field.schedule_kind.cron")}</option>
                    <option value="interval">{t("scheduler.field.schedule_kind.interval")}</option>
                    <option value="at">{t("scheduler.field.schedule_kind.at")}</option>
                    <option value="startup">{t("scheduler.field.schedule_kind.startup")}</option>
                  </select>
                </label>
                <label className={FIELD_LABEL}>
                  {t("scheduler.label.scheduleExpr")}
                  <input
                    className={`${FIELD_INPUT} font-mono`}
                    placeholder={schedulePlaceholder()}
                    value={draft.schedule_expr}
                    onChange={(e) => setDraft({ ...draft, schedule_expr: e.target.value })}
                  />
                </label>
                <label className={`col-span-2 ${FIELD_LABEL}`}>
                  {t("scheduler.label.prompt")}
                  <textarea
                    className={`${FIELD_INPUT} resize-y`}
                    placeholder={t("scheduler.field.prompt")}
                    rows={3}
                    value={draft.prompt}
                    onChange={(e) => setDraft({ ...draft, prompt: e.target.value })}
                  />
                </label>
                <label className={FIELD_LABEL}>
                  {t("scheduler.label.deliveryMode")}
                  <select
                    className={FIELD_INPUT}
                    value={draft.delivery_mode}
                    onChange={(e) =>
                      setDraft({
                        ...draft,
                        delivery_mode: e.target.value as Job["delivery_mode"],
                      })
                    }
                  >
                    <option value="db_only">{t("scheduler.field.delivery.db_only")}</option>
                    <option value="social">{t("scheduler.field.delivery.social")}</option>
                  </select>
                </label>
                {draft.delivery_mode === "social" ? (
                  <label className={FIELD_LABEL}>
                    {t("scheduler.label.deliveryTarget")}
                    <input
                      className={`${FIELD_INPUT} font-mono`}
                      placeholder={t("scheduler.field.delivery.target")}
                      value={draft.delivery_target}
                      onChange={(e) =>
                        setDraft({ ...draft, delivery_target: e.target.value })
                      }
                    />
                    <span className="mt-1 block normal-case tracking-normal text-text-faint">
                      {t("scheduler.hint.deliveryTarget")}
                    </span>
                  </label>
                ) : (
                  <div />
                )}
                <label className={FIELD_LABEL}>
                  {t("scheduler.label.timeout")}
                  <input
                    type="number"
                    min={1}
                    className={FIELD_INPUT}
                    value={draft.timeout_seconds}
                    onChange={(e) =>
                      setDraft({ ...draft, timeout_seconds: Number(e.target.value) })
                    }
                  />
                </label>
              </div>
              <div className="mt-4 flex gap-2">
                <button
                  onClick={submit}
                  className="rounded-full bg-text px-5 py-1.5 text-sm font-medium text-bg transition hover:scale-[1.02]"
                >
                  {editingId !== null ? t("scheduler.edit.btn") : t("scheduler.create.btn")}
                </button>
                <button onClick={closeForm} className={BTN_GHOST}>
                  {t("scheduler.cancel")}
                </button>
              </div>
            </div>
          )}

          <div className="glass overflow-hidden rounded-[24px]">
            <table className="w-full text-sm">
              <thead className={TABLE_HEAD}>
                <tr>
                  <th className="p-3">{t("scheduler.col.name")}</th>
                  <th className="p-3">{t("scheduler.col.schedule")}</th>
                  <th className="p-3">{t("scheduler.col.last_run")}</th>
                  <th className="p-3">{t("scheduler.col.status")}</th>
                  <th className="p-3">{t("scheduler.col.actions")}</th>
                </tr>
              </thead>
              <tbody>
                {jobs.length === 0 && (
                  <tr>
                    <td colSpan={5} className="p-6 text-center text-text-faint">
                      {t("scheduler.empty.jobs")}
                    </td>
                  </tr>
                )}
                {jobs.map((j) => (
                  <tr key={j.id} className="border-b border-[var(--border)] last:border-b-0">
                    <td className="p-3">
                      <div className="font-medium">{j.name}</div>
                      <div className="text-xs text-text-muted">
                        {j.description || <em>{t("scheduler.node.desc.empty")}</em>}
                      </div>
                    </td>
                    <td className="p-3 font-mono text-xs text-text-muted">
                      {j.schedule_kind}: {j.schedule_expr}
                    </td>
                    <td className="p-3 text-xs">
                      {j.last_run_at
                        ? new Date(j.last_run_at).toLocaleString()
                        : "—"}
                    </td>
                    <td className="p-3">
                      {j.enabled ? (
                        <span className="rounded-full bg-[var(--success)]/10 px-2 py-0.5 text-xs text-[var(--success)]">
                          {j.last_status || t("scheduler.status.armed")}
                        </span>
                      ) : (
                        <span className="rounded-full bg-[var(--chip-bg)] px-2 py-0.5 text-xs text-text-muted">
                          {t("scheduler.status.disabled")}
                        </span>
                      )}
                      {j.consecutive_errors > 0 && (
                        <div className="mt-1 text-xs text-[var(--danger)]">
                          {t("scheduler.errors.count", { n: j.consecutive_errors })}
                        </div>
                      )}
                    </td>
                    <td className="p-3">
                      <div className="flex gap-1">
                        <button
                          onClick={() => runNow(j)}
                          className="rounded-full p-1.5 text-text-muted transition hover:bg-glass hover:text-text"
                          title={t("scheduler.action.run_now")}
                        >
                          <Play className="h-4 w-4" />
                        </button>
                        <button
                          onClick={() => startEdit(j)}
                          className="rounded-full p-1.5 text-text-muted transition hover:bg-glass hover:text-text"
                          title={t("scheduler.action.edit")}
                        >
                          <Pencil className="h-4 w-4" />
                        </button>
                        <button
                          onClick={() => toggle(j)}
                          className="rounded-full p-1.5 text-text-muted transition hover:bg-glass hover:text-text"
                          title={j.enabled ? t("scheduler.action.disable") : t("scheduler.action.enable")}
                        >
                          {j.enabled ? (
                            <PowerOff className="h-4 w-4" />
                          ) : (
                            <Power className="h-4 w-4" />
                          )}
                        </button>
                        <button
                          onClick={() => remove(j)}
                          className="rounded-full p-1.5 text-[var(--danger)] transition hover:bg-[var(--danger)]/10"
                          title={t("scheduler.action.delete")}
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === "runs" && (
        <div className="glass overflow-hidden rounded-[24px]">
          <table className="w-full text-sm">
            <thead className={TABLE_HEAD}>
              <tr>
                <th className="p-3">{t("scheduler.col.job")}</th>
                <th className="p-3">{t("scheduler.col.started")}</th>
                <th className="p-3">{t("scheduler.col.duration")}</th>
                <th className="p-3">{t("scheduler.col.status")}</th>
                <th className="p-3">{t("scheduler.col.delivery")}</th>
              </tr>
            </thead>
            <tbody>
              {runs.length === 0 && (
                <tr>
                  <td colSpan={5} className="p-6 text-center text-text-faint">
                    {t("scheduler.empty.runs")}
                  </td>
                </tr>
              )}
              {runs.map((r) => {
                const job = [...jobs, ...systemJobs].find((j) => j.id === r.job_id);
                return (
                  <tr key={r.id} className="border-b border-[var(--border)] last:border-b-0">
                    <td className="p-3">
                      {job?.name || `job#${r.job_id}`}
                    </td>
                    <td className="p-3 text-xs">
                      {r.started_at
                        ? new Date(r.started_at).toLocaleString()
                        : "—"}
                    </td>
                    <td className="p-3 text-xs">
                      {r.duration_ms != null ? `${r.duration_ms}ms` : "—"}
                    </td>
                    <td className="p-3">
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs ${
                          r.status === "ok"
                            ? "bg-[var(--success)]/10 text-[var(--success)]"
                            : r.status === "error"
                              ? "bg-[var(--danger)]/10 text-[var(--danger)]"
                              : "bg-[var(--chip-bg)] text-text-muted"
                        }`}
                      >
                        {r.status}
                      </span>
                    </td>
                    <td className="p-3 text-xs">
                      {r.delivery_status || "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {tab === "system" && (
        <div className="flex flex-col gap-3">
          <p className="text-sm text-text-muted">{t("scheduler.system.desc")}</p>
          <div className="glass overflow-hidden rounded-[24px]">
            <table className="w-full text-sm">
              <thead className={TABLE_HEAD}>
                <tr>
                  <th className="p-3">{t("scheduler.col.name")}</th>
                  <th className="p-3">{t("scheduler.col.schedule")}</th>
                  <th className="p-3">{t("scheduler.col.last_status")}</th>
                  <th className="p-3">{t("scheduler.col.enabled")}</th>
                </tr>
              </thead>
              <tbody>
                {systemJobs.map((j) => (
                  <tr key={j.id} className="border-b border-[var(--border)] last:border-b-0">
                    <td className="p-3 font-medium">{j.name}</td>
                    <td className="p-3 font-mono text-xs text-text-muted">
                      {j.schedule_kind}: {j.schedule_expr}
                    </td>
                    <td className="p-3">
                      {j.last_status || (
                        <span className="text-text-faint">{t("scheduler.status.never")}</span>
                      )}
                    </td>
                    <td className="p-3">
                      <button
                        onClick={() => toggleSystem(j)}
                        className={`rounded-full px-3 py-1 text-xs transition ${
                          j.enabled
                            ? "bg-[var(--success)]/10 text-[var(--success)]"
                            : "bg-[var(--chip-bg)] text-text-muted"
                        }`}
                      >
                        {j.enabled ? t("scheduler.toggle.on") : t("scheduler.toggle.off")}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="text-xs text-text-faint">
            {t("scheduler.handlers.available", { list: handlers.join(", ") || "(none)" })}
          </div>
        </div>
      )}
    </div>
  );
}
