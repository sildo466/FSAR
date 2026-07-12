// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { Loader2, CheckCircle2, AlertTriangle } from "lucide-react";
import { useWS } from "../../stores/ws";

type Provider = "openai" | "lmstudio" | "ollama";

const PROVIDER_DEFAULTS: Record<Provider, { base_url: string; model: string; needs_key: boolean; label: string }> = {
  openai: { base_url: "https://api.openai.com/v1", model: "text-embedding-3-small", needs_key: true, label: "OpenAI" },
  lmstudio: { base_url: "http://localhost:1234/v1", model: "text-embedding-embeddinggemma-300m-qat", needs_key: false, label: "LM Studio (local)" },
  ollama: { base_url: "http://localhost:11434/api", model: "nomic-embed-text", needs_key: false, label: "Ollama (local)" },
};

interface Initial {
  provider?: string;
  base_url?: string;
  model?: string;
  api_key?: string;
}

export function EmbeddingTab({ initial }: { initial?: Initial | null }) {
  const send = useWS((s) => s.send);
  const client = useWS((s) => s.client);

  const [provider, setProvider] = useState<Provider | "">((initial?.provider as Provider) || "");
  const [baseUrl, setBaseUrl] = useState(initial?.base_url || "");
  const [model, setModel] = useState(initial?.model || "");
  const [apiKey, setApiKey] = useState(initial?.api_key || "");

  useEffect(() => {
    if (!initial) return;
    if (initial.provider) setProvider(initial.provider as Provider);
    setBaseUrl(initial.base_url || "");
    setModel(initial.model || "");
    setApiKey(initial.api_key || "");
  }, [initial?.provider, initial?.base_url, initial?.model, initial?.api_key]);

  const [probe, setProbe] = useState<
    | { kind: "idle" }
    | { kind: "probing" }
    | { kind: "ok"; dim?: number }
    | { kind: "fail"; reason: string }
  >({ kind: "idle" });

  const [savedAt, setSavedAt] = useState<string | null>(null);

  function chooseProvider(p: Provider) {
    setProvider(p);
    if (!baseUrl) setBaseUrl(PROVIDER_DEFAULTS[p].base_url);
    if (!model) setModel(PROVIDER_DEFAULTS[p].model);
    setProbe({ kind: "idle" });
  }

  function save() {
    if (!provider) return;
    send({
      type: "embedding.upsert",
      provider,
      base_url: baseUrl,
      model,
      api_key: provider === "openai" ? apiKey : "",
    });
    setSavedAt(new Date().toLocaleTimeString());
  }

  async function testConnection() {
    if (!provider) return;
    setProbe({ kind: "probing" });
    const onResult = (msg: any) => {
      if (msg.type !== "embedding.probe_result") return;
      if (msg.ok) setProbe({ kind: "ok", dim: msg.dim });
      else setProbe({ kind: "fail", reason: msg.error || "unknown error" });
    };
    const u = client?.on(onResult);
    send({
      type: "embedding.probe",
      provider,
      base_url: baseUrl || undefined,
      model: model || undefined,
      api_key: apiKey || undefined,
    } as any);
    setTimeout(() => u?.(), 8000);
  }

  const def = provider ? PROVIDER_DEFAULTS[provider] : null;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-1">
        <h2 className="font-display text-sm font-semibold">Embedding provider</h2>
        <p className="text-[12px] text-text-muted max-w-prose">
          Embeddings power FSAR's semantic memory — finding relevant past conversations
          and experiences. Pick OpenAI for hosted, or run LM Studio / Ollama locally.
        </p>
      </div>

      <div className="flex items-center gap-2">
        {(["openai", "lmstudio", "ollama"] as const).map((p) => (
          <button
            key={p}
            onClick={() => chooseProvider(p)}
            data-testid={`settings-embedder-provider-${p}`}
            data-active={provider === p}
            className={`h-7 px-3 text-[12px] border rounded font-mono uppercase tracking-[0.05em] ${
              provider === p ? "bg-text text-bg border-border" : "border-border text-text-muted hover:bg-surface"
            }`}
          >
            {PROVIDER_DEFAULTS[p].label}
          </button>
        ))}
      </div>

      {def && (
        <div className="grid grid-cols-2 gap-4 text-[12px]">
          {def.needs_key && (
            <div className="col-span-2 flex flex-col gap-1">
              <label className="text-text-muted font-mono text-[10px] uppercase tracking-[0.1em]">API key</label>
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="sk-..."
                className="bg-bg border border-border rounded px-2 h-7 font-mono"
              />
            </div>
          )}
          <div className="flex flex-col gap-1">
            <label className="text-text-muted font-mono text-[10px] uppercase tracking-[0.1em]">Base URL</label>
            <input
              value={baseUrl}
              onChange={(e) => { setBaseUrl(e.target.value); setProbe({ kind: "idle" }); }}
              className="bg-bg border border-border rounded px-2 h-7 font-mono"
              placeholder={def.base_url}
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-text-muted font-mono text-[10px] uppercase tracking-[0.1em]">Model</label>
            <input
              value={model}
              onChange={(e) => { setModel(e.target.value); setProbe({ kind: "idle" }); }}
              className="bg-bg border border-border rounded px-2 h-7 font-mono"
              placeholder={def.model}
            />
          </div>

          <div className="col-span-2 flex items-center gap-3 pt-1">
            <button
              onClick={testConnection}
              disabled={probe.kind === "probing"}
              className="px-2 h-7 border border-border rounded text-[12px] hover:bg-surface flex items-center gap-1"
            >
              {probe.kind === "probing" ? <Loader2 size={11} className="animate-spin" /> : null}
              {probe.kind === "probing" ? "Testing…" : "Test connection"}
            </button>
            {probe.kind === "ok" && (
              <span className="text-[11px] flex items-center gap-1 text-text-muted">
                <CheckCircle2 size={11} className="text-success" />
                OK{probe.dim ? ` · dim ${probe.dim}` : ""}
              </span>
            )}
            {probe.kind === "fail" && (
              <span className="text-[11px] flex items-center gap-1 text-text-muted">
                <AlertTriangle size={11} className="text-warning" />
                {probe.reason}
              </span>
            )}
            <button
              onClick={save}
              disabled={!provider || !baseUrl || !model}
              className="ml-auto px-3 h-7 bg-text text-bg rounded text-[12px] disabled:opacity-50"
              data-testid="settings-embedder-save"
            >
              Save
            </button>
            {savedAt && (
              <span className="text-[11px] text-text-muted">saved {savedAt}</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
