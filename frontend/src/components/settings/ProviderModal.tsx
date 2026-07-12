// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { X, Loader2, CheckCircle2, AlertTriangle, RefreshCw } from "lucide-react";
import { useWS } from "../../stores/ws";

interface Provider {
  id: string;
  label?: string;
  preset_id?: string;
  family?: string;
  provider_family?: string;
  base_url?: string;
  api_key?: string;
  model?: string;
  context_window?: number;
  max_output_tokens?: number;
  pricing?: { input_per_1m?: number; output_per_1m?: number };
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

function normalizeFamily(family?: string): string {
  if (family === "openai" || family === "openai-compatible") return "openai_compat";
  if (family === "google") return "gemini";
  return family || "openai_compat";
}

export function ProviderModal({ open, initial, existingIds, onClose, onSaved }: Props) {
  const send = useWS((s) => s.send);
  const config = useWS((s) => s.config);
  const client = useWS((s) => s.client);

  const [label, setLabel] = useState(initial?.label ?? "");
  const [providerFamily, setProviderFamily] = useState(normalizeFamily(initial?.provider_family ?? initial?.family));
  const [baseUrl, setBaseUrl] = useState(initial?.base_url ?? "");
  const [apiKey, setApiKey] = useState(initial?.api_key ?? "");
  const [model, setModel] = useState(initial?.model ?? "");
  const [contextWindow, setContextWindow] = useState(String(initial?.context_window ?? 128000));
  const [maxOutputTokens, setMaxOutputTokens] = useState(String(initial?.max_output_tokens ?? 4096));
  const [models, setModels] = useState<string[]>([]);
  const [fetchingModels, setFetchingModels] = useState(false);
  const [inputPer1m, setInputPer1m] = useState<string>(
    initial?.pricing?.input_per_1m?.toString() ?? ""
  );
  const [outputPer1m, setOutputPer1m] = useState<string>(
    initial?.pricing?.output_per_1m?.toString() ?? ""
  );
  const [enabled, setEnabled] = useState(initial?.enabled !== false);
  const [test, setTest] = useState<TestState>({ kind: "idle" });

  useEffect(() => {
    if (open) {
      setLabel(initial?.label ?? "");
      setProviderFamily(normalizeFamily(initial?.provider_family ?? initial?.family));
      setBaseUrl(initial?.base_url ?? "");
      setApiKey(initial?.api_key ?? "");
      setModel(initial?.model ?? "");
      setContextWindow(String(initial?.context_window ?? 128000));
      setMaxOutputTokens(String(initial?.max_output_tokens ?? 4096));
      setModels([]);
      setFetchingModels(false);
      setInputPer1m(initial?.pricing?.input_per_1m?.toString() ?? "");
      setOutputPer1m(initial?.pricing?.output_per_1m?.toString() ?? "");
      setEnabled(initial?.enabled !== false);
      setTest({ kind: "idle" });
    }
  }, [open, initial]);

  useEffect(() => {
    if (!open || !client) return;
    return client.on((msg) => {
      if (msg.type === "provider.test_result") {
        setTest(msg.ok
          ? { kind: "ok", model: model || undefined }
          : { kind: "fail", reason: msg.error || "Connection failed." });
      } else if (msg.type === "provider.models") {
        setFetchingModels(false);
        if (msg.ok) {
          setModels(msg.models);
          if (!model && msg.models.length > 0) setModel(msg.models[0]);
        } else {
          setTest({ kind: "fail", reason: msg.error || "Unable to fetch models." });
        }
      }
    });
  }, [open, client, model]);

  if (!open) return null;

  function presetId(): string {
    if (initial?.preset_id) return initial.preset_id;
    if (providerFamily === "anthropic") return "anthropic";
    if (providerFamily === "gemini" || providerFamily === "google") return "google";
    return "openai";
  }

  function testConnection() {
    if (!baseUrl) {
      setTest({ kind: "fail", reason: "Base URL is empty." });
      return;
    }
    setTest({ kind: "testing" });
    send({
      type: "provider.test_connection",
      preset_id: presetId(),
      base_url: baseUrl,
      api_key: apiKey,
      model,
    });
  }

  function fetchModels() {
    if (!baseUrl) {
      setTest({ kind: "fail", reason: "Base URL is empty." });
      return;
    }
    setFetchingModels(true);
    send({
      type: "provider.fetch_models",
      preset_id: presetId(),
      base_url: baseUrl,
      api_key: apiKey,
    });
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
      preset_id: presetId(),
      family: providerFamily,
      base_url: baseUrl,
      api_key: apiKey,
      model,
      context_window: Number(contextWindow) || 128000,
      max_output_tokens: Number(maxOutputTokens) || 4096,
      pricing: {
        input_per_1m: Number(inputPer1m) || 0,
        output_per_1m: Number(outputPer1m) || 0,
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
              <option value="openai_compat">openai compatible</option>
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
          <Field label="Model" wide>
            <div className="flex gap-2">
              <input
                value={model}
                onChange={(e) => setModel(e.target.value)}
                list="provider-models"
                className="min-w-0 flex-1 bg-bg border border-border rounded px-2 h-7 font-mono"
                placeholder="claude-sonnet-4-6"
              />
              <datalist id="provider-models">
                {models.map((item) => <option key={item} value={item} />)}
              </datalist>
              <button
                onClick={fetchModels}
                disabled={fetchingModels}
                className="px-2 h-7 border border-border rounded text-[12px] hover:bg-surface flex items-center gap-1 disabled:opacity-50"
              >
                <RefreshCw size={11} className={fetchingModels ? "animate-spin" : ""} />
                Fetch models
              </button>
            </div>
          </Field>
          <Field label="Context window">
            <input
              value={contextWindow}
              onChange={(e) => setContextWindow(e.target.value)}
              type="number"
              min="1024"
              className="w-full bg-bg border border-border rounded px-2 h-7 font-mono"
            />
          </Field>
          <Field label="Max output tokens">
            <input
              value={maxOutputTokens}
              onChange={(e) => setMaxOutputTokens(e.target.value)}
              type="number"
              min="1"
              className="w-full bg-bg border border-border rounded px-2 h-7 font-mono"
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
          <Field label="Pricing (per 1M tokens, USD)">
            <div className="flex items-center gap-2">
              <input
                value={inputPer1m}
                onChange={(e) => setInputPer1m(e.target.value)}
                className="w-20 bg-bg border border-border rounded px-2 h-7 font-mono text-right"
                placeholder="0.15"
              />
              <span className="text-text-muted text-[11px]">in</span>
              <input
                value={outputPer1m}
                onChange={(e) => setOutputPer1m(e.target.value)}
                className="w-20 bg-bg border border-border rounded px-2 h-7 font-mono text-right"
                placeholder="0.60"
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
