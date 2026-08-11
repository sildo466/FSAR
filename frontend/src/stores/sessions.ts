// SPDX-License-Identifier: MIT
import { create } from "zustand";
import type { ClientMsg, ServerMsg, SessionMeta, StoredMessage } from "../lib/ws-client";
import type { ChatMessage } from "../components/chat/MessageList";
import { WSClient } from "../lib/ws-client";
import { useCardsStore } from "./cards";

const LS_KEY = "fsar.currentConversationId";

interface SessionsState {
  sessions: SessionMeta[];
  currentId: string | null;
  history: Record<string, StoredMessage[]>;
  loadingHistory: boolean;
  listLoaded: boolean;
  // Live UI messages as they streamed in — kept so navigating away and back
  // to the same conversation restores the full stream (the backend only
  // persists a plain-text summary, not the agent's tool-call progress).
  liveHistory: Record<string, ChatMessage[]>;

  init: (client: WSClient) => () => void;
  setCurrent: (id: string | null) => void;
  refreshList: () => void;
  fetchHistory: (id: string) => void;
  createNew: () => void;
  switchTo: (id: string) => void;
  rename: (id: string, title: string) => void;
  togglePin: (id: string) => void;
  deleteOne: (id: string) => void;
  syncLive: (convId: string, msgs: ChatMessage[]) => void;

  send: (msg: ClientMsg) => void;
  applyServerMsg: (msg: ServerMsg) => void;
}

function loadSavedId(): string | null {
  try {
    return localStorage.getItem(LS_KEY);
  } catch {
    return null;
  }
}

function saveId(id: string | null) {
  try {
    if (id) localStorage.setItem(LS_KEY, id);
    else localStorage.removeItem(LS_KEY);
  } catch {
    /* ignore */
  }
}

export const useSessions = create<SessionsState>((set, get) => {
  let attached: WSClient | null = null;
  let detach: (() => void) | null = null;

  const applyServerMsg = (msg: ServerMsg) => {
    if (msg.type === "conversation.list") {
      const incoming = msg.sessions;
      const savedId = loadSavedId();
      const state = get();
      set({ sessions: incoming, listLoaded: true });

      // Auto-pick a conversation: prefer localStorage saved id if it
      // still exists; otherwise the most recently updated session.
      // Only on the first list load — later refreshes (reconnect, draft
      // canvas after createNew) must not steal the current selection.
      if (!state.listLoaded && state.currentId == null && incoming.length > 0) {
        const target =
          (savedId && incoming.find((s) => s.id === savedId)?.id) ||
          incoming[0].id;
        attached?.send({ type: "conversation.switch", conversation_id: target });
        attached?.send({
          type: "conversation.history",
          conversation_id: target,
          limit: 100,
        });
      } else if (state.currentId == null && incoming.length === 0) {
        // Don't auto-create on empty list. Stay on the welcome canvas;
        // chat_engine.handle_send creates a session lazily on the first
        // user message. Avoids ghost "untitled" rows appearing in the
        // history panel before the user has actually said anything.
      }
    } else if (msg.type === "conversation.created") {
      set((s) => ({
        sessions: [msg.session, ...s.sessions.filter((x) => x.id !== msg.session.id)],
        currentId: msg.session.id,
        history: { ...s.history, [msg.session.id]: s.history[msg.session.id] ?? [] },
      }));
      saveId(msg.session.id);
    } else if (msg.type === "conversation.switched") {
      set({ currentId: msg.conversation_id });
      saveId(msg.conversation_id);
      if (get().history[msg.conversation_id] === undefined) {
        attached?.send({
          type: "conversation.history",
          conversation_id: msg.conversation_id,
          limit: 100,
        });
      }
    } else if (msg.type === "conversation.history") {
      set((s) => ({
        history: { ...s.history, [msg.conversation_id]: msg.messages },
        loadingHistory: false,
      }));
    } else if (msg.type === "conversation.title_updated") {
      set((s) => ({
        sessions: s.sessions.map((x) =>
          x.id === msg.conversation_id ? { ...x, title: msg.title } : x
        ),
      }));
    } else if (msg.type === "conversation.updated") {
      set((s) => ({
        sessions: s.sessions.map((x) =>
          x.id === msg.session.id ? msg.session : x
        ),
      }));
    } else if (msg.type === "conversation.deleted") {
      const { [msg.conversation_id]: _drop, ...rest } = get().history;
      const { [msg.conversation_id]: _dropLive, ...liveRest } = get().liveHistory;
      set((s) => {
        const nextCurrent =
          s.currentId === msg.conversation_id ? null : s.currentId;
        if (nextCurrent == null) saveId(null);
        return {
          sessions: s.sessions.filter((x) => x.id !== msg.conversation_id),
          history: rest,
          liveHistory: liveRest,
          currentId: nextCurrent,
        };
      });
    }
  };

  return {
    sessions: [],
    currentId: null,
    history: {},
    loadingHistory: false,
    listLoaded: false,
    liveHistory: {},

    init: (client) => {
      attached = client;
      detach = client.on(applyServerMsg);
      // The server pushes conversation.list once, at connect time. If we
      // attached after that push (app booted on a non-chat route, or the
      // socket reconnected), ask for it again — otherwise the store stays
      // empty and the chat canvas loses its conversation and character.
      if (!get().listLoaded) client.send({ type: "conversation.list" });
      return detach;
    },

    setCurrent: (id) => {
      set({ currentId: id });
      saveId(id);
    },

    refreshList: () => attached?.send({ type: "conversation.list" }),

    fetchHistory: (id) => {
      if (get().history[id] !== undefined) return;
      set({ loadingHistory: true });
      attached?.send({
        type: "conversation.history",
        conversation_id: id,
        limit: 100,
      });
    },

    createNew: () => {
      const prevId = get().currentId;
      const prevCharacter = prevId
        ? useCardsStore.getState().sessionCharacters[prevId] ?? null
        : null;
      if (prevCharacter != null) {
        useCardsStore.getState().setDraftCharacter(prevCharacter);
      }
      set({ currentId: null, loadingHistory: false });
      saveId(null);
    },

    switchTo: (id) => {
      set({ currentId: id, loadingHistory: true });
      saveId(id);
      attached?.send({ type: "conversation.switch", conversation_id: id });
      attached?.send({
        type: "conversation.history",
        conversation_id: id,
        limit: 100,
      });
    },

    rename: (id, title) =>
      attached?.send({ type: "conversation.rename", conversation_id: id, title }),

    togglePin: (id) => {
      const s = get().sessions.find((x) => x.id === id);
      if (s)
        attached?.send({
          type: "conversation.pin",
          conversation_id: id,
          pinned: !s.pinned,
        });
    },

    deleteOne: (id) =>
      attached?.send({ type: "conversation.delete", conversation_id: id }),

    syncLive: (convId, msgs) => {
      if (!convId) return;
      set((s) => ({ liveHistory: { ...s.liveHistory, [convId]: msgs } }));
    },

    send: (msg) => attached?.send(msg),

    applyServerMsg,
  };
});
