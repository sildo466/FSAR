// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { useCardsStore, type CardSummary, type UserCardSummary } from "../stores/cards";
import { useWS } from "../stores/ws";
import type { ClientMsg, ServerMsg, WSClient } from "../lib/ws-client";

type Tab = "character" | "user";
type EditorTarget = { kind: Tab; id: number | "new" } | null;
type EmotionMetric = { key: string; name: string; min: number; max: number; initial: number };

const DEFAULT_EMOTION_SCHEMA: EmotionMetric[] = [
  { key: "affection", name: "Affection", min: 0, max: 100, initial: 50 },
  { key: "trust", name: "Trust", min: 0, max: 100, initial: 50 },
  { key: "mood", name: "Mood", min: -100, max: 100, initial: 0 },
  { key: "energy", name: "Energy", min: 0, max: 100, initial: 50 },
  { key: "empathy", name: "Empathy", min: 0, max: 100, initial: 50 },
  { key: "playfulness", name: "Playfulness", min: 0, max: 100, initial: 50 },
  { key: "formality", name: "Formality", min: 0, max: 100, initial: 50 },
];

const DEFAULT_EMOTION_FORMULAS: Record<string, string> = {
  affection: "affection + 0.05",
  trust: "trust * 0.99 + 0.05",
  mood: "mood * 0.95",
  energy: "energy - 0.5",
};

function defaultEmotionSchema(): EmotionMetric[] {
  return DEFAULT_EMOTION_SCHEMA.map((metric) => ({ ...metric }));
}

function stateFromSchema(schema: EmotionMetric[]): Record<string, number> {
  return Object.fromEntries(schema.map((metric) => [metric.key, metric.initial]));
}

type ServerMessageOfType<T extends ServerMsg["type"]> = Extract<ServerMsg, { type: T }>;

function requestCard<T extends ServerMsg["type"]>(
  client: WSClient | null,
  request: ClientMsg,
  responseType: T,
): Promise<ServerMessageOfType<T>> {
  if (!client) return Promise.reject(new Error("WebSocket is not connected"));

  return new Promise((resolve, reject) => {
    let detach = () => {};
    const timeout = window.setTimeout(() => {
      detach();
      reject(new Error("Card request timed out"));
    }, 5000);
    const finish = () => {
      window.clearTimeout(timeout);
      detach();
    };

    detach = client.on((message) => {
      if (message.type === "card.error") {
        finish();
        reject(new Error(message.message ?? message.code));
      } else if (message.type === responseType) {
        finish();
        resolve(message as ServerMessageOfType<T>);
      }
    });
    client.send(request);
  });
}

function field(card: CardSummary | UserCardSummary | null, key: string, fallback = ""): string {
  if (!card) return fallback;
  const v = (card as Record<string, unknown>)[key];
  return typeof v === "string" ? v : fallback;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block mb-3">
      <span className="block text-[11px] font-display uppercase tracking-[0.06em] text-text-muted mb-1">
        {label}
      </span>
      {children}
    </label>
  );
}

function Bar({ value, min = 0, max = 100 }: { value: number; min?: number; max?: number }) {
  const range = Math.max(1, max - min);
  const pct = Math.max(0, Math.min(100, ((value - min) / range) * 100));
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-2 bg-bg/40 rounded overflow-hidden">
        <div className="h-full bg-text" style={{ width: `${pct}%` }} />
      </div>
      <span className="font-mono text-xs text-text-muted w-12 text-right">
        {value.toFixed(0)}
      </span>
    </div>
  );
}

