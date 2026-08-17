import { GripVertical, Link2, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { IntegrationSnapshot, IntegrationSub, ModelSpec } from "../../clients/integrationClient";

interface Props {
  sub: IntegrationSub;
  integrations?: IntegrationSnapshot[];
  onChange: (next: IntegrationSub) => void;
  onRemove: () => void;
  onDragStart?: () => void;
  onDrop?: () => void;
}

const emptyModel: ModelSpec = {
  provider: "openai",
  base_url: "https://api.openai.com/v1",
  model: "gpt-4o-mini",
  persona_prompt: "You are a focused specialist. Provide concrete evidence and concise recommendations.",
  specialty: "",
  temperature: 0.7,
};

export function IntegrationEditorSub({ sub, integrations = [], onChange, onRemove, onDragStart, onDrop }: Props) {
  const { t } = useTranslation();
  const updateModel = (patch: Partial<ModelSpec>) => {
    onChange({ ...sub, model: { ...(sub.model ?? emptyModel), ...patch } });
  };

  return (
    <div
      draggable
      onDragStart={onDragStart}
      onDragOver={(event) => event.preventDefault()}
      onDrop={onDrop}
      className="group rounded-[22px] border border-[var(--border)] bg-[var(--glass)] p-4 transition hover:border-[var(--text-faint)]"
    >
      <div className="flex items-center gap-3">
        <GripVertical size={15} className="cursor-grab text-text-faint" />
        <input
          aria-label={t("integration.subDisplayName")}
          value={sub.display_name}
          onChange={(event) => onChange({ ...sub, display_name: event.target.value })}
          className="min-w-0 flex-1 bg-transparent font-display text-[15px] font-semibold outline-none"
        />
        <div className="flex rounded-full bg-[var(--glow-faint)] p-1 text-[10px] font-mono uppercase tracking-[0.12em]">
          {(["model", "integration"] as const).map((kind) => (
            <button
              type="button"
              key={kind}
              onClick={() => onChange({
                ...sub,
                kind,
                model: kind === "model" ? (sub.model ?? emptyModel) : undefined,
                child_integration_id: kind === "integration" ? (sub.child_integration_id ?? integrations[0]?.id) : undefined,
              })}
              className={`rounded-full px-2 py-1 transition ${sub.kind === kind ? "bg-[var(--button-bg)] text-[var(--button-text)] button-tex" : "text-text-muted"}`}
            >
              {t(kind === "model" ? "integration.kind.model" : "integration.kind.integration")}
            </button>
          ))}
        </div>
        <button type="button" aria-label={t("common.remove")} onClick={onRemove} className="rounded-full p-2 text-text-faint transition hover:bg-danger/10 hover:text-danger">
          <Trash2 size={14} />
        </button>
      </div>

      {sub.kind === "integration" ? (
        <div className="mt-4 flex items-center gap-3 rounded-2xl bg-[var(--glow-faint)] px-3 py-2">
          <Link2 size={14} className="text-text-muted" />
          <select
            aria-label={t("integration.linkedIntegration")}
            value={sub.child_integration_id ?? ""}
            onChange={(event) => onChange({ ...sub, child_integration_id: Number(event.target.value) })}
            className="min-w-0 flex-1 bg-transparent text-[12px] outline-none"
          >
            <option value="">{t("integration.chooseIntegration")}</option>
            {integrations.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
          {sub.child_integration_id && (
            <a className="text-[11px] font-mono text-text-muted underline" href={`/intergration?id=${sub.child_integration_id}`}>{t("common.open")}</a>
          )}
        </div>
      ) : (
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <label className="md:col-span-2 text-[10px] font-mono uppercase tracking-[0.14em] text-text-muted">
            {t("integration.baseUrl")}
            <input aria-label={t("integration.subBaseUrl")} value={sub.model?.base_url ?? ""} onChange={(event) => updateModel({ base_url: event.target.value })} placeholder="https://api.example.com/v1" className="mt-1 w-full rounded-xl bg-[var(--glow-faint)] px-3 py-2 font-mono text-[12px] normal-case tracking-normal text-text outline-none" />
          </label>
          <label className="text-[10px] font-mono uppercase tracking-[0.14em] text-text-muted">
            {t("integration.providerName")}
            <input aria-label={t("integration.subProviderName")} value={sub.model?.provider ?? ""} onChange={(event) => updateModel({ provider: event.target.value })} className="mt-1 w-full rounded-xl bg-[var(--glow-faint)] px-3 py-2 text-[12px] normal-case tracking-normal text-text outline-none" />
          </label>
          <label className="text-[10px] font-mono uppercase tracking-[0.14em] text-text-muted">
            {t("integration.modelId")}
            <input aria-label={t("integration.subModelId")} value={sub.model?.model ?? ""} onChange={(event) => updateModel({ model: event.target.value })} className="mt-1 w-full rounded-xl bg-[var(--glow-faint)] px-3 py-2 font-mono text-[12px] normal-case tracking-normal text-text outline-none" />
          </label>
          <label className="md:col-span-2 text-[10px] font-mono uppercase tracking-[0.14em] text-text-muted">
            {t("integration.apiKey")}
            <input aria-label={t("integration.subApiKey")} type="password" autoComplete="off" value={sub.model?.api_key ?? ""} onChange={(event) => updateModel({ api_key: event.target.value })} placeholder={t("integration.apiKeyPlaceholder")} className="mt-1 w-full rounded-xl bg-[var(--glow-faint)] px-3 py-2 font-mono text-[12px] normal-case tracking-normal text-text outline-none" />
          </label>
          <label className="text-[10px] font-mono uppercase tracking-[0.14em] text-text-muted">
            {t("integration.protocol")}
            <select aria-label={t("integration.subProtocol")} value={sub.model?.protocol ?? ""} onChange={(event) => updateModel({ protocol: event.target.value })} className="mt-1 w-full rounded-xl bg-[var(--glow-faint)] px-3 py-2 text-[12px] normal-case tracking-normal text-text outline-none">
              <option value="">{t("integration.protocol.auto")}</option>
              <option value="chat">{t("integration.protocol.chat")}</option>
              <option value="responses">{t("integration.protocol.responses")}</option>
              <option value="anthropic">{t("integration.protocol.anthropic")}</option>
            </select>
          </label>
          <label className="md:col-span-2 text-[10px] font-mono uppercase tracking-[0.14em] text-text-muted">
            {t("integration.specialty")}
            <input value={sub.model?.specialty ?? ""} onChange={(event) => updateModel({ specialty: event.target.value })} placeholder={t("integration.specialtyPlaceholder")} className="mt-1 w-full rounded-xl bg-[var(--glow-faint)] px-3 py-2 text-[12px] normal-case tracking-normal text-text outline-none" />
          </label>
          <label className="md:col-span-2 text-[10px] font-mono uppercase tracking-[0.14em] text-text-muted">
            {t("integration.persona")}
            <textarea value={sub.model?.persona_prompt ?? ""} onChange={(event) => updateModel({ persona_prompt: event.target.value })} rows={3} className="mt-1 w-full resize-y rounded-xl bg-[var(--glow-faint)] px-3 py-2 text-[12px] normal-case leading-relaxed tracking-normal text-text outline-none" />
          </label>
        </div>
      )}
    </div>
  );
}
