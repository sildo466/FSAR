// SPDX-License-Identifier: MIT
import { create } from "zustand";
import type {
  HardlineClassInfo,
  SandboxAuditEvent,
  SandboxEscapeRequest,
  SensitiveClassInfo,
  WorkspaceInfo,
  WSClient,
} from "../lib/ws-client";

interface WorkspaceState {
  workspaces: WorkspaceInfo[];
  currentBinding: { conversation_id: string; workspace: WorkspaceInfo } | null;
  bindings: Record<string, WorkspaceInfo>;
  defaultId: number | null;
  hardlineClasses: HardlineClassInfo[];
  sensitiveClasses: SensitiveClassInfo[];
  customSensitive: string[];
  auditEvents: SandboxAuditEvent[];
  escapeRequest: SandboxEscapeRequest | null;
  init: (client: WSClient) => () => void;
  clearEscape: () => void;
}

function replaceWorkspace(items: WorkspaceInfo[], workspace: WorkspaceInfo): WorkspaceInfo[] {
  const next = items.filter((item) => item.id !== workspace.id);
  return [...next, workspace].sort((a, b) => Number(b.default_for_new) - Number(a.default_for_new) || a.name.localeCompare(b.name));
}

export const useWorkspace = create<WorkspaceState>((set) => ({
  workspaces: [],
  currentBinding: null,
  bindings: {},
  defaultId: null,
  hardlineClasses: [],
  sensitiveClasses: [],
  customSensitive: [],
  auditEvents: [],
  escapeRequest: null,
  init: (client) => client.on((msg) => {
    if (msg.type === "snapshot") {
      set({
        workspaces: msg.workspace?.all_workspaces ?? [],
        currentBinding: msg.workspace?.current_binding ?? null,
        defaultId: msg.workspace?.default_workspace_id ?? null,
        hardlineClasses: msg.security?.hardline_classes ?? [],
        sensitiveClasses: msg.sensitive?.classes ?? [],
        customSensitive: msg.sensitive?.custom ?? [],
      });
    } else if (msg.type === "workspace.list_result") {
      set({ workspaces: msg.workspaces });
    } else if (msg.type === "workspace.created" || msg.type === "workspace.updated") {
      set((state) => ({ workspaces: replaceWorkspace(state.workspaces, msg.workspace) }));
    } else if (msg.type === "workspace.deleted") {
      set((state) => ({ workspaces: state.workspaces.filter((item) => item.id !== msg.id) }));
    } else if (msg.type === "workspace.default_changed") {
      set((state) => ({ defaultId: msg.id, workspaces: state.workspaces.map((item) => ({ ...item, default_for_new: item.id === msg.id })) }));
    } else if ((msg.type === "workspace.bound" || msg.type === "workspace.binding_changed") && msg.workspace) {
      set((state) => ({
        currentBinding: { conversation_id: msg.conversation_id, workspace: msg.workspace! },
        bindings: { ...state.bindings, [msg.conversation_id]: msg.workspace! },
      }));
    } else if (msg.type === "hardline.classes_result") {
      set({ hardlineClasses: msg.classes });
    } else if (msg.type === "sensitive.list_result") {
      set({ sensitiveClasses: msg.classes, customSensitive: msg.custom });
    } else if (msg.type === "sensitive.custom_added") {
      set((state) => ({ customSensitive: Array.from(new Set([...state.customSensitive, msg.pattern])) }));
    } else if (msg.type === "sensitive.custom_removed") {
      set((state) => ({ customSensitive: state.customSensitive.filter((item) => item !== msg.pattern) }));
    } else if (msg.type === "sandbox_audit.list_result") {
      set({ auditEvents: msg.events });
    } else if (msg.type === "tool.sandbox.request_escape") {
      set({ escapeRequest: msg });
    }
  }),
  clearEscape: () => set({ escapeRequest: null }),
}));
