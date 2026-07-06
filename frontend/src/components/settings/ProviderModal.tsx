// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { X, Loader2, CheckCircle2, AlertTriangle } from "lucide-react";
import { useWS } from "../../stores/ws";

interface Provider {
  id: string;
  label?: string;
  provider_family?: string;
  base_url?: string;
  api_key?: string;
  model?: string;
  pricing?: { input_per_1k?: number; output_per_1k?: number };
  enabled?: boolean;
}

interface Props {
  open: boolean;
  initial: Provider | null;
  existingIds: string[];
  onClose: () => void;
  onSaved: () => void;
}

type TestState =
  | { kind: "idle" }
  | { kind: "testing" }
  | { kind: "ok"; model?: string }
  | { kind: "fail"; reason: string };

function generateId(label: string): string {
  const slug = label.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  return slug || `provider-${Date.now().toString(36)}`;
}

export function ProviderModal({ open, initial, existingIds, onClose, onSaved }: Props) {
  const send = useWS((s) => s.send);
  const config = useWS((s) => s.config);

  const [label, setLabel] = useState(initial?.label ?? "");
  const [providerFamily, setProviderFamily] = useState(initial?.provider_family ?? "openai");
  const [baseUrl, setBaseUrl] = useState(initial?.base_url ?? "");
  const [apiKey, setApiKey] = useState(initial?.api_key ?? "");
  const [model, setModel] = useState(initial?.model ?? "");
  const [inputPer1k, setInputPer1k] = useState<string>(
    initial?.pricing?.input_per_1k?.toString() ?? ""
  );
  const [outputPer1k, setOutputPer1k] = useState<string>(
    initial?.pricing?.output_per_1k?.toString() ?? ""
  );
  const [enabled, setEnabled] = useState(initial?.enabled !== false);
  const [test, setTest] = useState<TestState>({ kind: "idle" });

  useEffect(() => {
    if (open) {
      setLabel(initial?.label ?? "");
      setProviderFamily(initial?.provider_family ?? "openai");
      setBaseUrl(initial?.base_url ?? "");
      setApiKey(initial?.api_key ?? "");
      setModel(initial?.model ?? "");
      setInputPer1k(initial?.pricing?.input_per_1k?.toString() ?? "");
      setOutputPer1k(initial?.pricing?.output_per_1k?.toString() ?? "");
      setEnabled(initial?.enabled !== false);
      setTest({ kind: "idle" });
    }
  }, [open, initial]);

  if (!open) return null;

  async function testConnection() {
    if (!baseUrl) {
      setTest({ kind: "fail", reason: "Base URL is empty." });
      return;
    }
    setTest({ kind: "testing" });
    try {
      const url = `${baseUrl.replace(/\/$/, "")}/models`;
      const res = await fetch(url, {
        method: "GET",
        headers: apiKey ? { Authorization: `Bearer ${apiKey}` } : {},
      });
      if (!res.ok) {
        setTest({ kind: "fail", reason: `HTTP ${res.status}` });
        return;
      }
      const data = await res.json().catch(() => null);
      const firstModel =
        Array.isArray(data?.data)
          ? data.data[0]?.id
          : Array.isArray(data?.models)
            ? data.models[0]?.name
            : undefined;
      setTest({ kind: "ok", model: firstModel });
    } catch (e) {
      setTest({ kind: "fail", reason: e instanceof Error ? e.message : String(e) });
    }
  }

  function save() {
    const llm = ((config?.llm ?? {}) as Record<string, unknown>);
    const providers = Array.isArray(llm.providers)
      ? (llm.providers as Provider[]).map((p) => ({ ...p }))
      : [];
    const id = initial?.id ?? generateId(label);
    if (!initial && existingIds.includes(id)) {
      setTest({ kind: "fail", reason: "Provider id already exists." });
      return;
    }
    const next: Provider = {
      id,
      label,
      provider_family: providerFamily,
      base_url: baseUrl,
      api_key: apiKey,
      model,
      pricing: {
        input_per_1k: Number(inputPer1k) || 0,
        output_per_1k: Number(outputPer1k) || 0,
      },
      enabled,
    };
    let nextProviders: Provider[];
    if (initial) {
      nextProviders = providers.map((p) => (p.id === initial.id ? next : p));
    } else {
      nextProviders = [...providers, next];
    }
    const patch: Record<string, unknown> = { "llm.providers": nextProviders };
    if (!llm.active || initial) {
      patch["llm.active"] = id;
    }
    send({ type: "settings.patch", patch });
    onSaved();
    onClose();
  }

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="bg-bg border border-border rounded shadow-xl w-[520px] max-w-[92vw] flex flex-col">
        <div className="flex items-center justify-between px-5 h-12 border-b border-border">
          <div className="font-display text-sm font-semibold">
            {initial ? `Edit ${initial.label || initial.id}` : "Add provider"}
          </div>
          <button onClick={onClose} className="text-text-muted hover:text-text">
            <X size={16} strokeWidth={1.5} />
          </button>
        </div>

        <div className="p-5 grid grid-cols-2 gap-4 text-[12px]">
          <Field label="Label">
            <input
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              className="w-full bg-bg border border-border rounded px-2 h-7 font-mono"
              placeholder="My Provider"
            />
          </Field>
          <Field label="Family">
            <select
              value={providerFamily}
              onChange={(e) => setProviderFamily(e.target.value)}
              className="w-full bg-bg border border-border rounded px-2 h-7 font-mono"
            >
              <option value="openai">openai</option>
              <option value="anthropic">anthropic</option>
              <option value="gemini">gemini</option>
            </select>
          </Field>
          <Field label="Base URL" wide>
            <input
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              className="w-full bg-bg border border-border rounded px-2 h-7 font-mono"
              placeholder="https://api.example.com/v1"
            />
          </Field>
          <Field label="API key" wide>
            <input
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              type="password"
              className="w-full bg-bg border border-border rounded px-2 h-7 font-mono"
              placeholder="${API_KEY}"
            />
          </Field>
          <Field label="Model">
            <input
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="w-full bg-bg border border-border rounded px-2 h-7 font-mono"
              placeholder="claude-sonnet-4-6"
            />
          </Field>
          <Field label="Enabled">
            <label className="flex items-center gap-2 h-7">
              <input
                type="checkbox"
                checked={enabled}
                onChange={(e) => setEnabled(e.target.checked)}
              />
              <span className="text-text-muted">enable on save</span>
            </label>
          </Field>
          <Field label="Pricing (per 1k)">
            <div className="flex items-center gap-2">
              <input
                value={inputPer1k}
                onChange={(e) => setInputPer1k(e.target.value)}
                className="w-20 bg-bg border border-border rounded px-2 h-7 font-mono text-right"
                placeholder="0.001"
              />
              <span className="text-text-muted text-[11px]">in</span>
              <input
                value={outputPer1k}
                onChange={(e) => setOutputPer1k(e.target.value)}
                className="w-20 bg-bg border border-border rounded px-2 h-7 font-mono text-right"
                placeholder="0.002"
              />
              <span className="text-text-muted text-[11px]">out</span>
            </div>
          </Field>
          <Field label="Test connection">
            <div className="flex items-center gap-2 h-7">
              <button
                onClick={testConnection}
                disabled={test.kind === "testing"}
                className="px-2 h-7 border border-border rounded text-[12px] hover:bg-surface flex items-center gap-1"
              >
                {test.kind === "testing" ? (
                  <Loader2 size={11} className="animate-spin" />
                ) : null}
                {test.kind === "testing" ? "Testing…" : "Test"}
              </button>
              {test.kind === "ok" && (
                <span className="text-[11px] flex items-center gap-1 text-text-muted">
                  <CheckCircle2 size={11} className="text-success" />
                  OK{test.model ? ` · ${test.model}` : ""}
                </span>
              )}
              {test.kind === "fail" && (
                <span className="text-[11px] flex items-center gap-1 text-text-muted">
                  <AlertTriangle size={11} className="text-warning" />
                  {test.reason}
                </span>
              )}
            </div>
          </Field>
        </div>

        <div className="flex items-center justify-end gap-2 px-5 h-12 border-t border-border">
          <button
            onClick={onClose}
            className="px-3 h-7 border border-border rounded text-[12px] hover:bg-surface"
          >
            Cancel
          </button>
          <button
            onClick={save}
            disabled={!label || !model}
            className="px-3 h-7 bg-text text-bg rounded text-[12px] disabled:opacity-50"
          >
            Save
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children, wide }: { label: string; children: React.ReactNode; wide?: boolean }) {
  return (
    <div className={wide ? "col-span-2 flex flex-col gap-1" : "flex flex-col gap-1"}>
      <label className="text-text-muted font-mono text-[10px] uppercase tracking-[0.1em]">{label}</label>
      {children}
    </div>
  );
}