export function Cards() {
  const [tab, setTab] = useState<Tab>("character");
  const [editing, setEditing] = useState<EditorTarget>(null);
  const characters = useCardsStore((s) => s.characters);
  const userCards = useCardsStore((s) => s.userCards);
  const refresh = useCardsStore((s) => s.refresh);

  useEffect(() => {
    refresh();
  }, [refresh]);

  if (editing) {
    return <CardEditor target={editing} onDone={() => { setEditing(null); refresh(); }} />;
  }

  return (
    <div className="p-6 max-w-5xl">
      <div className="flex items-center justify-between mb-4">
        <h1 className="font-display text-2xl">Cards</h1>
        <button
          onClick={() => setEditing({ kind: tab, id: "new" })}
          className="px-3 h-9 bg-text text-surface text-[12px] font-semibold"
        >
          + New {tab === "character" ? "Character" : "User"}
        </button>
      </div>
      <div className="flex gap-2 mb-4 border-b border-border">
        <button
          onClick={() => setTab("character")}
          className={`px-4 py-2 text-[12px] font-display font-semibold uppercase tracking-[0.06em] ${
            tab === "character" ? "border-b-2 border-text" : "text-text-muted"
          }`}
        >
          Character 卡片 ({characters.length})
        </button>
        <button
          onClick={() => setTab("user")}
          className={`px-4 py-2 text-[12px] font-display font-semibold uppercase tracking-[0.06em] ${
            tab === "user" ? "border-b-2 border-text" : "text-text-muted"
          }`}
        >
          User 卡片 ({userCards.length})
        </button>
      </div>

      {tab === "character" ? (
        <ul>
          {characters.map((c) => (
            <li key={c.id} className="flex items-center gap-3 p-3 border-b border-border/50 hover:bg-bg/30">
              {c.avatar_path && <img src={c.avatar_path} alt="" className="w-10 h-10 rounded-full" />}
              <div className="flex-1">
                <strong>{c.name}</strong>
                {c.is_default === 1 && <em className="ml-2 text-text-muted text-xs">(default)</em>}
                <p className="text-xs text-text-muted">{c.personality}</p>
              </div>
              <button onClick={() => setEditing({ kind: "character", id: c.id })} className="px-3 h-8 text-xs border border-border">
                Edit
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <ul>
          {userCards.map((u) => (
            <li key={u.id} className="flex items-center gap-3 p-3 border-b border-border/50 hover:bg-bg/30">
              <div className="flex-1">
                <strong>{u.name}</strong>
                {u.is_default === 1 && <em className="ml-2 text-text-muted text-xs">(default)</em>}
                <p className="text-xs text-text-muted">{u.description}</p>
              </div>
              <button onClick={() => setEditing({ kind: "user", id: u.id })} className="px-3 h-8 text-xs border border-border">
                Edit
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function CardEditor({ target, onDone }: { target: NonNullable<EditorTarget>; onDone: () => void }) {
  const client = useWS((s) => s.client);
  const characters = useCardsStore((s) => s.characters);
  const userCards = useCardsStore((s) => s.userCards);
  const card = target.kind === "character"
    ? (target.id === "new" ? null : characters.find((c) => c.id === target.id) ?? null)
    : (target.id === "new" ? null : userCards.find((u) => u.id === target.id) ?? null);

  const [name, setName] = useState(field(card, "name"));
  const [description, setDescription] = useState(field(card, "description"));
  const [personality, setPersonality] = useState(target.kind === "character" ? field(card, "personality") : "");
  const [scenario, setScenario] = useState(target.kind === "character" ? field(card, "scenario") : "");
  const [systemPromptOverride, setSystemPromptOverride] = useState(
    target.kind === "character" ? field(card, "system_prompt_override") : ""
  );
  const [communicationStyle, setCommunicationStyle] = useState(
    target.kind === "user" ? field(card, "communication_style") : ""
  );
  const [preferencesJson, setPreferencesJson] = useState(
    target.kind === "user"
      ? JSON.stringify((card && (card as UserCardSummary).preferences) ?? {}, null, 2)
      : ""
  );
  const [emotionSchema, setEmotionSchema] = useState<EmotionMetric[]>(() => {
    if (target.kind !== "character") return [];
    const stored = (card as CardSummary | null)?.emotion_schema as EmotionMetric[] | undefined;
    return stored?.length ? stored.map((metric) => ({ ...metric })) : defaultEmotionSchema();
  });
  const [emotionState, setEmotionState] = useState<Record<string, number>>(() => {
    if (target.kind !== "character") return {};
    const stored = (card as CardSummary | null)?.emotion_state;
    return stored && Object.keys(stored).length ? { ...stored } : stateFromSchema(emotionSchema);
  });
  const [emotionFormulas, setEmotionFormulas] = useState<Record<string, string>>(() => {
    if (target.kind !== "character") return {};
    const stored = (card as CardSummary | null)?.emotion_formulas;
    return stored && Object.keys(stored).length ? { ...stored } : { ...DEFAULT_EMOTION_FORMULAS };
  });
  const [formulaStatus, setFormulaStatus] = useState<Record<string, { valid: boolean; error?: string }>>({});
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const schemaError = emotionSchema.find((metric) => (
    metric.min >= metric.max || metric.initial < metric.min || metric.initial > metric.max
  ));

  const updateEmotionMetric = (
    index: number,
    field: "min" | "max" | "initial",
    value: number,
  ) => {
    if (!Number.isFinite(value)) return;
    const metricKey = emotionSchema[index]?.key;
    setEmotionSchema((schema) => schema.map((metric, metricIndex) => (
      metricIndex === index ? { ...metric, [field]: value } : metric
    )));
    if (target.id === "new" && field === "initial" && metricKey) {
      setEmotionState((state) => ({ ...state, [metricKey]: value }));
    }
  };

  const updateFormula = (key: string, formula: string) => {
    setFormulaStatus((status) => {
      const next = { ...status };
      delete next[key];
      return next;
    });
    setEmotionFormulas((formulas) => {
      const next = { ...formulas };
      if (formula.trim()) next[key] = formula;
      else delete next[key];
      return next;
    });
  };

  const onSave = async () => {
    if (schemaError) {
      setActionError(`${schemaError.name}: require min < max and min <= initial <= max`);
      return;
    }
    const card: Record<string, unknown> = {
      id: target.id === "new" ? null : target.id,
      name,
      description,
    };
    if (target.kind === "character") {
      card.personality = personality;
      card.scenario = scenario;
      card.system_prompt_override = systemPromptOverride;
      card.emotion_state = emotionState;
      card.emotion_schema = emotionSchema;
      card.emotion_formulas = emotionFormulas;
    } else {
      card.communication_style = communicationStyle;
      try { card.preferences = JSON.parse(preferencesJson || "{}"); } catch { card.preferences = {}; }
    }
    setBusy(true);
    setActionError(null);
    try {
      await requestCard(client, { type: "card.upsert", kind: target.kind, card }, "card.upserted");
      onDone();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  };

  const onDelete = async () => {
    if (target.id === "new") { onDone(); return; }
    if (!confirm(`Delete this ${target.kind} card?`)) return;
    setBusy(true);
    setActionError(null);
    try {
      await requestCard(client, { type: "card.delete", kind: target.kind, id: target.id }, "card.deleted");
      onDone();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  };

  const onAvatar = async (file: File) => {
    if (target.id === "new") { alert("Save first, then upload avatar."); return; }
    const ext = file.name.split(".").pop() || "png";
    const fd = new FormData();
    fd.append("avatar", file);
    await fetch(`/api/card/${target.id}/avatar`, {
      method: "POST",
      headers: { "X-FSAR-Avatar-Ext": ext },
      body: fd,
    });
    onDone();
  };

  const onImportV2 = async () => {
    const text = prompt("Paste SillyTavern V2 JSON:");
    if (!text) return;
    setBusy(true);
    setActionError(null);
    try {
      await requestCard(client, { type: "card.import_v2", json_text: text }, "card.imported");
      onDone();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  };

  const onExport = async () => {
    if (target.id === "new") return;
    setActionError(null);
    try {
      const response = await requestCard(client, { type: "card.export", id: target.id }, "card.exported");
      const blob = new Blob([JSON.stringify(response.card, null, 2)], { type: "application/json" });
      const anchor = document.createElement("a");
      anchor.href = URL.createObjectURL(blob);
      anchor.download = `${name || "card"}.json`;
      anchor.click();
      URL.revokeObjectURL(anchor.href);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    }
  };

  const onValidateFormula = async (key: string) => {
    if (target.id === "new") return;
    try {
      const response = await requestCard(client, {
        type: "card.validate_formula",
        character_id: target.id,
        formula: emotionFormulas[key] ?? "",
      }, "card.formula_validated");
      setFormulaStatus((status) => ({
        ...status,
        [key]: { valid: response.valid, error: response.error ?? undefined },
      }));
    } catch (error) {
      setFormulaStatus((status) => ({
        ...status,
        [key]: { valid: false, error: error instanceof Error ? error.message : String(error) },
      }));
    }
  };

  return (
    <div className="p-6 max-w-3xl">
      <div className="flex items-center justify-between mb-4">
        <h1 className="font-display text-2xl">
          {target.id === "new" ? "New" : "Edit"} {target.kind} card
        </h1>
        <div className="flex gap-2">
          {target.kind === "character" && (
            <>
              <button onClick={onImportV2} className="px-3 h-8 text-xs border border-border">Import V2</button>
              <button onClick={onExport} className="px-3 h-8 text-xs border border-border">Export</button>
            </>
          )}
        </div>
      </div>

      {target.kind === "character" && target.id !== "new" && (
        <div className="mb-4">
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp"
            onChange={(e) => e.target.files?.[0] && onAvatar(e.target.files[0])}
            className="text-xs"
          />
        </div>
      )}

      <Field label="Name">
        <input value={name} onChange={(e) => setName(e.target.value)} className="w-full px-2 h-9 bg-bg border border-border" />
      </Field>
      <Field label="Description">
        <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} className="w-full px-2 py-1 bg-bg border border-border" />
      </Field>
      {target.kind === "character" && (
        <>
          <Field label="Personality">
            <input value={personality} onChange={(e) => setPersonality(e.target.value)} className="w-full px-2 h-9 bg-bg border border-border" />
          </Field>
          <Field label="Scenario">
            <textarea value={scenario} onChange={(e) => setScenario(e.target.value)} rows={2} className="w-full px-2 py-1 bg-bg border border-border" />
          </Field>
          <Field label="System prompt override (appended to base prompt)">
            <textarea value={systemPromptOverride} onChange={(e) => setSystemPromptOverride(e.target.value)} rows={3} className="w-full px-2 py-1 bg-bg border border-border font-mono text-xs" />
          </Field>

          <details open={target.id === "new"} className="mt-4 border border-border p-3">
            <summary className="cursor-pointer font-display text-[12px] uppercase tracking-[0.06em]">
              Emotion profile
            </summary>
            <p className="mt-2 text-xs text-text-muted">
              Current values evolve during chat. Initial values seed a newly created character.
            </p>
            <div className="mt-4 font-display text-[11px] uppercase tracking-[0.06em] text-text-muted">
              Current values
            </div>
            <div className="mt-3 space-y-2">
              {emotionSchema.map((metric) => (
                <div key={metric.key} className="grid grid-cols-[7rem_1fr] items-center gap-3 text-xs">
                  <span className="text-text-muted">{metric.name}</span>
                  <Bar
                    value={Number(emotionState[metric.key] ?? metric.initial)}
                    min={metric.min}
                    max={metric.max}
                  />
                </div>
              ))}
            </div>

            <div className="mt-5 font-display text-[11px] uppercase tracking-[0.06em] text-text-muted">Schema</div>
            <div className="mt-2 grid grid-cols-[minmax(7rem,1fr)_5.5rem_5.5rem_5.5rem] gap-2 px-2 text-[10px] uppercase tracking-[0.08em] text-text-muted">
              <span>Metric</span>
              <span>Min</span>
              <span>Max</span>
              <span>Initial</span>
            </div>
            <div className="mt-1 space-y-1">
              {emotionSchema.map((metric, index) => (
                <div key={metric.key} className="grid grid-cols-[minmax(7rem,1fr)_5.5rem_5.5rem_5.5rem] items-center gap-2 border border-border/50 px-2 py-1.5 text-xs">
                  <div>
                    <div>{metric.name}</div>
                    <div className="font-mono text-[10px] text-text-muted">{metric.key}</div>
                  </div>
                  {(["min", "max", "initial"] as const).map((fieldName) => (
                    <input
                      key={fieldName}
                      type="number"
                      value={metric[fieldName]}
                      onChange={(event) => updateEmotionMetric(index, fieldName, event.currentTarget.valueAsNumber)}
                      data-testid={`emotion-${fieldName}-${metric.key}`}
                      aria-label={`${metric.name} ${fieldName}`}
                      className="h-8 w-full border border-border bg-bg px-2 font-mono"
                    />
                  ))}
                </div>
              ))}
            </div>
            {schemaError && (
              <div role="alert" className="mt-2 border-l-2 border-red-500 pl-3 text-xs text-red-500">
                {schemaError.name}: require min &lt; max and min &le; initial &le; max.
              </div>
            )}

            <div className="mt-5 font-display text-[11px] uppercase tracking-[0.06em] text-text-muted">Formulas</div>
            <p className="mt-1 text-[11px] text-text-muted">Leave blank to keep a metric static.</p>
            <div className="mt-2 space-y-1">
              {emotionSchema.map((metric) => (
                <div key={metric.key} className="grid grid-cols-[7rem_minmax(10rem,1fr)_4.5rem] items-center gap-2 text-xs">
                  <span>{metric.name}</span>
                  <input
                    value={emotionFormulas[metric.key] ?? ""}
                    onChange={(event) => updateFormula(metric.key, event.target.value)}
                    data-testid={`emotion-formula-${metric.key}`}
                    aria-label={`${metric.name} formula`}
                    placeholder="Static"
                    className="h-8 border border-border bg-bg px-2 font-mono"
                  />
                  <button
                    type="button"
                    onClick={() => onValidateFormula(metric.key)}
                    disabled={target.id === "new" || !emotionFormulas[metric.key]}
                    className="h-8 border border-border text-[11px] disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    Validate
                  </button>
                  {formulaStatus[metric.key] && (
                    <span className={`col-start-2 col-span-2 text-[11px] ${formulaStatus[metric.key].valid ? "text-green-500" : "text-red-500"}`}>
                      {formulaStatus[metric.key].valid ? "Valid" : formulaStatus[metric.key].error}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </details>
        </>
      )}
      {target.kind === "user" && (
        <>
          <Field label="Communication style">
            <input value={communicationStyle} onChange={(e) => setCommunicationStyle(e.target.value)} className="w-full px-2 h-9 bg-bg border border-border" />
          </Field>
          <Field label="Preferences (JSON)">
            <textarea value={preferencesJson} onChange={(e) => setPreferencesJson(e.target.value)} rows={4} className="w-full px-2 py-1 bg-bg border border-border font-mono text-xs" />
          </Field>
        </>
      )}

      {actionError && (
        <div role="alert" className="mt-4 border border-red-500 bg-red-500/10 px-3 py-2 text-xs text-red-500">
          {actionError}
        </div>
      )}
      <div className="flex gap-2 mt-6">
        <button disabled={busy || Boolean(schemaError)} onClick={onSave} className="px-4 h-9 bg-text text-surface text-[12px] font-semibold disabled:cursor-not-allowed disabled:opacity-40">
          {busy ? "Saving..." : "Save"}
        </button>
        <button disabled={busy} onClick={onDone} className="px-4 h-9 border border-border text-[12px] disabled:opacity-40">Cancel</button>
        {target.id !== "new" && (
          <button disabled={busy} onClick={onDelete} className="px-4 h-9 border border-red-500 text-red-500 text-[12px] disabled:opacity-40">Delete</button>
        )}
      </div>
    </div>
  );
}
