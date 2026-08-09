// SPDX-License-Identifier: MIT
import { useEffect, useState } from "react";
import { Network, Plus, ShieldCheck, X } from "lucide-react";
import { useWS } from "../../stores/ws";
import { useTranslation } from "react-i18next";
import { SandboxSecurityPanels } from "../workspace/SandboxSecurityPanels";

interface PermissionsConfig {
  mode?: "strict" | "normal" | "trust";
  tools?: Record<string, { mode?: string; risk?: string }>;
  path_rules?: Array<{ pattern: string; mode?: string }>;
}

interface ToolInfo {
  name: string;
  description: string;
  risk_level: string;
}

function getTools(config: Record<string, unknown> | null): NonNullable<PermissionsConfig["tools"]> {
  return (((config?.permissions ?? {}) as Record<string, unknown>).tools as PermissionsConfig["tools"]) ?? {};
}

function getRules(config: Record<string, unknown> | null): NonNullable<PermissionsConfig["path_rules"]> {
  return (((config?.permissions ?? {}) as Record<string, unknown>).path_rules as PermissionsConfig["path_rules"]) ?? [];
}

function getMode(config: Record<string, unknown> | null): string {
  return String(((config?.permissions ?? {}) as Record<string, unknown>).mode ?? "normal");
}

function getAt<T>(config: Record<string, unknown> | null, path: string, fallback: T): T {
  let current: unknown = config;
  for (const part of path.split(".")) {
    if (typeof current !== "object" || current === null || !(part in current)) return fallback;
    current = (current as Record<string, unknown>)[part];
  }
  return current as T;
}

