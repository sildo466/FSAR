// SPDX-License-Identifier: Apache-2.0
import { useState, useEffect, useRef } from "react";
import { ChevronDown, Cpu } from "lucide-react";
import { useWS } from "../../stores/ws";
import { cn } from "../../lib/cn";

interface Provider {
  id: string;
  label?: string;
  model?: string;
  enabled?: boolean;
}

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

function activeProvider(providers: Provider[], id: string): Provider | null {
  return providers.find((p) => p.id === id) ?? null;
}

export function Topbar() {
  const send = useWS((s) => s.send);
  const config = useWS((s) => s.config);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const providers = readProviders(config);
  const enabled = providers.filter((p) => p.enabled !== false);
  const activeId = readActiveId(config);
  const active = activeProvider(providers, activeId);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  function pick(id: string) {
    if (id === activeId) {
      setOpen(false);
      return;
    }
    send({ type: "llm.set_active", provider_id: id });
    setOpen(false);
  }

  const label = active?.label || active?.model || activeId || "(no provider)";

  return (
    <div className="h-12 border-b border-border bg-bg flex items-center px-6 justify-between">
      <div className="text-[13px] text-text-muted font-mono">FSAR · local-first agent</div>
      <div ref={ref} className="relative">
        <button
          onClick={() => setOpen((v) => !v)}
          className={cn(
            "flex items-center gap-2 px-3 h-8 border border-border rounded text-[12px] hover:bg-surface",
            !active && "border-warning text-warning"
          )}
        >
          <Cpu size={13} strokeWidth={1.5} />
          <span className="font-mono">{label}</span>
          <ChevronDown size={12} strokeWidth={1.5} />
        </button>
        {open && (
          <div className="absolute right-0 top-9 z-50 w-[260px] border border-border rounded bg-bg shadow-lg">
            {enabled.length === 0 ? (
              <div className="px-4 py-3 text-[12px] text-text-muted">
                No enabled providers. <a href="/settings" className="underline">Configure</a>
              </div>
            ) : (
              <ul>
                {enabled.map((p) => (
                  <li key={p.id}>
                    <button
                      onClick={() => pick(p.id)}
                      className={cn(
                        "w-full text-left px-3 py-2 text-[12px] hover:bg-surface flex items-center justify-between gap-3",
                        p.id === activeId && "bg-surface"
                      )}
                    >
                      <div className="flex flex-col">
                        <span className="font-mono">{p.label || p.id}</span>
                        <span className="text-text-muted font-mono text-[11px]">{p.model || ""}</span>
                      </div>
                      {p.id === activeId && (
                        <span className="text-[10px] font-mono uppercase tracking-[0.1em] text-text-muted">active</span>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
