// SPDX-License-Identifier: MIT
import { create } from "zustand";
import type {
  ClientMsg,
  ElectionCandidate,
  GroupMessage,
  RoomSummary,
  ServerMsg,
  WSClient,
} from "../lib/ws-client";

interface GroupState {
  rooms: RoomSummary[];
  currentRoomId: number | null;
  messages: Record<number, GroupMessage[]>;
  elections: Record<number, ElectionCandidate[]>;
  chainRunning: Record<number, boolean>;
  loadingHistory: Record<number, boolean>;

  init: (client: WSClient) => () => void;
  refreshRooms: () => void;
  openRoom: (roomId: number) => void;
  closeRoom: () => void;
  createRoom: (payload: {
    name: string;
    description?: string;
    scenario_prompt?: string;
    user_card_id?: number | null;
    character_ids: number[];
  }) => void;
  updateRoom: (
    roomId: number,
    payload: {
      name?: string;
      description?: string;
      scenario_prompt?: string;
      user_card_id?: number | null;
      pinned?: boolean;
    }
  ) => void;
  deleteRoom: (roomId: number) => void;
  addMembers: (roomId: number, characterIds: number[]) => void;
  removeMember: (roomId: number, characterId: number) => void;
  rate: (roomId: number, rowId: number, score: number, reason?: string) => void;
  regenerate: (roomId: number, rowId: number) => void;
  send: (msg: ClientMsg) => void;
  applyServerMsg: (msg: ServerMsg) => void;
}

export function applyGroupEvent(
  live: GroupMessage[],
  msg: ServerMsg
): GroupMessage[] {
  switch (msg.type) {
    case "group.speaker.start": {
      // A regenerate re-streams an existing row: same id, so reset it in place
      // instead of appending a second bubble.
      const incoming: GroupMessage = {
        id: msg.message_id,
        role: "assistant",
        content: "",
        character_id: msg.character_id ?? undefined,
        character_name: msg.character_name ?? undefined,
        streaming: true,
        thinking: false,
      };
      if (live.some((m) => m.id === msg.message_id)) {
        return live.map((m) =>
          m.id === msg.message_id
            ? { ...m, ...incoming, row_id: m.row_id }
            : m
        );
      }
      return [...live, incoming];
    }
    case "group.speaker.thinking":
      return live.map((m) =>
        m.id === msg.message_id ? { ...m, thinking: true } : m
      );
    case "group.speaker.delta":
      return live.map((m) =>
        m.id === msg.message_id
          ? {
              ...m,
              content: m.content + msg.content,
              thinking: false,
              streaming: true,
            }
          : m
      );
    case "group.speaker.done":
      return live.map((m) =>
        m.id === msg.message_id
          ? {
              ...m,
              streaming: false,
              thinking: false,
              // The server's text is authoritative: deltas were streamed before
              // the speaker marker was stripped / a failure suffix was added.
              content: msg.content ?? m.content,
              // The live message has no row id until the server reports one;
              // regenerate addresses rows, so without this a fresh reply
              // could not be regenerated at all.
              row_id: msg.row_id ?? m.row_id,
            }
          : m
      );
    default:
      return live;
  }
}

const LIVE_EVENTS = new Set([
  "group.speaker.start",
  "group.speaker.thinking",
  "group.speaker.delta",
  "group.speaker.done",
]);

