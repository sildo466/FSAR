// SPDX-License-Identifier: MIT
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, FolderLock } from "lucide-react";

import type { WorkspaceInfo } from "../../lib/ws-client";
import { useWS } from "../../stores/ws";
import { useWorkspace } from "../../stores/workspace";

/** A sandbox may not be a whole drive or the home directory itself: pointing a
 *  room at one of those would put the whole machine back inside the boundary. */
export function isRestrictedSandbox(workspace: WorkspaceInfo): boolean {
  const root = (workspace.root_path || "").replace(/\\/g, "/").replace(/\/+$/, "");
  if (!root) return false;
  if (/^[a-zA-Z]:$/.test(root)) return false;                   // "C:"
  if (/^[a-zA-Z]:\/Users\/[^/]+$/i.test(root)) return false;     // "C:/Users/TANG"
  if (/^\/home\/[^/]+$/.test(root)) return false;                // "/home/me"
  if (/^\/Users\/[^/]+$/.test(root)) return false;               // macOS "/Users/me"
  return true;
}

export function RoomSandboxPill({ roomId, sandboxWorkspaceId }: {
  roomId: number;
  sandboxWorkspaceId: number | null;
}) {
  const { t } = useTranslation();
  const send = useWS((state) => state.send);
  const workspaces = useWorkspace((state) => state.workspaces);
  const choices = workspaces.filter(isRestrictedSandbox);
  const active = choices.find((workspace) => workspace.id === sandboxWorkspaceId);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        data-testid="room-sandbox-pill"
        aria-label={t("roomSandbox.label")}
        title={active?.root_path ?? ""}
        onClick={() => setOpen((value) => !value)}
        className="flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1.5 font-mono text-[11px] text-text-muted transition hover:bg-glass hover:text-text"
      >
        <FolderLock size={13} strokeWidth={1.6} />
        <span className="max-w-[140px] truncate">{active?.name ?? "—"}</span>
        <ChevronDown size={12} />
      </button>
      {open && (
        <div className="absolute right-0 top-9 z-50 w-[300px] overflow-hidden rounded-2xl border border-border bg-surface-2 shadow-[0_18px_54px_var(--glow-faint)]">
          {choices.map((workspace) => (
            <button
              key={workspace.id}
              data-testid={`room-sandbox-option-${workspace.id}`}
              onClick={() => {
                send({
                  type: "group.update",
                  room_id: roomId,
                  sandbox_workspace_id: workspace.id,
                });
                setOpen(false);
              }}
              className="flex w-full flex-col items-start border-b border-border px-4 py-3 text-left last:border-0 hover:bg-glass"
            >
              <span className="text-[12px] font-medium">{workspace.name}</span>
              <span className="truncate font-mono text-[10px] text-text-muted">
                {workspace.root_path}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
