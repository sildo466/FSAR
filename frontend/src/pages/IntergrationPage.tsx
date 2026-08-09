import { useCallback, useEffect, useState } from "react";
import { Layers3, Plus, Sparkles } from "lucide-react";
import { useTranslation } from "react-i18next";
import { integrationClient, type IntegrationDraft, type IntegrationSnapshot } from "../clients/integrationClient";
import { IntegrationEditor } from "./components/IntegrationEditor";

const blank: IntegrationDraft = {
  name: "New Intergration",
  description: "",
  main_model_id: 0,
  main_model: {
    provider: "openai",
    base_url: "https://api.openai.com/v1",
    model: "gpt-4o-mini",
    persona_prompt: "You route requests to relevant specialists and synthesize one accurate final response.",
    specialty: "Routing and synthesis",
    temperature: 0.7,
  },
  rounds: 2,
  max_depth: 2,
  max_subs_picked: 2,
  subs: [],
};

export function IntergrationPage() {
  const { t } = useTranslation();
  const [items, setItems] = useState<IntegrationSnapshot[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      const next = await integrationClient.list();
      setItems(next);
      setSelectedId((current) => next.some((item) => item.id === current) ? current : next[0]?.id ?? null);
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const create = async () => {
    const result = await integrationClient.save({ ...blank, name: `New Intergration ${items.length + 1}` });
    await refresh();
    setSelectedId(result.id);
  };

  const selected = items.find((item) => item.id === selectedId) ?? null;

  if (loading) return <div className="grid min-h-[70vh] place-items-center font-mono text-[11px] uppercase tracking-[0.18em] text-text-muted">{t("integration.mapping")}</div>;

  if (items.length === 0) {
    return (
      <div className="relative grid min-h-[calc(100vh-1.5rem)] place-items-center overflow-hidden rounded-[34px] border border-[var(--border)] bg-[var(--glass)]">
        <div className="absolute inset-0 opacity-50 [background-image:radial-gradient(circle_at_50%_40%,var(--glow-soft),transparent_38%)]" />
        <div className="relative max-w-lg px-6 text-center">
          <div className="mx-auto grid h-20 w-20 place-items-center rounded-[28px] border border-[var(--border)] bg-[var(--glass-strong)] shadow-[0_20px_60px_var(--glow-soft)]"><Layers3 size={31} strokeWidth={1.2} /></div>
          <p className="mt-6 font-mono text-[10px] uppercase tracking-[0.22em] text-text-muted">{t("integration.recursiveIntelligence")}</p>
          <h1 className="mt-2 font-display text-4xl font-semibold tracking-[-0.04em]">{t("integration.buildMind")}</h1>
          <p className="mx-auto mt-4 max-w-md text-[13px] leading-relaxed text-text-muted">{t("integration.buildMindDesc")}</p>
          {error && <div role="alert" className="mt-4 text-[12px] text-danger">{error}</div>}
          <button type="button" onClick={create} className="mx-auto mt-7 flex items-center gap-2 rounded-full bg-text px-6 py-3 text-[11px] font-semibold text-bg transition hover:scale-105"><Sparkles size={14} /> {t("integration.createFirst")}</button>
        </div>
      </div>
    );
  }

  return (
    <div className="grid min-h-full gap-3 lg:grid-cols-[300px_minmax(0,1fr)]">
      <aside className="rounded-[30px] border border-[var(--border)] bg-[var(--glass)] p-3 lg:sticky lg:top-3 lg:h-[calc(100vh-1.5rem)]">
        <div className="flex items-center justify-between px-3 py-3"><div><p className="font-mono text-[9px] uppercase tracking-[0.2em] text-text-muted">{t("integration.ensembleRegistry")}</p><h1 className="font-display text-xl font-semibold">{t("integration.title")}</h1></div><button type="button" onClick={create} aria-label={t("integration.newIntegration")} className="grid h-9 w-9 place-items-center rounded-full bg-text text-bg"><Plus size={15} /></button></div>
        <div className="mt-2 space-y-2">
          {items.map((item) => (
            <button key={item.id} type="button" onClick={() => setSelectedId(item.id)} className={`group w-full rounded-[22px] p-4 text-left transition ${selectedId === item.id ? "bg-text text-bg shadow-[0_12px_32px_var(--glow-soft)]" : "hover:bg-[var(--glow-faint)]"}`}>
              <div className="flex items-start justify-between gap-3"><span className="font-display text-[15px] font-semibold">{item.name}</span><span className={`font-mono text-[9px] ${selectedId === item.id ? "text-bg/60" : "text-text-faint"}`}>~{item.est_calls ?? 2}</span></div>
              <p className={`mt-1 line-clamp-2 text-[11px] leading-relaxed ${selectedId === item.id ? "text-bg/65" : "text-text-muted"}`}>{item.description || t("integration.noDescription")}</p>
              <div className={`mt-3 font-mono text-[9px] uppercase tracking-[0.12em] ${selectedId === item.id ? "text-bg/55" : "text-text-faint"}`}>{t("integration.subsRounds", { subs: item.subs.length, rounds: item.rounds })}</div>
            </button>
          ))}
        </div>
      </aside>
      <main className="min-w-0 rounded-[34px] bg-[radial-gradient(circle_at_top_right,var(--glow-faint),transparent_35%)] p-1 lg:p-3">
        {selected && <IntegrationEditor intg={selected} integrations={items} onSaved={refresh} onDeleted={refresh} />}
      </main>
    </div>
  );
}
