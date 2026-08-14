// SPDX-License-Identifier: MIT
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { ChevronDown, FolderLock, ShieldCheck } from "lucide-react";
import { useSessions } from "../../stores/sessions";
import { useWorkspace } from "../../stores/workspace";
import { useWS } from "../../stores/ws";

export function WorkspacePill() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const currentId = useSessions((state) => state.currentId);
  const workspaces = useWorkspace((state) => state.workspaces);
  const binding = useWorkspace((state) => state.currentBinding);
  const pendingWorkspaceId = useWorkspace((state) => state.pendingWorkspaceId);
  const setPendingWorkspace = useWorkspace((state) => state.setPendingWorkspace);
  const send = useWS((state) => state.send);
  const active = binding?.conversation_id === currentId
    ? binding.workspace
    : pendingWorkspaceId != null
      ? workspaces.find((w) => w.id === pendingWorkspaceId) ?? null
      : null;

  useEffect(() => {
    if (currentId) send({ type: "workspace.get_binding", conversation_id: currentId });
  }, [currentId, send]);
  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => { if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  function select(workspaceId: number) {
    if (currentId) {
      send({ type: "workspace.switch_binding", conversation_id: currentId, workspace_id: workspaceId });
    } else {
      setPendingWorkspace(workspaceId);
    }
    setOpen(false);
  }

  return (
    <div ref={ref} className="relative">
      <button onClick={() => setOpen((value) => !value)} title={active?.root_path ?? t("workspacePill.noActive")} className="glass flex h-8 max-w-[210px] items-center gap-2 rounded-full px-3 text-[12px] transition hover:bg-glass-strong disabled:opacity-45">
        <FolderLock size={13} />
        <span className="truncate font-mono">{active?.name ?? t("workspacePill.sandbox")}</span>
        <ChevronDown size={12} />
      </button>
      {open && (
        <div className="glass-strong absolute right-0 top-10 z-50 w-[310px] overflow-hidden rounded-2xl shadow-[0_18px_54px_var(--glow-faint)]">
          <div className="border-b border-border px-4 py-3"><p className="font-mono text-[10px] uppercase tracking-[0.16em] text-text-muted">{t("workspacePill.title")}</p></div>
          {workspaces.map((workspace) => (
            <button key={workspace.id} onClick={() => select(workspace.id)} className="flex w-full items-start gap-3 border-b border-border px-4 py-3 text-left last:border-0 hover:bg-glass">
              <ShieldCheck size={15} className={workspace.id === active?.id ? "mt-0.5 text-success" : "mt-0.5 text-text-faint"} />
              <span className="min-w-0"><span className="block text-[12px] font-medium">{workspace.name}</span><span className="block truncate font-mono text-[10px] text-text-muted">{workspace.root_path}</span></span>
            </button>
          ))}
          <Link to="/settings/workspace" className="block px-4 py-3 text-[11px] text-text-muted hover:text-text">{t("workspacePill.manage")} →</Link>
        </div>
      )}
    </div>
  );
}
