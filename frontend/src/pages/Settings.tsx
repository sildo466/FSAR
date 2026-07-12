// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { Plus, Cpu, Plug, Shield, Palette, Wrench, Database } from "lucide-react";
import { useWS } from "../stores/ws";
import { ProviderModal } from "../components/settings/ProviderModal";
import { MCPTab } from "../components/settings/MCPTab";
import { PermissionsTab } from "../components/settings/PermissionsTab";
import { StyleTab } from "../components/settings/StyleTab";
import { AdvancedTab } from "../components/settings/AdvancedTab";
import { EmbeddingTab } from "../components/settings/EmbeddingTab";
import { cn } from "../lib/cn";

interface Provider {
  id: string;
  label?: string;
  provider_family?: string;
  base_url?: string;
  model?: string;
  pricing?: { input_per_1m?: number; output_per_1m?: number };
  enabled?: boolean;
}

type Tab = "models" | "embedding" | "mcp" | "permissions" | "style" | "advanced";

const TABS: { id: Tab; label: string; icon: typeof Cpu }[] = [
  { id: "models", label: "Models", icon: Cpu },
  { id: "embedding", label: "Embedding", icon: Database },
  { id: "mcp", label: "MCP", icon: Plug },
  { id: "permissions", label: "Permissions", icon: Shield },
  { id: "style", label: "Style", icon: Palette },
  { id: "advanced", label: "Advanced", icon: Wrench },
];

function readProviders(config: Record<string, unknown> | null): Provider[] {
  const llm = (config?.llm ?? {}) as Record<string, unknown>;
  const raw = llm.providers;
  if (!Array.isArray(raw)) return [];
  return raw.filter((p): p is Provider => typeof p === "object" && p !== null);
}

function readActiveId(config: Record<string, unknown> | null): string {
  const llm = (config?.llm ?? {}) as Record<string, unknown>;
  return String(llm.active ?? "");
}

