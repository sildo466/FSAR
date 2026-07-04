// SPDX-License-Identifier: Apache-2.0
import { useEffect, useMemo, useState } from "react";
import { useWS } from "../stores/ws";

interface Experience {
  id?: number;
  name: string;
  category: string;
  description: string;
  body: string;
  use_count: number;
  last_used_at: string | null;
  state: string;
  pinned: boolean;
  created_at: string;
}

const STATES = ["all", "active", "stale", "archived"] as const;
type StateFilter = (typeof STATES)[number];

export function Library() {
  const send = useWS((s) => s.send);
  const client = useWS((s) => s.client);

  const [exps, setExps] = useState<Experience[]>([]);
  const [category, setCategory] = useState<string>("all");
  const [state, setState] = useState<StateFilter>("all");
  const [selected, setSelected] = useState<string | null>(null);
  const [learnOpen, setLearnOpen] = useState(false);
  const [draft, setDraft] = useState({ name: "", category: "", description: "", body: "" });

  useEffect(() => {
    send({ type: "library.list" });
  }, [send]);

  useEffect(() => {
    return client?.on((msg) => {
      if (msg.type === "library.list_result") {
        setExps(msg.experiences as unknown as Experience[]);
      } else if (msg.type === "library.changed") {
        send({ type: "library.list" });
      }
    });
  }, [client, send]);

  const categories = useMemo(() => {
    const set = new Set(exps.map((e) => e.category).filter(Boolean));
    return ["all", ...Array.from(set).sort()];
  }, [exps]);

  const filtered = useMemo(() => {
    return exps.filter((e) => {
      if (category !== "all" && e.category !== category) return false;
      if (state !== "all" && e.state !== state) return false;
      return true;
    });
  }, [exps, category, state]);

  const selectedExp = selected ? exps.find((e) => e.name === selected) ?? null : null;

  const handleLearnSave = () => {
    const name = draft.name.trim();
    const cat = draft.category.trim();
    const body = draft.body.trim();
    if (!name || !cat || !body) return;
    send({
      type: "library.create",
      name,
      category: cat,
      description: draft.description,
      body,
      created_by: "user",
    });
    setDraft({ name: "", category: "", description: "", body: "" });
    setLearnOpen(false);
  };

  if (selectedExp) {
    return (
      <div className="max-w-[720px] mx-auto px-8 py-10 flex flex-col gap-6">
        <button
          onClick={() => setSelected(null)}
          className="self-start text-[13px] text-text-muted hover:text-text"
        >
          ← Library
        </button>
        <header>
          <div className="flex items-center gap-3">
            <h1 className="font-display text-2xl font-semibold">#{selectedExp.name}</h1>
            <span className="text-text-muted text-sm">{selectedExp.category}</span>
            {selectedExp.pinned && <span aria-label="pinned">📌</span>}
          </div>
          {selectedExp.description && (
            <p className="text-text-muted mt-1">{selectedExp.description}</p>
          )}
          <p className="font-mono text-xs text-text-muted mt-2">
            used {selectedExp.use_count}× · last{" "}
            {selectedExp.last_used_at ? new Date(selectedExp.last_used_at).toLocaleString() : "never"}{" "}
            · created {new Date(selectedExp.created_at).toLocaleDateString()}
          </p>
        </header>
        <section className="border border-border rounded p-4">
          <pre className="font-mono text-[13px] whitespace-pre-wrap">{selectedExp.body}</pre>
        </section>
        <div className="flex gap-2 justify-end">
          <button
            onClick={() => send({ type: "library.archive", name: selectedExp.name })}
            className="px-3 h-8 rounded border border-border text-[12px]"
          >
            Archive
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-[720px] mx-auto px-8 py-10 flex flex-col gap-8">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-[-0.01em]">Library</h1>
          <p className="text-text-muted">Procedures and skills FSAR has learned</p>
        </div>
        <button
          onClick={() => setLearnOpen(true)}
          className="px-3 h-8 rounded border border-border-strong text-[13px]"
        >
          + Learn
        </button>
      </header>

      <div className="grid grid-cols-2 gap-6">
        <FilterGroup
          label="Category"
          options={categories}
          value={category}
          onChange={setCategory}
          counts={Object.fromEntries(
            categories.map((c) => [
              c,
              c === "all" ? exps.length : exps.filter((e) => e.category === c).length,
            ])
          )}
        />
        <FilterGroup
          label="State"
          options={STATES as unknown as string[]}
          value={state}
          onChange={(v) => setState(v as StateFilter)}
          counts={Object.fromEntries(
            STATES.map((s) => [
              s,
              s === "all" ? exps.length : exps.filter((e) => e.state === s).length,
            ])
          )}
        />
      </div>

      <section className="flex flex-col divide-y divide-border">
        {filtered.length === 0 ? (
          <p className="text-text-muted text-sm py-6">No experiences match.</p>
        ) : (
          filtered.map((e) => (
            <button
              key={e.name}
              onClick={() => setSelected(e.name)}
              className="text-left py-4 flex flex-col gap-1 hover:bg-bg px-2 -mx-2 rounded"
            >
              <div className="flex items-center gap-3">
                <span className="font-mono text-[13px] font-medium">#{e.name}</span>
                <span className="text-text-muted text-[12px]">{e.category}</span>
                {e.pinned && <span aria-label="pinned">📌</span>}
                {e.state === "stale" && (
                  <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-text-muted">
                    [stale]
                  </span>
                )}
                {e.state === "archived" && (
                  <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-text-muted">
                    [archived]
                  </span>
                )}
              </div>
              {e.description && <p className="text-sm text-text-muted">{e.description}</p>}
              <p className="font-mono text-[11px] text-text-muted">
                used {e.use_count}× · last{" "}
                {e.last_used_at ? new Date(e.last_used_at).toLocaleString() : "never"}
              </p>
            </button>
          ))
        )}
      </section>

      {learnOpen && (
        <div
          className="fixed inset-0 bg-black/40 flex items-center justify-center z-50"
          onClick={() => setLearnOpen(false)}
        >
          <div
            className="w-[80vw] max-w-[640px] bg-surface border border-border rounded p-6 flex flex-col gap-3"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="font-display text-lg font-semibold">Learn a new experience</h2>
            <label className="flex flex-col gap-1 text-[12px] text-text-muted">
              Name
              <input
                value={draft.name}
                onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))}
                className="h-8 px-2 bg-bg border border-border rounded text-[13px] text-text"
              />
            </label>
            <label className="flex flex-col gap-1 text-[12px] text-text-muted">
              Category
              <input
                value={draft.category}
                onChange={(e) => setDraft((d) => ({ ...d, category: e.target.value }))}
                placeholder="e.g. file-mgmt"
                className="h-8 px-2 bg-bg border border-border rounded text-[13px] text-text"
              />
            </label>
            <label className="flex flex-col gap-1 text-[12px] text-text-muted">
              Description
              <input
                value={draft.description}
                onChange={(e) => setDraft((d) => ({ ...d, description: e.target.value }))}
                className="h-8 px-2 bg-bg border border-border rounded text-[13px] text-text"
              />
            </label>
            <label className="flex flex-col gap-1 text-[12px] text-text-muted">
              Body (markdown)
              <textarea
                value={draft.body}
                onChange={(e) => setDraft((d) => ({ ...d, body: e.target.value }))}
                rows={8}
                placeholder="## Goal&#10;..."
                className="px-2 py-1 bg-bg border border-border rounded text-[13px] text-text font-mono resize-none"
              />
            </label>
            <div className="flex gap-2 justify-end pt-2">
              <button
                onClick={() => {
                  setLearnOpen(false);
                  setDraft({ name: "", category: "", description: "", body: "" });
                }}
                className="px-3 h-8 rounded border border-border text-[12px]"
              >
                Cancel
              </button>
              <button
                onClick={handleLearnSave}
                className="px-3 h-8 rounded border border-border-strong bg-text text-surface text-[12px]"
              >
                Save
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function FilterGroup({
  label,
  options,
  value,
  onChange,
  counts,
}: {
  label: string;
  options: string[];
  value: string;
  onChange: (v: string) => void;
  counts: Record<string, number>;
}) {
  return (
    <div>
      <div className="font-display text-[10px] font-bold uppercase tracking-[0.1em] text-text-muted mb-2">
        {label}
      </div>
      <ul className="flex flex-col gap-1">
        {options.map((o) => (
          <li key={o}>
            <button
              onClick={() => onChange(o)}
              className="flex items-center gap-2 text-[13px] text-left"
            >
              <span
                className={`inline-block w-3 h-3 border border-border-strong ${
                  value === o ? "bg-text" : ""
                }`}
              />
              <span>{o}</span>
              <span className="font-mono text-[11px] text-text-muted">{counts[o] ?? 0}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}