export function PermissionsTab() {
  const { t } = useTranslation();
  const send = useWS((s) => s.send);
  const client = useWS((s) => s.client);
  const config = useWS((s) => s.config);
  const tools = getTools(config);
  const rules = getRules(config);
  const mode = getMode(config);
  const [newPattern, setNewPattern] = useState("");
  const [toolList, setToolList] = useState<ToolInfo[]>([]);

  useEffect(() => {
    send({ type: "tools.list" });
    return client?.on((msg) => {
      if (msg.type === "tools.list_result") {
        const incoming = (msg.tools as unknown as ToolInfo[]) ?? [];
        setToolList([...incoming].sort((a, b) => a.name.localeCompare(b.name)));
      }
    });
  }, [send, client]);

  function setMode(next: string) {
    send({ type: "permissions.patch", patch: { "permissions.mode": next } });
  }

  function setToolMode(name: string, value: string) {
    send({ type: "permissions.patch", patch: { [`permissions.tools.${name}.mode`]: value } });
  }

  function addRule() {
    const p = newPattern.trim();
    if (!p) return;
    const next = [...rules, { pattern: p, mode: "ask" }];
    send({ type: "permissions.patch", patch: { "permissions.path_rules": next } });
    setNewPattern("");
  }

  function removeRule(idx: number) {
    const next = rules.filter((_, i) => i !== idx);
    send({ type: "permissions.patch", patch: { "permissions.path_rules": next } });
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <h2 className="font-display text-sm font-semibold">{t("settings.permissions.globalMode")}</h2>
        <div className="flex items-center gap-2">
          {(["strict", "normal", "trust"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={`h-7 px-3 text-[12px] border rounded font-mono uppercase tracking-[0.05em] ${
                mode === m ? "bg-text text-bg border-border" : "border-border text-text-muted hover:bg-surface"
              }`}
            >
              {t(`settings.permissions.mode.${m}`)}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <h2 className="font-display text-sm font-semibold">{t("settings.permissions.toolOverrides")}</h2>
        <div className="border border-border rounded overflow-hidden">
          <table className="w-full text-[12px]">
            <thead className="bg-bg text-text-muted font-mono text-[10px] uppercase tracking-[0.1em]">
              <tr>
                <th className="text-left px-3 py-2">{t("settings.permissions.colTool")}</th>
                <th className="text-left px-3 py-2">{t("settings.permissions.colRisk")}</th>
                <th className="text-left px-3 py-2">{t("settings.permissions.colMode")}</th>
              </tr>
            </thead>
            <tbody>
              {toolList.length === 0 ? (
                <tr>
                  <td colSpan={3} className="px-3 py-3 text-text-muted text-center">
                    {t("settings.permissions.loadingTools")}
                  </td>
                </tr>
              ) : (
                toolList.map((t) => {
                  const override = tools[t.name] || {};
                  return (
                    <tr key={t.name} className="border-t border-border">
                      <td className="px-3 py-2 font-mono">
                        <div>#{t.name}</div>
                        <div className="text-[10px] text-text-muted font-sans">{t.description}</div>
                      </td>
                      <td className="px-3 py-2 font-mono text-[11px] text-text-muted">
                        {t.risk_level}
                      </td>
                      <td className="px-3 py-2">
                        <select
                          value={override.mode || "ask"}
                          onChange={(e) => setToolMode(t.name, e.target.value)}
                          className="bg-bg border border-border rounded px-2 h-7 text-[12px] font-mono"
                        >
                          <option value="ask">ask</option>
                          <option value="trust">trust</option>
                          <option value="deny">deny</option>
                        </select>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <h2 className="font-display text-sm font-semibold">{t("settings.permissions.pathRules")}</h2>
        <div className="flex items-center gap-2">
          <input
            value={newPattern}
            onChange={(e) => setNewPattern(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addRule()}
            placeholder={t("settings.permissions.pathPlaceholder")}
            className="flex-1 bg-bg border border-border rounded px-2 h-7 text-[12px] font-mono"
          />
          <button
            onClick={addRule}
            disabled={!newPattern.trim()}
            className="flex items-center gap-1 h-7 px-2 border border-border rounded text-[12px] hover:bg-surface disabled:opacity-50"
          >
            <Plus size={12} strokeWidth={1.5} /> {t("common.add")}
          </button>
        </div>
        {rules.length === 0 ? (
          <p className="text-[12px] text-text-muted">{t("settings.permissions.noPathRules")}</p>
        ) : (
          <ul className="border border-border rounded overflow-hidden">
            {rules.map((r, i) => (
              <li
                key={`${r.pattern}-${i}`}
                className="px-3 py-2 text-[12px] flex items-center justify-between border-b border-border last:border-b-0"
              >
                <code className="font-mono">{r.pattern}</code>
                <button
                  onClick={() => removeRule(i)}
                  className="text-text-muted hover:text-warning"
                  title={t("common.delete")}
                >
                  <X size={12} strokeWidth={1.5} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      <SandboxSecurityPanels />
      <SecurityControls config={config} send={send} />
    </div>
  );
}

interface SecurityControlsProps {
  config: Record<string, unknown> | null;
  send: ReturnType<typeof useWS.getState>["send"];
}

const SECURITY_TOGGLES = [
  ["security.skills.review_required", "requireReviewedSkills", "requireReviewedSkillsDesc", true],
  ["security.skills.subprocess_env.enabled", "isolateSkillEnv", "isolateSkillEnvDesc", true],
  ["security.skills.llm_review.enabled", "llmSkillReview", "llmSkillReviewDesc", false],
  ["security.mcp.review_required", "requireReviewedMcp", "requireReviewedMcpDesc", true],
  ["security.mcp.cwd_pinning.enabled", "pinMcpCwd", "pinMcpCwdDesc", true],
  ["security.egress.enabled", "filterOutbound", "filterOutboundDesc", false],
  ["security.redaction.enabled", "redactApiKeys", "redactApiKeysDesc", true],
  ["security.memory.write_sanitization.enabled", "sanitizeMemory", "sanitizeMemoryDesc", true],
  ["security.file_read_blacklist.enabled", "blockSensitiveReads", "blockSensitiveReadsDesc", true],
  ["security.session.no_trust_mode", "disableSessionTrust", "disableSessionTrustDesc", false],
  ["security.small_agent_review.enabled", "reviewToolResults", "reviewToolResultsDesc", false],
] as const;

function SecurityControls({ config, send }: SecurityControlsProps) {
  const { t } = useTranslation();
  const patch = (path: string, value: unknown) => {
    send({ type: "permissions.patch", patch: { [path]: value } });
  };
  const list = (path: string) => getAt<unknown[]>(config, path, []).filter((item): item is string => typeof item === "string");

  return (
    <section className="flex flex-col gap-4 border-t border-border pt-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="flex items-center gap-2 font-display text-sm font-semibold">
            <ShieldCheck size={14} strokeWidth={1.5} /> {t("settings.permissions.executionPerimeter")}
          </h2>
          <p className="mt-1 max-w-[620px] text-[11px] leading-relaxed text-text-muted">
            {t("settings.permissions.executionPerimeterDesc")}
          </p>
        </div>
        <span className="rounded border border-success/40 bg-success/10 px-2 py-1 font-mono text-[9px] uppercase tracking-[0.12em] text-success">
          {t("settings.permissions.wsAuthAlwaysOn")}
        </span>
      </div>

      <div className="grid gap-2 lg:grid-cols-2">
        {SECURITY_TOGGLES.map(([path, labelKey, descKey, fallback]) => (
          <SecurityToggle
            key={path}
            label={t(`settings.permissions.toggles.${labelKey}`)}
            description={t(`settings.permissions.toggles.${descKey}`)}
            checked={getAt<boolean>(config, path, fallback)}
            onChange={(value) => patch(path, value)}
          />
        ))}
      </div>

      <div className="flex items-center justify-between rounded-lg border border-border bg-bg px-3 py-2.5">
        <div className="flex items-center gap-2">
          <Network size={13} strokeWidth={1.5} className="text-text-muted" />
          <div>
            <div className="text-[12px] font-medium">{t("settings.permissions.egressMode")}</div>
            <div className="text-[10px] text-text-muted">{t("settings.permissions.egressModeDesc")}</div>
          </div>
        </div>
        <div className="flex rounded border border-border p-0.5 font-mono text-[10px] uppercase">
          {(["deny", "warn"] as const).map((mode) => (
            <button
              key={mode}
              type="button"
              onClick={() => patch("security.egress.mode", mode)}
              className={`rounded px-2.5 py-1 ${getAt(config, "security.egress.mode", "deny") === mode ? "bg-text text-bg" : "text-text-muted hover:text-text"}`}
            >
              {mode}
            </button>
          ))}
        </div>
      </div>

      <div className="grid gap-3 xl:grid-cols-2">
        <div className="rounded-xl border border-border bg-bg p-3">
          <div className="mb-3 font-mono text-[9px] uppercase tracking-[0.14em] text-text-muted">{t("settings.permissions.networkRules")}</div>
          <div className="grid gap-3 sm:grid-cols-2">
            <ListEditor label={t("settings.permissions.allowlist")} path="security.egress.allowlist" values={list("security.egress.allowlist")} placeholder="api.openai.com:443" onChange={patch} />
            <ListEditor label={t("settings.permissions.blocklist")} path="security.egress.blocklist" values={list("security.egress.blocklist")} placeholder="*.example.com" onChange={patch} />
          </div>
        </div>
        <ListPanel title={t("settings.permissions.resultRedaction")} description={t("settings.permissions.resultRedactionDesc")}>
          <ListEditor label={t("settings.permissions.customRegex")} path="security.redaction.patterns" values={list("security.redaction.patterns")} placeholder="token-[A-Za-z0-9]+" onChange={patch} />
        </ListPanel>
        <ListPanel title={t("settings.permissions.memorySanitization")} description={t("settings.permissions.memorySanitizationDesc")}>
          <ListEditor label={t("settings.permissions.customRegex")} path="security.memory.write_sanitization.custom_patterns" values={list("security.memory.write_sanitization.custom_patterns")} placeholder="override policy" onChange={patch} />
        </ListPanel>
        <ListPanel title={t("settings.permissions.fileReadBlacklist")} description={t("settings.permissions.fileReadBlacklistDesc")}>
          <ListEditor label={t("settings.permissions.customGlob")} path="security.file_read_blacklist.extra_patterns" values={list("security.file_read_blacklist.extra_patterns")} placeholder="~/work/private/**" onChange={patch} />
        </ListPanel>
      </div>
    </section>
  );
}

function SecurityToggle({ label, description, checked, onChange }: { label: string; description: string; checked: boolean; onChange: (value: boolean) => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="group flex min-h-[62px] items-center justify-between gap-4 rounded-lg border border-border bg-bg px-3 py-2.5 text-left transition-colors hover:bg-surface"
    >
      <span>
        <span className="block text-[12px] font-medium">{label}</span>
        <span className="mt-0.5 block text-[10px] leading-relaxed text-text-muted">{description}</span>
      </span>
      <span className={`relative h-4 w-8 shrink-0 rounded-full border transition-colors ${checked ? "border-success/60 bg-success/25" : "border-border bg-surface"}`}>
        <span className={`absolute top-0.5 h-2.5 w-2.5 rounded-full transition-transform ${checked ? "translate-x-[17px] bg-success" : "translate-x-0.5 bg-text-muted"}`} />
      </span>
    </button>
  );
}

function ListPanel({ title, description, children }: { title: string; description: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-border bg-bg p-3">
      <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-text-muted">{title}</div>
      <p className="mb-3 mt-1 text-[10px] text-text-muted">{description}</p>
      {children}
    </div>
  );
}

function ListEditor({ label, path, values, placeholder, onChange }: { label: string; path: string; values: string[]; placeholder: string; onChange: (path: string, value: unknown) => void }) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState("");
  const add = () => {
    const value = draft.trim();
    if (!value || values.includes(value)) return;
    onChange(path, [...values, value]);
    setDraft("");
  };

  return (
    <div className="flex flex-col gap-2">
      <label className="font-mono text-[10px] text-text-muted">{label}</label>
      <div className="flex gap-1.5">
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => event.key === "Enter" && add()}
          placeholder={placeholder}
          className="h-7 min-w-0 flex-1 rounded border border-border bg-surface px-2 font-mono text-[10px] outline-none focus:border-text-muted"
        />
        <button type="button" onClick={add} disabled={!draft.trim()} className="flex h-7 w-7 items-center justify-center rounded border border-border hover:bg-surface disabled:opacity-40" aria-label={`Add ${label}`}>
          <Plus size={12} strokeWidth={1.5} />
        </button>
      </div>
      <div className="flex min-h-7 flex-wrap gap-1.5">
        {values.length === 0 ? <span className="py-1 text-[10px] text-text-muted">{t("settings.permissions.noCustomRules")}</span> : values.map((value, index) => (
          <span key={`${value}-${index}`} className="flex max-w-full items-center gap-1 rounded border border-border bg-surface px-1.5 py-1 font-mono text-[9px]">
            <span className="truncate">{value}</span>
            <button type="button" onClick={() => onChange(path, values.filter((_, itemIndex) => itemIndex !== index))} className="text-text-muted hover:text-warning" aria-label={`Remove ${value}`}>
              <X size={10} strokeWidth={1.5} />
            </button>
          </span>
        ))}
      </div>
    </div>
  );
}