function ModelsTab({
  providers,
  activeId,
  onAdd,
  onEdit,
  onRemove,
  onSetActive,
}: {
  providers: Provider[];
  activeId: string;
  onAdd: () => void;
  onEdit: (p: Provider) => void;
  onRemove: (id: string) => void;
  onSetActive: (id: string) => void;
}) {
  return (
    <>
      <div className="flex items-center justify-between">
        <h2 className="font-display text-sm font-semibold">LLM providers</h2>
        <button
          onClick={onAdd}
          className="flex items-center gap-1 h-7 px-2 border border-border rounded text-[12px] hover:bg-surface"
        >
          <Plus size={12} strokeWidth={1.5} /> Add provider
        </button>
      </div>

      {providers.length === 0 ? (
        <div className="border border-border rounded p-6 text-[12px] text-text-muted text-center">
          No providers configured. Click "Add provider" to set one up,
          or copy <code className="font-mono">config/fsar.yaml.template</code>{" "}
          to <code className="font-mono">config/fsar.yaml</code> and edit.
        </div>
      ) : (
        <div className="border border-border rounded overflow-hidden">
          <table className="w-full text-[12px]">
            <thead className="bg-bg text-text-muted font-mono text-[10px] uppercase tracking-[0.1em]">
              <tr>
                <th className="text-left px-3 py-2">Label</th>
                <th className="text-left px-3 py-2">Family</th>
                <th className="text-left px-3 py-2">Model</th>
                <th className="text-right px-3 py-2">Pricing (in/out)</th>
                <th className="text-center px-3 py-2">Active</th>
                <th className="text-right px-3 py-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {providers.map((p) => (
                <tr key={p.id} className="border-t border-border">
                  <td className="px-3 py-2 font-mono">
                    <div className="flex flex-col">
                      <span>{p.label || p.id}</span>
                      <span className="text-text-muted text-[10px]">{p.id}</span>
                    </div>
                  </td>
                  <td className="px-3 py-2 font-mono">{p.provider_family || "—"}</td>
                  <td className="px-3 py-2 font-mono">{p.model || "—"}</td>
                  <td className="px-3 py-2 text-right font-mono text-text-muted">
                    {p.pricing?.input_per_1m ?? 0} / {p.pricing?.output_per_1m ?? 0}
                  </td>
                  <td className="px-3 py-2 text-center">
                    {p.id === activeId ? (
                      <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-success">● active</span>
                    ) : p.enabled === false ? (
                      <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-text-muted">disabled</span>
                    ) : (
                      <button
                        onClick={() => onSetActive(p.id)}
                        className="font-mono text-[10px] uppercase tracking-[0.1em] text-text-muted hover:text-text underline"
                      >
                        set default
                      </button>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <div className="inline-flex items-center gap-1">
                      <button
                        onClick={() => onEdit(p)}
                        className="h-6 w-6 flex items-center justify-center hover:bg-surface rounded"
                        title="Edit"
                      >
                        <span className="text-[11px]">edit</span>
                      </button>
                      <button
                        onClick={() => onRemove(p.id)}
                        className="h-6 px-2 flex items-center justify-center hover:bg-surface rounded text-warning text-[11px]"
                        title="Delete"
                      >
                        del
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

export function Settings() {
  const send = useWS((s) => s.send);
  const config = useWS((s) => s.config);
  const [tab, setTab] = useState<Tab>("models");
  const [editing, setEditing] = useState<Provider | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  const providers = readProviders(config);
  const activeId = readActiveId(config);
  const ids = providers.map((p) => p.id);

  function openAdd() {
    setEditing(null);
    setModalOpen(true);
  }
  function openEdit(p: Provider) {
    setEditing(p);
    setModalOpen(true);
  }
  function removeProvider(id: string) {
    const next = providers.filter((p) => p.id !== id);
    const patch: Record<string, unknown> = { "llm.providers": next };
    if (id === activeId) patch["llm.active"] = "";
    send({ type: "settings.patch", patch });
  }
  function setActive(id: string) {
    if (id === activeId) return;
    send({ type: "llm.set_active", provider_id: id });
  }

  return (
    <div className="mx-auto flex max-w-[1080px] flex-col gap-8 px-8 py-10">
      <header>
        <h1 className="font-display text-4xl italic tracking-[-0.02em]">Settings</h1>
        <p className="text-text-muted">LLM providers, MCP, permissions, and app preferences.</p>
      </header>

      <div className="grid grid-cols-[180px_1fr] gap-8">
        <nav className="glass flex h-fit flex-col gap-1 rounded-[24px] p-2">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={cn(
                "flex items-center gap-2 h-9 px-3 rounded-full text-[12px] text-left",
                tab === t.id
                  ? "bg-text text-bg font-medium shadow-[0_0_18px_var(--glow-soft)]"
                  : "text-text-muted hover:bg-glass hover:text-text"
              )}
            >
              <t.icon size={13} strokeWidth={1.5} />
              {t.label}
            </button>
          ))}
        </nav>

        <section className="glass-strong flex flex-col gap-4 rounded-[28px] p-6 shadow-[0_18px_54px_var(--glow-faint)]">
          {tab === "models" && (
            <ModelsTab
              providers={providers}
              activeId={activeId}
              onAdd={openAdd}
              onEdit={openEdit}
              onRemove={removeProvider}
              onSetActive={setActive}
            />
          )}
          {tab === "embedding" && (
            <EmbeddingTab
              initial={(() => {
                const mem = (config as any)?.memory ?? {};
                const emb = mem.embedder ?? {};
                return {
                  provider: emb.provider || undefined,
                  base_url: emb.base_url || undefined,
                  model: emb.model || undefined,
                  api_key: emb.api_key || undefined,
                };
              })()}
            />
          )}
          {tab === "mcp" && <MCPTab />}
          {tab === "permissions" && <PermissionsTab />}
          {tab === "style" && <StyleTab />}
          {tab === "advanced" && <AdvancedTab />}
        </section>
      </div>

      <ProviderModal
        open={modalOpen}
        initial={editing}
        existingIds={ids}
        onClose={() => setModalOpen(false)}
        onSaved={() => {}}
      />
    </div>
  );
}
