// SPDX-License-Identifier: Apache-2.0
import { useState, useEffect, useRef } from "react";
import { ChevronDown, Cpu, Sun, Moon, Monitor } from "lucide-react";
import { motion } from "framer-motion";
import { useWS } from "../../stores/ws";
import { useUI, type Theme } from "../../stores/ui";
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
  const theme = useUI((s) => s.theme);
  const setTheme = useUI((s) => s.setTheme);
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

  function cycle() {
    const next: Theme = theme === "light" ? "dark" : theme === "dark" ? "system" : "light";
    setTheme(next);
    send({ type: "style.set_theme", theme: next });
  }

  const ThemeIcon = theme === "light" ? Sun : theme === "dark" ? Moon : Monitor;
  const label = active?.label || active?.model || activeId || "(no provider)";

  return (
    <motion.header initial={{ y: -16, opacity: 0 }} animate={{ y: 0, opacity: 1 }} className="glass fixed left-[5.5rem] right-3 top-3 z-30 flex h-12 items-center justify-between rounded-full px-4 shadow-[0_12px_36px_var(--glow-faint)]">
      <div className="flex items-center gap-2">
        <div className="text-[13px] text-text-muted font-mono">FSAR · local-first agent</div>
        <button
          onClick={cycle}
          title={`Theme: ${theme}`}
          className="flex h-8 w-8 items-center justify-center rounded-full text-text-muted transition hover:bg-glass hover:text-text"
        >
          <ThemeIcon size={12} strokeWidth={1.5} />
        </button>
      </div>
      <div ref={ref} className="relative">
        <button
          onClick={() => setOpen((v) => !v)}
          className={cn(
            "glass flex h-8 items-center gap-2 rounded-full px-3 text-[12px] transition hover:bg-glass-strong",
            !active && "border-warning text-warning"
          )}
        >
          <Cpu size={13} strokeWidth={1.5} />
          <span className="font-mono">{label}</span>
          <ChevronDown size={12} strokeWidth={1.5} />
        </button>
        {open && (
          <div className="glass-strong absolute right-0 top-10 z-50 w-[260px] overflow-hidden rounded-2xl shadow-[0_16px_44px_var(--glow-faint)]">
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
                        "flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-[12px] transition hover:bg-glass",
                        p.id === activeId && "bg-glass"
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
    </motion.header>
  );
}