export const useGroup = create<GroupState>((set, get) => {
  let attached: WSClient | null = null;

  const applyServerMsg = (msg: ServerMsg) => {
    if (msg.type === "group.list.ok") {
      set({ rooms: msg.rooms });
    } else if (msg.type === "group.created") {
      set((s) => ({
        rooms: [msg.room, ...s.rooms.filter((r) => r.id !== msg.room.id)],
        currentRoomId: msg.room.id,
      }));
    } else if (msg.type === "group.updated") {
      set((s) => ({
        rooms: s.rooms.map((r) => (r.id === msg.room.id ? msg.room : r)),
      }));
    } else if (msg.type === "group.deleted") {
      set((s) => {
        const { [msg.room_id]: _messages, ...messages } = s.messages;
        const { [msg.room_id]: _elections, ...elections } = s.elections;
        const { [msg.room_id]: _running, ...chainRunning } = s.chainRunning;
        return {
          rooms: s.rooms.filter((r) => r.id !== msg.room_id),
          messages,
          elections,
          chainRunning,
          currentRoomId:
            s.currentRoomId === msg.room_id ? null : s.currentRoomId,
        };
      });
    } else if (msg.type === "group.history.ok") {
      set((s) => ({
        messages: {
          ...s.messages,
          [msg.room_id]: msg.messages.map((m) => ({ ...m, streaming: false })),
        },
        loadingHistory: { ...s.loadingHistory, [msg.room_id]: false },
      }));
    } else if (msg.type === "group.elect.started") {
      set((s) => ({
        elections: { ...s.elections, [msg.room_id]: [] },
        chainRunning: { ...s.chainRunning, [msg.room_id]: true },
      }));
    } else if (msg.type === "group.elect.candidate") {
      const prior = get().elections[msg.room_id] ?? [];
      set((s) => ({
        elections: {
          ...s.elections,
          [msg.room_id]: [
            ...prior.filter((c) => c.character_id !== msg.character_id),
            {
              character_id: msg.character_id,
              character_name: msg.character_name,
              eagerness: msg.eagerness,
              reason: msg.reason,
            },
          ],
        },
      }));
    } else if (msg.type === "group.chain.finished") {
      set((s) => ({
        chainRunning: { ...s.chainRunning, [msg.room_id]: false },
      }));
    }
  };

  return {
    rooms: [],
    currentRoomId: null,
    messages: {},
    elections: {},
    chainRunning: {},
    loadingHistory: {},

    init: (client) => {
      attached = client;
      const detachA = client.on(applyServerMsg);
      const detachB = client.on((msg) => {
        if (!LIVE_EVENTS.has(msg.type)) return;
        const roomId = (msg as { room_id: number }).room_id;
        if (roomId == null) return;
        set((s) => ({
          messages: {
            ...s.messages,
            [roomId]: applyGroupEvent(s.messages[roomId] ?? [], msg),
          },
        }));
      });
      client.send({ type: "group.list" });
      return () => {
        detachA();
        detachB();
      };
    },

    refreshRooms: () => attached?.send({ type: "group.list" }),

    openRoom: (roomId) => {
      set((s) => ({
        currentRoomId: roomId,
        elections: { ...s.elections, [roomId]: [] },
        loadingHistory: { ...s.loadingHistory, [roomId]: true },
      }));
      attached?.send({ type: "group.history", room_id: roomId });
    },

    closeRoom: () => set({ currentRoomId: null }),

    createRoom: (payload) => attached?.send({ type: "group.create", ...payload }),

    updateRoom: (roomId, payload) =>
      attached?.send({ type: "group.update", room_id: roomId, ...payload }),

    deleteRoom: (roomId) =>
      attached?.send({ type: "group.delete", room_id: roomId }),

    addMembers: (roomId, characterIds) =>
      attached?.send({
        type: "group.members.add",
        room_id: roomId,
        character_ids: characterIds,
      }),

    removeMember: (roomId, characterId) =>
      attached?.send({
        type: "group.members.remove",
        room_id: roomId,
        character_id: characterId,
      }),

    rate: (roomId, rowId, score, reason) =>
      attached?.send({
        type: "group.rate",
        room_id: roomId,
        message_id: rowId,
        score,
        reason,
      }),

    regenerate: (roomId, rowId) =>
      attached?.send({
        type: "group.regenerate",
        room_id: roomId,
        message_id: rowId,
      }),

    send: (msg) => attached?.send(msg),

    applyServerMsg,
  };
});
