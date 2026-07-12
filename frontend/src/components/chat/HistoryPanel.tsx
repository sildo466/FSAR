// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { Pin, Pencil, Trash2, Plus, PanelRightClose, PanelRightOpen } from "lucide-react";
import { useSessions } from "../../stores/sessions";

interface Props {
  open: boolean;
  onToggle: () => void;
}

export function HistoryPanel({ open, onToggle }: Props) {
  const sessions = useSessions((s) => s.sessions);
  const currentId = useSessions((s) => s.currentId);
  const createNew = useSessions((s) => s.createNew);
  const switchTo = useSessions((s) => s.switchTo);
  const rename = useSessions((s) => s.rename);
  const togglePin = useSessions((s) => s.togglePin);
  const deleteOne = useSessions((s) => s.deleteOne);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState("");

  const sorted = [...sessions].sort((a, b) => {
    if (a.pinned !== b.pinned) return a.pinned ? -1 : 1;
    return b.updated_at.localeCompare(a.updated_at);
  });

  const handleRenameStart = (id: string, current: string) => {
    setEditingId(id);
    setEditingTitle(current);
  };

  const handleRenameCommit = () => {
    if (editingId && editingTitle.trim()) {
      rename(editingId, editingTitle.trim());
    }
    setEditingId(null);
    setEditingTitle("");
  };

  const handleDelete = (id: string, title: string) => {
    if (confirm(`Delete "${title || "Untitled"}"? This cannot be undone.`)) {
      deleteOne(id);
    }
  };

  return (
    <aside
      className={`glass m-0 ml-3 flex h-full shrink-0 flex-col overflow-hidden rounded-[24px] shadow-[0_12px_36px_var(--glow-faint)] transition-[width] duration-300 ${
        open ? "w-64" : "w-10"
      }`}
    >
      <div className="flex h-14 shrink-0 items-center justify-end px-3">
        {open && (
          <span className="font-display text-xs uppercase tracking-[0.1em] text-text-muted mr-auto pl-2">
            History
          </span>
        )}
        {open && (
          <button
            onClick={() => createNew()}
            className="rounded-full bg-text px-3 py-1.5 text-xs text-bg transition hover:scale-105"
            title="New conversation"
          >
            <Plus size={12} /> New
          </button>
        )}
        <button
          onClick={onToggle}
          className="ml-1 rounded-full p-2 text-text-muted transition hover:bg-glass hover:text-text"
          aria-label={open ? "Close history" : "Open history"}
          title={open ? "Close history" : "Open history"}
        >
          {open ? <PanelRightClose size={16} /> : <PanelRightOpen size={16} />}
        </button>
      </div>

      {open && (
        <div className="flex-1 overflow-y-auto">
          {sorted.length === 0 ? (
            <div className="px-4 py-8 text-text-muted text-xs text-center">
              No conversations yet.<br />Click + New to start.
            </div>
          ) : (
            <ul className="space-y-1 px-2 py-2">
              {sorted.map((s) => {
                const isActive = s.id === currentId;
                const isEditing = editingId === s.id;
                const titleDisplay = s.title || "Untitled";
                return (
                  <li
                    key={s.id}
                    className={`group relative rounded-2xl transition ${isActive ? "bg-glass shadow-[0_0_18px_var(--glow-faint)]" : "hover:bg-glass"}`}
                  >
                    <button
                      onClick={() => switchTo(s.id)}
                      className="w-full rounded-2xl px-3 py-2.5 pr-16 text-left"
                    >
                      <div className="flex items-center gap-1">
                        {s.pinned && <Pin size={10} className="text-text-muted shrink-0" />}
                        {isEditing ? (
                          <input
                            autoFocus
                            value={editingTitle}
                            onChange={(e) => setEditingTitle(e.target.value)}
                            onBlur={handleRenameCommit}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") handleRenameCommit();
                              if (e.key === "Escape") {
                                setEditingId(null);
                                setEditingTitle("");
                              }
                            }}
                            onClick={(e) => e.stopPropagation()}
                            className="glass flex-1 rounded-lg px-1 py-0.5 text-xs text-text"
                          />
                        ) : (
                          <span className="text-sm text-text truncate">{titleDisplay}</span>
                        )}
                      </div>
                      <div className="text-[10px] text-text-muted mt-0.5">
                        {s.message_count} msg · {fmtRelative(s.updated_at)}
                      </div>
                    </button>

                    <div className="absolute right-2 top-2 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          togglePin(s.id);
                        }}
                        className="p-1 rounded text-text-muted hover:text-text"
                        title={s.pinned ? "Unpin" : "Pin"}
                      >
                        <Pin size={12} className={s.pinned ? "fill-current" : ""} />
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleRenameStart(s.id, s.title);
                        }}
                        className="p-1 rounded text-text-muted hover:text-text"
                        title="Rename"
                      >
                        <Pencil size={12} />
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDelete(s.id, s.title);
                        }}
                        className="p-1 rounded text-text-muted hover:text-red-400"
                        title="Delete"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </aside>
  );
}

function fmtRelative(iso: string): string {
  try {
    const t = new Date(iso).getTime();
    const delta = Date.now() - t;
    if (delta < 60_000) return "just now";
    if (delta < 3_600_000) return `${Math.floor(delta / 60_000)}m ago`;
    if (delta < 86_400_000) return `${Math.floor(delta / 3_600_000)}h ago`;
    return `${Math.floor(delta / 86_400_000)}d ago`;
  } catch {
    return "";
  }
}
