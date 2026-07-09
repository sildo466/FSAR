// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { useCardsStore, type CardSummary, type UserCardSummary } from "../stores/cards";

type Tab = "character" | "user";
type EditorTarget = { kind: Tab; id: number | "new" } | null;

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

function Bar({ value, max, lo = 0, hi = 100 }: { value: number; max?: number; lo?: number; hi?: number }) {
  const range = max ?? (hi - lo);
  const pct = Math.max(0, Math.min(100, ((value - lo) / range) * 100));
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
  const [emotionState] = useState<Record<string, number>>(
    target.kind === "character" ? ((card as CardSummary | null)?.emotion_state ?? {}) : {}
  );
  const [emotionSchema] = useState<unknown[]>(
    target.kind === "character" ? ((card as CardSummary | null)?.emotion_schema ?? []) : []
  );
  const [emotionFormulas] = useState<Record<string, string>>(
    target.kind === "character" ? ((card as CardSummary | null)?.emotion_formulas ?? {}) : {}
  );
  const [formulaInput, setFormulaInput] = useState<Record<string, string>>({});
  const [formulaStatus, setFormulaStatus] = useState<Record<string, { valid: boolean; error?: string }>>({});

  const send = (msg: unknown) => {
    const w = window as unknown as { __WS?: { send: (m: unknown) => Promise<unknown> } };
    return w.__WS?.send(msg);
  };

  const onSave = async () => {
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
    await send({ type: "card.upsert", kind: target.kind, card });
    onDone();
  };

  const onDelete = async () => {
    if (target.id === "new") { onDone(); return; }
    if (!confirm(`Delete this ${target.kind} card?`)) return;
    await send({ type: "card.delete", kind: target.kind, id: target.id });
    onDone();
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
    await send({ type: "card.import_v2", json_text: text });
    onDone();
  };

  const onExport = async () => {
    if (target.id === "new") return;
    const res = (await send({ type: "card.export", id: target.id })) as { card: CardSummary };
    const blob = new Blob([JSON.stringify(res.card, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${name || "card"}.json`;
    a.click();
  };

  const onValidateFormula = async (key: string) => {
    if (target.id === "new") return;
    const res = (await send({
      type: "card.validate_formula",
      character_id: target.id,
      formula: formulaInput[key] ?? "",
    })) as { valid: boolean; error?: string | null };
    setFormulaStatus((s) => ({ ...s, [key]: { valid: res.valid, error: res.error ?? undefined } }));
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

          <details className="mt-4 border border-border p-3">
            <summary className="cursor-pointer font-display text-[12px] uppercase tracking-[0.06em]">
              Emotion (current values)
            </summary>
            <div className="mt-3 space-y-2">
              {Object.entries(emotionState).map(([key, value]) => (
                <div key={key} className="flex items-center gap-2 text-xs">
                  <span className="w-24 text-text-muted">{key}</span>
                  <Bar value={Number(value)} max={(emotionSchema as Array<{key: string; max: number; min?: number}>).find((m) => m.key === key)?.max ?? 100} />
                </div>
              ))}
            </div>

            <div className="mt-4 font-display text-[11px] uppercase tracking-[0.06em] text-text-muted">Schema</div>
            {(emotionSchema as Array<{key: string; name: string; min: number; max: number; initial: number}>).map((m) => (
              <div key={m.key} className="flex items-center gap-2 mt-1 text-xs">
                <span className="w-20">{m.name ?? m.key}</span>
                <span className="font-mono text-text-muted">[{m.min}..{m.max}] init {m.initial}</span>
              </div>
            ))}

            <div className="mt-4 font-display text-[11px] uppercase tracking-[0.06em] text-text-muted">Formulas</div>
            {Object.entries(emotionFormulas).map(([key, formula]) => (
              <div key={key} className="flex items-center gap-2 mt-1 text-xs">
                <span className="w-20">{key}</span>
                <input
                  value={formulaInput[key] ?? formula}
                  onChange={(e) => setFormulaInput((s) => ({ ...s, [key]: e.target.value }))}
                  className="flex-1 px-2 h-7 bg-bg border border-border font-mono"
                />
                <button onClick={() => onValidateFormula(key)} className="px-2 h-7 text-xs border border-border">
                  validate
                </button>
                <span className={formulaStatus[key]?.valid ? "text-green-500" : "text-red-500"}>
                  {formulaStatus[key] ? (formulaStatus[key].valid ? "✓" : `✗ ${formulaStatus[key].error}`) : ""}
                </span>
              </div>
            ))}
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

      <div className="flex gap-2 mt-6">
        <button onClick={onSave} className="px-4 h-9 bg-text text-surface text-[12px] font-semibold">Save</button>
        <button onClick={onDone} className="px-4 h-9 border border-border text-[12px]">Cancel</button>
        {target.id !== "new" && (
          <button onClick={onDelete} className="px-4 h-9 border border-red-500 text-red-500 text-[12px]">Delete</button>
        )}
      </div>
    </div>
  );
}
