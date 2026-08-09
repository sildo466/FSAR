// SPDX-License-Identifier: MIT
import { useEffect, useMemo, useRef, useState } from "react";
import { FolderPlus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { open } from "@tauri-apps/plugin-dialog";
import { fetchWSToken, useWS } from "../stores/ws";

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
  const { t } = useTranslation();
  const send = useWS((s) => s.send);
  const client = useWS((s) => s.client);

  const [exps, setExps] = useState<Experience[]>([]);
  const [category, setCategory] = useState<string>("all");
  const [state, setState] = useState<StateFilter>("all");
  const [selected, setSelected] = useState<string | null>(null);
  const [learnOpen, setLearnOpen] = useState(false);
  const [installing, setInstalling] = useState(false);
  const [installMessage, setInstallMessage] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const [draft, setDraft] = useState({ name: "", category: "", description: "", body: "" });
  const folderInputRef = useRef<HTMLInputElement>(null);
  const isTauri = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

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

  const reportInstall = async (response: Response) => {
    const payload = await response.json().catch(() => ({})) as Record<string, unknown>;
    if (!response.ok) {
      throw new Error(typeof payload.detail === "string" ? payload.detail : `HTTP ${response.status}`);
    }
    setInstallMessage({
      kind: "success",
      text: t("library.installSuccess", { name: String(payload.name), scripts: Number(payload.scripts), references: Number(payload.references), templates: Number(payload.templates) }),
    });
  };

  const handleInstall = async () => {
    if (!isTauri) {
      folderInputRef.current?.click();
      return;
    }
    setInstallMessage(null);
    setInstalling(true);
    try {
      const folderPath = await open({ directory: true, multiple: false, title: t("library.installSkill") });
      if (typeof folderPath !== "string") return;
      const token = await fetchWSToken();
      const response = await fetch("/api/skill/install", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ folder_path: folderPath }),
      });
      await reportInstall(response);
    } catch (error) {
      setInstallMessage({
        kind: "error",
        text: t("library.installFailed", { error: error instanceof Error ? error.message : t("library.unknownError") }),
      });
    } finally {
      setInstalling(false);
    }
  };

  const handleFolderPicked = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setInstallMessage(null);
    setInstalling(true);
    try {
      const form = new FormData();
      for (const file of Array.from(files).slice(0, 200)) {
        const rel =
          (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name;
        form.append("files", file, rel);
      }
      const token = await fetchWSToken();
      const response = await fetch("/api/skill/install/upload", {
        method: "POST",
        credentials: "same-origin",
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      });
      await reportInstall(response);
    } catch (error) {
      setInstallMessage({
        kind: "error",
        text: t("library.installFailed", { error: error instanceof Error ? error.message : t("library.unknownError") }),
      });
    } finally {
      setInstalling(false);
    }
  };

  if (selectedExp) {
    return (
      <div className="max-w-[720px] mx-auto px-8 py-10 flex flex-col gap-6">
        <button
          onClick={() => setSelected(null)}
          className="self-start text-[13px] text-text-muted hover:text-text"
        >
          ← {t("library.title")}
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
            {t("library.usedFormat", { count: selectedExp.use_count })} · {t("library.lastPrefix")}{" "}
            {selectedExp.last_used_at ? new Date(selectedExp.last_used_at).toLocaleString() : t("library.never")}{" "}
            · {t("library.createdPrefix")} {new Date(selectedExp.created_at).toLocaleDateString()}
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
            {t("library.archive")}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-[720px] mx-auto px-8 py-10 flex flex-col gap-8">
      <input
        ref={folderInputRef}
        type="file"
        multiple
        className="hidden"
        {...({ webkitdirectory: "" } as Record<string, string>)}
        onChange={(e) => {
          void handleFolderPicked(e.target.files);
          e.target.value = "";
        }}
      />
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-[-0.01em]">{t("library.title")}</h1>
          <p className="text-text-muted">{t("library.subtitle")}</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleInstall}
            disabled={installing}
            className="px-3 h-8 rounded border border-border-strong text-[13px] inline-flex items-center gap-1.5 disabled:opacity-50"
          >
            <FolderPlus size={14} strokeWidth={1.5} />
            {installing ? t("library.installing") : t("library.installSkill")}
          </button>
          <button
            onClick={() => setLearnOpen(true)}
            className="px-3 h-8 rounded border border-border-strong text-[13px]"
          >
            + {t("library.learn")}
          </button>
        </div>
      </header>

      {installMessage && (
        <p
          role={installMessage.kind === "error" ? "alert" : "status"}
          className={`-mt-5 text-[12px] ${installMessage.kind === "error" ? "text-red-500" : "text-text-muted"}`}
        >
          {installMessage.text}
        </p>
      )}

      <div className="grid grid-cols-2 gap-6">
        <FilterGroup
          label={t("library.category")}
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
          label={t("library.state")}
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
          <p className="text-text-muted text-sm py-6">{t("library.noMatches")}</p>
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
