import { useEffect, useMemo, useRef, useState } from "react";
import { Plus, Save, Sparkles, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { integrationClient, type IntegrationDraft, type IntegrationSnapshot, type IntegrationSub, type ModelSpec } from "../../clients/integrationClient";
import { IntegrationEditorSub } from "./IntegrationEditorSub";
import { IntegrationTestPanel } from "./IntegrationTestPanel";

interface Props {
  intg: IntegrationSnapshot;
  integrations?: IntegrationSnapshot[];
  onSaved: () => Promise<void> | void;
  onDeleted: () => Promise<void> | void;
}

const defaultMain: ModelSpec = {
  provider: "openai",
  base_url: "https://api.openai.com/v1",
  model: "gpt-4o-mini",
  persona_prompt: "You route requests to relevant specialists and synthesize one accurate final response.",
  specialty: "Routing and synthesis",
  temperature: 0.7,
};

function toDraft(intg: IntegrationSnapshot): IntegrationDraft {
  return {
    id: intg.id,
    name: intg.name,
    description: intg.description ?? "",
    main_model_id: intg.main_model_id,
    main_model: intg.main_model ?? defaultMain,
    rounds: intg.rounds,
    max_depth: intg.max_depth,
    max_subs_picked: intg.max_subs_picked,
    is_default: intg.is_default,
    subs: intg.subs.map((sub) => ({ ...sub, model: sub.model ? { ...sub.model } : sub.model })),
  };
}

export function IntegrationEditor({ intg, integrations = [], onSaved, onDeleted }: Props) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState<IntegrationDraft>(() => toDraft(intg));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const dragging = useRef<number | null>(null);

  useEffect(() => setDraft(toDraft(intg)), [intg]);

  const estCalls = useMemo(() => {
    const chosen = Math.min(Math.max(0, draft.max_subs_picked), draft.subs.length);
    return 2 + chosen * draft.rounds;
  }, [draft.max_subs_picked, draft.rounds, draft.subs.length]);

  const updateMain = (patch: Partial<ModelSpec>) => {
    setDraft((current) => ({ ...current, main_model: { ...(current.main_model ?? defaultMain), ...patch } }));
  };

  const save = async () => {
    setSaving(true);
    setError("");
    try {
      await integrationClient.save(draft);
      await onSaved();
    } catch (reason: any) {
      setError(reason?.code === "cycle" ? `Cycle detected: ${(reason.path ?? []).join(" → ")}` : String(reason?.message ?? reason));
    } finally {
      setSaving(false);
    }
  };

  const addSub = (kind: "model" | "integration") => {
    const lastModel = [...draft.subs].reverse().find((item) => item.kind === "model" && item.model)?.model;
    const sub: IntegrationSub = kind === "model"
      ? {
          display_name: t("integration.subDisplayNameModel", { count: draft.subs.length + 1 }),
          kind,
          model: lastModel
            ? { ...lastModel, id: undefined }
            : { ...defaultMain, persona_prompt: t("integration.subDefaultModelPrompt") },
        }
      : { display_name: t("integration.subDisplayNameIntegration", { count: draft.subs.length + 1 }), kind, child_integration_id: integrations.find((item) => item.id !== intg.id)?.id };
    setDraft((current) => ({ ...current, subs: [...current.subs, sub] }));
  };

  return (
    <div className="space-y-5">
      <section className="rounded-[30px] border border-[var(--border)] bg-[var(--glass)] p-6 shadow-[0_18px_60px_var(--glow-faint)]">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-[260px] flex-1">
            <input aria-label={t("integration.nameLabel")} value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} className="w-full bg-transparent font-display text-3xl font-semibold tracking-[-0.03em] outline-none" />
            <input aria-label={t("integration.descLabel")} value={draft.description ?? ""} onChange={(event) => setDraft({ ...draft, description: event.target.value })} placeholder={t("integration.descPlaceholder")} className="mt-2 w-full bg-transparent text-[13px] text-text-muted outline-none" />
          </div>
          <div data-testid="cost-badge" className="flex items-center gap-2 rounded-full bg-text px-4 py-2 font-mono text-[10px] uppercase tracking-[0.12em] text-bg">
            <Sparkles size={12} /> {t("integration.estCalls", { count: estCalls })}
          </div>
        </div>

        <div className="mt-6 grid gap-3 sm:grid-cols-3">
          {[
            [t("integration.rounds"), "rounds", 1, 5],
            [t("integration.maxSubs"), "max_subs_picked", 0, 20],
            [t("integration.maxDepth"), "max_depth", 1, 8],
          ].map(([label, key, min, max]) => (
            <label key={String(key)} className="rounded-2xl bg-[var(--glow-faint)] px-4 py-3 text-[10px] font-mono uppercase tracking-[0.14em] text-text-muted">
              {label}
              <input type="number" min={Number(min)} max={Number(max)} value={Number(draft[key as keyof IntegrationDraft])} onChange={(event) => setDraft({ ...draft, [key]: Number(event.target.value) })} className="mt-1 w-full bg-transparent font-display text-xl text-text outline-none" />
            </label>
          ))}
        </div>
      </section>

      <section className="rounded-[28px] border border-[var(--border)] bg-[var(--glass)] p-5">
        <div className="mb-4 flex items-center justify-between"><div><h2 className="font-display text-lg font-semibold">{t("integration.mainAgent")}</h2><p className="text-[11px] text-text-muted">{t("integration.mainAgentDesc")}</p></div><span className="font-mono text-[9px] uppercase tracking-[0.16em] text-text-faint">{t("integration.alwaysAtomic")}</span></div>
        <div className="grid gap-3 md:grid-cols-2">
          <label className="md:col-span-2 text-[10px] font-mono uppercase tracking-[0.14em] text-text-muted">
            {t("integration.baseUrl")}
            <input aria-label={t("integration.mainBaseUrl")} value={draft.main_model?.base_url ?? ""} onChange={(event) => updateMain({ base_url: event.target.value })} placeholder="https://api.example.com/v1" className="mt-1 w-full rounded-2xl bg-[var(--glow-faint)] px-4 py-3 font-mono text-[12px] normal-case tracking-normal text-text outline-none" />
          </label>
          <label className="text-[10px] font-mono uppercase tracking-[0.14em] text-text-muted">
            {t("integration.providerName")}
            <input aria-label={t("integration.mainProviderName")} value={draft.main_model?.provider ?? ""} onChange={(event) => updateMain({ provider: event.target.value })} placeholder="openai" className="mt-1 w-full rounded-2xl bg-[var(--glow-faint)] px-4 py-3 text-[12px] normal-case tracking-normal text-text outline-none" />
          </label>
          <label className="text-[10px] font-mono uppercase tracking-[0.14em] text-text-muted">
            {t("integration.modelId")}
            <input aria-label={t("integration.mainModelId")} value={draft.main_model?.model ?? ""} onChange={(event) => updateMain({ model: event.target.value })} placeholder="gpt-4o-mini" className="mt-1 w-full rounded-2xl bg-[var(--glow-faint)] px-4 py-3 font-mono text-[12px] normal-case tracking-normal text-text outline-none" />
          </label>
          <label className="md:col-span-2 text-[10px] font-mono uppercase tracking-[0.14em] text-text-muted">
            {t("integration.apiKey")}
            <input aria-label={t("integration.mainApiKey")} type="password" autoComplete="off" value={draft.main_model?.api_key ?? ""} onChange={(event) => updateMain({ api_key: event.target.value })} placeholder={t("integration.apiKeyPlaceholder")} className="mt-1 w-full rounded-2xl bg-[var(--glow-faint)] px-4 py-3 font-mono text-[12px] normal-case tracking-normal text-text outline-none" />
          </label>
          <label className="md:col-span-2 text-[10px] font-mono uppercase tracking-[0.14em] text-text-muted">
            {t("integration.protocol")}
            <select aria-label={t("integration.mainProtocol")} value={draft.main_model?.protocol ?? ""} onChange={(event) => updateMain({ protocol: event.target.value })} className="mt-1 w-full rounded-2xl bg-[var(--glow-faint)] px-4 py-3 text-[12px] normal-case tracking-normal text-text outline-none">
              <option value="">{t("integration.protocol.auto")}</option>
              <option value="chat">{t("integration.protocol.chat")}</option>
              <option value="responses">{t("integration.protocol.responses")}</option>
              <option value="anthropic">{t("integration.protocol.anthropic")}</option>
            </select>
          </label>
          <textarea aria-label={t("integration.mainPersona")} value={draft.main_model?.persona_prompt ?? ""} onChange={(event) => updateMain({ persona_prompt: event.target.value })} rows={4} className="md:col-span-2 resize-y rounded-2xl bg-[var(--glow-faint)] px-4 py-3 text-[12px] leading-relaxed outline-none" />
        </div>
      </section>

      <section className="rounded-[28px] border border-[var(--border)] bg-[var(--glass)] p-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div><h2 className="font-display text-lg font-semibold">{t("integration.topology")}</h2><p className="text-[11px] text-text-muted">{t("integration.topologyDesc")}</p></div>
          <div className="flex gap-2">
            <button type="button" onClick={() => addSub("model")} className="flex items-center gap-1 rounded-full bg-[var(--glow-faint)] px-3 py-2 text-[10px] font-mono uppercase"><Plus size={12} /> {t("integration.addModel")}</button>
            <button type="button" onClick={() => addSub("integration")} className="flex items-center gap-1 rounded-full bg-[var(--glow-faint)] px-3 py-2 text-[10px] font-mono uppercase"><Plus size={12} /> {t("integration.addIntegration")}</button>
          </div>
        </div>
        <div className="space-y-3">
          {draft.subs.length === 0 && <div className="rounded-[22px] border border-dashed border-[var(--border)] py-10 text-center text-[12px] text-text-muted">{t("integration.mainOnlyHint")}</div>}
          {draft.subs.map((sub, index) => (
            <IntegrationEditorSub
              key={`${sub.id ?? "new"}-${index}`}
              sub={sub}
              integrations={integrations.filter((item) => item.id !== intg.id)}
              onChange={(next) => setDraft((current) => ({ ...current, subs: current.subs.map((item, position) => position === index ? next : item) }))}
              onRemove={() => setDraft((current) => ({ ...current, subs: current.subs.filter((_, position) => position !== index) }))}
              onDragStart={() => { dragging.current = index; }}
              onDrop={() => {
                if (dragging.current === null || dragging.current === index) return;
                const next = [...draft.subs];
                const [moved] = next.splice(dragging.current, 1);
                next.splice(index, 0, moved);
                dragging.current = null;
                setDraft({ ...draft, subs: next });
              }}
            />
          ))}
        </div>
      </section>

      {error && <div role="alert" className="rounded-2xl border border-danger/20 bg-danger/10 px-4 py-3 text-[12px] text-danger">{error}</div>}
      <div className="flex items-center justify-between gap-3">
        <button type="button" onClick={async () => { await integrationClient.delete(intg.id); await onDeleted(); }} className="flex items-center gap-2 rounded-full px-4 py-2 text-[11px] text-danger transition hover:bg-danger/10"><Trash2 size={14} /> {t("common.delete")}</button>
        <button type="button" disabled={saving} onClick={save} className="flex items-center gap-2 rounded-full bg-text px-6 py-2.5 text-[11px] font-semibold text-bg transition hover:scale-[1.02] disabled:opacity-50"><Save size={14} /> {saving ? t("channels.saving") : t("integration.saveEnsemble")}</button>
      </div>
      <IntegrationTestPanel integrationId={intg.id} />
    </div>
  );
}
