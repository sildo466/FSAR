import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { AnimatePresence, motion } from "framer-motion";
import { Check, ChevronDown } from "lucide-react";
import { useWS } from "../stores/ws";
import { integrationClient, type IntegrationSnapshot } from "../clients/integrationClient";
import { chatClient } from "../clients/chatClient";

interface ModelItem { kind: "model" | "integration"; id?: number; provider?: string; model?: string; label: string; est_calls: number; }

function selectedFromConfig(config: Record<string, unknown> | null): Record<string, unknown> {
  const chat = (config?.chat ?? {}) as Record<string, unknown>;
  const saved = chat.default_model;
  if (saved && typeof saved === "object") return saved as Record<string, unknown>;
  const llm = (config?.llm ?? {}) as Record<string, any>;
  const provider = (llm.providers ?? []).find((item: any) => item.id === llm.active) ?? (llm.providers ?? [])[0];
  return { kind: "model", provider: provider?.id ?? "", model: provider?.model ?? "" };
}

function keyFor(item: ModelItem): string {
  return item.kind === "integration" ? `integration:${item.id}` : `model:${item.provider}:${item.model}`;
}

export function ChatModelPicker() {
  const { t } = useTranslation();
  const config = useWS((state) => state.config);
  const send = useWS((state) => state.send);
  const [open, setOpen] = useState(false);
  const [integrations, setIntegrations] = useState<IntegrationSnapshot[]>([]);
  const [snapshotModels, setSnapshotModels] = useState<ModelItem[]>([]);
  const [loaded, setLoaded] = useState(false);
  const selected = selectedFromConfig(config);
  const llm = (config?.llm ?? {}) as Record<string, any>;
  const models: ModelItem[] = useMemo(() => [
    ...((Array.isArray(llm.providers) ? llm.providers : []).filter((item: any) => item.enabled !== false).map((item: any) => ({ kind: "model" as const, provider: item.id, model: item.model, label: item.label || item.id, est_calls: 1 }))),
    ...(snapshotModels.length > 0 ? snapshotModels.filter((item) => item.kind === "integration") : integrations.map((item) => ({ kind: "integration" as const, id: item.id, label: item.name, est_calls: item.est_calls ?? 2 }))),
  ], [integrations, llm.providers, snapshotModels]);
  const found = models.find((item) => keyFor(item) === keyFor(selected as unknown as ModelItem));
  const current = found ?? ((selected.kind === "integration" ? null : models[0]) ?? null);

  useEffect(() => {
    void chatClient.snapshot().then((snapshot) => {
      setSnapshotModels(snapshot.chat_models);
      setIntegrations(snapshot.chat_models.filter((item) => item.kind === "integration").map((item) => ({ id: item.id!, name: item.label, description: "", main_model_id: 0, rounds: 2, max_depth: 2, max_subs_picked: 2, subs: [], est_calls: item.est_calls })));
    }).catch(() => undefined).finally(() => setLoaded(true));
  }, []);

  useEffect(() => {
    if (!open) return;
    void integrationClient.list().then(setIntegrations).catch(() => undefined);
  }, [open]);

  const pick = (item: ModelItem) => {
    const next = item.kind === "integration"
      ? { kind: "integration", id: item.id }
      : { kind: "model", provider: item.provider, model: item.model };
    send({ type: "settings.patch", patch: { "chat.default_model": next } });
    if (item.kind === "model" && item.provider && item.provider !== String(llm.active ?? "")) {
      send({ type: "llm.set_active", provider_id: item.provider });
    }
    setOpen(false);
  };

  return (
    <div className="relative">
      <button type="button" aria-label={t("chatModel.aria")} aria-expanded={open} onClick={() => setOpen((value) => !value)} className="flex items-center gap-2 rounded-full px-2 py-1.5 text-[11px] text-text-muted transition hover:bg-[var(--glow-faint)] hover:text-text">
        <span className="max-w-[150px] truncate font-mono">{current?.kind === "integration" ? `✓ ${current.label}` : current?.label ?? (!loaded && selected.kind === "integration" ? t("chatModel.loading") : t("chatModel.noModel"))}</span><ChevronDown size={12} className={`transition-transform duration-200 ${open ? "rotate-180" : ""}`} />
      </button>
      <AnimatePresence>{open && <motion.div initial={{ opacity: 0, y: -6, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -6, scale: 0.97 }} transition={{ duration: 0.16, ease: "easeOut" }} className="glass-strong absolute left-0 top-9 z-50 w-[280px] overflow-hidden rounded-[22px] border border-[var(--border)] p-2 shadow-[0_20px_60px_var(--glow-faint)]">
        <div className="px-3 py-2 font-mono text-[9px] uppercase tracking-[0.18em] text-text-faint">{t("chatModel.title")}</div>
        {models.map((item) => <button type="button" key={keyFor(item)} onClick={() => pick(item)} className="flex w-full items-center justify-between gap-3 rounded-2xl px-3 py-2.5 text-left transition hover:bg-[var(--glow-faint)]"><span><span className="block text-[12px]">{item.kind === "integration" ? `✓ ${item.label}` : item.label}</span><span className="font-mono text-[10px] text-text-muted">{item.kind === "integration" ? `~${item.est_calls} calls` : `${item.provider} · ${item.model}`}</span></span>{keyFor(item) === keyFor(selected as unknown as ModelItem) && <Check size={14} />}</button>)}
      </motion.div>}</AnimatePresence>
    </div>
  );
}
