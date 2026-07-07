// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { Plus, X } from "lucide-react";
import { useWS } from "../../stores/ws";

interface PermissionsConfig {
  mode?: "strict" | "normal" | "trust";
  tools?: Record<string, { mode?: string; risk?: string }>;
  path_rules?: Array<{ pattern: string; mode?: string }>;
}

const TOOL_NAMES = [
  "run_command", "file_ops", "web_search", "browser_use",
  "wechat_send", "remember_fact", "learn_experience",
];

function getTools(config: Record<string, unknown> | null): NonNullable<PermissionsConfig["tools"]> {
  return (((config?.permissions ?? {}) as Record<string, unknown>).tools as PermissionsConfig["tools"]) ?? {};
}

function getRules(config: Record<string, unknown> | null): NonNullable<PermissionsConfig["path_rules"]> {
  return (((config?.permissions ?? {}) as Record<string, unknown>).path_rules as PermissionsConfig["path_rules"]) ?? [];
}

function getMode(config: Record<string, unknown> | null): string {
  return String(((config?.permissions ?? {}) as Record<string, unknown>).mode ?? "normal");
}

export function PermissionsTab() {
  const send = useWS((s) => s.send);
  const config = useWS((s) => s.config);
  const tools = getTools(config);
  const rules = getRules(config);
  const mode = getMode(config);
  const [newPattern, setNewPattern] = useState("");

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
        <h2 className="font-display text-sm font-semibold">Global mode</h2>
        <div className="flex items-center gap-2">
          {(["strict", "normal", "trust"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={`h-7 px-3 text-[12px] border rounded font-mono uppercase tracking-[0.05em] ${
                mode === m ? "bg-text text-bg border-border" : "border-border text-text-muted hover:bg-surface"
              }`}
            >
              {m}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <h2 className="font-display text-sm font-semibold">Tool overrides</h2>
        <div className="border border-border rounded overflow-hidden">
          <table className="w-full text-[12px]">
            <thead className="bg-bg text-text-muted font-mono text-[10px] uppercase tracking-[0.1em]">
              <tr>
                <th className="text-left px-3 py-2">Tool</th>
                <th className="text-left px-3 py-2">Mode</th>
              </tr>
            </thead>
            <tbody>
              {TOOL_NAMES.map((name) => {
                const t = tools[name] || {};
                return (
                  <tr key={name} className="border-t border-border">
                    <td className="px-3 py-2 font-mono">#{name}</td>
                    <td className="px-3 py-2">
                      <select
                        value={t.mode || "ask"}
                        onChange={(e) => setToolMode(name, e.target.value)}
                        className="bg-bg border border-border rounded px-2 h-7 text-[12px] font-mono"
                      >
                        <option value="ask">ask</option>
                        <option value="trust">trust</option>
                        <option value="deny">deny</option>
                      </select>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <h2 className="font-display text-sm font-semibold">Path rules</h2>
        <div className="flex items-center gap-2">
          <input
            value={newPattern}
            onChange={(e) => setNewPattern(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addRule()}
            placeholder="e.g. /private/**"
            className="flex-1 bg-bg border border-border rounded px-2 h-7 text-[12px] font-mono"
          />
          <button
            onClick={addRule}
            disabled={!newPattern.trim()}
            className="flex items-center gap-1 h-7 px-2 border border-border rounded text-[12px] hover:bg-surface disabled:opacity-50"
          >
            <Plus size={12} strokeWidth={1.5} /> Add
          </button>
        </div>
        {rules.length === 0 ? (
          <p className="text-[12px] text-text-muted">No path rules configured.</p>
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
                  title="Remove"
                >
                  <X size={12} strokeWidth={1.5} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
