// SPDX-License-Identifier: MIT
import { create } from "zustand";
import type {
  AgentMemberDetail,
  AuthAuditEvent,
  ClientMsg,
  ElectionCandidate,
  GroupMessage,
  LanBlockEntry,
  LanStatus,
  RoomSummary,
  ServerMsg,
  WSClient,
} from "../lib/ws-client";

import { applyToolEvent, asPreview } from "../lib/toolEvents";

interface GroupState {
  rooms: RoomSummary[];
  currentRoomId: number | null;
  messages: Record<number, GroupMessage[]>;
  /** Approvals waiting on the owner, per room. A character running tools in an
   *  agent room is the only thing that fills this. */
  pendingRisks: Record<number, PendingRisk[]>;
  elections: Record<number, ElectionCandidate[]>;
  chainRunning: Record<number, boolean>;
  loadingHistory: Record<number, boolean>;
  /** Per-room context gauge, fed by group.context (rooms have their own
   *  accounting so they never write over the single-chat readout). */
  context: Record<number, { used: number; window: number }>;
  /** Token metadata per room, keyed by member ref order as sent. Never holds a
   *  plaintext token — the issued event goes straight to a panel-local state. */
  agentMembers: Record<number, AgentMemberDetail[]>;
  /** Network access: the listener's state, blocked addresses, and the recent
   *  refusals that explain why a member cannot get in. */
  lan: {
    status: LanStatus | null;
    blocklist: LanBlockEntry[];
    audit: AuthAuditEvent[];
  };

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
    max_rounds?: number;
    agent_mode?: boolean;
    lan_enabled?: boolean;
  }) => void;
  updateRoom: (
    roomId: number,
    payload: {
      name?: string;
      description?: string;
      scenario_prompt?: string;
      user_card_id?: number | null;
      pinned?: boolean;
      /** 0 clears the cap, so the room debates until it settles. */
      max_rounds?: number;
    }
  ) => void;
  deleteRoom: (roomId: number) => void;
  addMembers: (roomId: number, characterIds: number[]) => void;
  removeMember: (roomId: number, characterId: number) => void;
  addAgentMember: (roomId: number, ref: string, displayName: string) => void;
  listAgentMembers: (roomId: number) => void;
  muteAgentMember: (roomId: number, ref: string, muted: boolean) => void;
  removeAgentMember: (roomId: number, ref: string) => void;
  issueMemberToken: (roomId: number, ref: string) => void;
  revokeMemberToken: (roomId: number, ref: string, tokenId: number) => void;
  unbanMemberToken: (roomId: number, ref: string, tokenId: number) => void;
  stopAllChains: () => void;
  refreshLanStatus: () => void;
  refreshLanBlocklist: () => void;
  refreshAuthAudit: (limit?: number) => void;
  blockIp: (ip: string, reason: string) => void;
  unblockIp: (ip: string) => void;
  rebindIp: (tokenId: number, ip: string) => void;
  rate: (roomId: number, rowId: number, score: number, reason?: string) => void;
  /** The room's own openness. Kept apart from the process-wide listener switch
   *  in LanPanel: one is a fact about this room, the other about the machine. */
  setRoomLan: (roomId: number, enabled: boolean) => void;
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
      // A call that produced nothing leaves no bubble at all.
      if (msg.failed) return live.filter((m) => m.id !== msg.message_id);
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
    case "chat.tool_call":
      return live.map((m) =>
        m.id === msg.message_id
          ? {
              ...m,
              tools: applyToolEvent(m.tools, {
                kind: "call", callId: msg.call_id, tool: msg.tool,
                args: msg.args,
              }),
            }
          : m
      );
    case "chat.tool_result":
      return live.map((m) =>
        m.tools?.some((t) => t.callId === msg.call_id)
          ? {
              ...m,
              tools: applyToolEvent(m.tools, {
                kind: "result", callId: msg.call_id, result: msg.result,
                latencyMs: msg.latency_ms,
              }),
            }
          : m
      );
    default:
      return live;
  }
}

export interface PendingRisk {
  callId: string;
  tool: string;
  argsPreview: string;
  risk: string;
}

/**
 * Approvals waiting on the owner for one room.
 *
 * Its own reducer rather than a branch of applyGroupEvent: that one is
 * (messages, event) -> messages, and this is a list of a different shape. The
 * room id is passed in because the event carries a conversation id, not a room
 * — whoever calls this has already resolved one to the other.
 */
export function applyRiskEvent(
  pending: Record<number, PendingRisk[]> | undefined,
  msg: ServerMsg,
  roomId: number
): Record<number, PendingRisk[]> {
  const current = pending ?? {};
  const queued = current[roomId] ?? [];
  if (msg.type === "chat.tool_call") {
    if (msg.risk === "SAFE") return current;
    return {
      ...current,
      [roomId]: [
        ...queued,
        {
          callId: msg.call_id,
          tool: msg.tool,
          argsPreview: asPreview(msg.args),
          risk: msg.risk,
        },
      ],
    };
  }
  if (msg.type === "chat.tool_result") {
    return {
      ...current,
      [roomId]: queued.filter((r) => r.callId !== msg.call_id),
    };
  }
  return current;
}

function roomIdForConversation(
  rooms: RoomSummary[],
  conversationId: string | undefined
): number | null {
  if (!conversationId) return null;
  const room = rooms.find((r) => r.session_id === conversationId);
  return room ? room.id : null;
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
    if (msg.type === "chat.tool_call" || msg.type === "chat.tool_result") {
      // A room is one conversation, so the conversation id in the payload is
      // enough to find the room and the message id is enough to find the
      // bubble — no new server field, whatever the room's member count.
      set((s) => {
        const roomId = roomIdForConversation(s.rooms, msg.conversation_id);
        if (roomId === null) return s;
        return {
          messages: {
            ...s.messages,
            [roomId]: applyGroupEvent(s.messages[roomId] ?? [], msg),
          },
          pendingRisks: applyRiskEvent(s.pendingRisks, msg, roomId),
        };
      });
    } else if (msg.type === "group.list.ok") {
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
    } else if (msg.type === "group.agent.list.ok") {
      set((s) => ({
        agentMembers: { ...s.agentMembers, [msg.room_id]: msg.agents },
      }));
    } else if (msg.type === "lan.status.ok") {
      const { type: _type, ...status } = msg;
      set((s) => ({ lan: { ...s.lan, status: status as LanStatus } }));
    } else if (msg.type === "lan.blocklist.ok") {
      set((s) => ({ lan: { ...s.lan, blocklist: msg.entries } }));
    } else if (msg.type === "auth_audit.list.ok") {
      set((s) => ({ lan: { ...s.lan, audit: msg.events } }));
    } else if (msg.type === "lan.error") {
      // Surfaced on the panel rather than swallowed: these are the errors a
      // user can act on (a bad address, a listener that would not start).
      set((s) => ({
        lan: {
          ...s.lan,
          status: s.lan.status
            ? { ...s.lan.status, error: msg.message }
            : s.lan.status,
        },
      }));
    } else if (msg.type === "group.deleted") {
      set((s) => {
        const { [msg.room_id]: _messages, ...messages } = s.messages;
        const { [msg.room_id]: _elections, ...elections } = s.elections;
        const { [msg.room_id]: _running, ...chainRunning } = s.chainRunning;
        const { [msg.room_id]: _gauge, ...context } = s.context;
        const { [msg.room_id]: _agents, ...agentMembers } = s.agentMembers;
        return {
          rooms: s.rooms.filter((r) => r.id !== msg.room_id),
          messages,
          elections,
          chainRunning,
          context,
          agentMembers,
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
      // Deliberately keep the previous round's candidates visible: clearing
      // here made the status strip blink away and back every round.
      set((s) => ({
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
    } else if (msg.type === "group.user_message") {
      const id = msg.message_id ?? `user_${msg.row_id ?? msg.content.length}`;
      const isAgent = msg.speaker_kind === "agent";
      set((s) => {
        const prior = s.messages[msg.room_id] ?? [];
        if (prior.some((m) => m.id === id)) return {};
        const entry: GroupMessage = {
          id,
          // An external member speaks on its own side of the transcript: same
          // side as the characters, named after the member.
          role: isAgent ? "assistant" : "user",
          content: msg.content,
          character_name: isAgent ? msg.user_name ?? undefined : undefined,
          user_name: isAgent ? undefined : msg.user_name ?? undefined,
          speaker_kind: isAgent ? "agent" : null,
          member_ref: msg.member_ref ?? undefined,
          row_id: msg.row_id ?? undefined,
        };
        return {
          messages: { ...s.messages, [msg.room_id]: [...prior, entry] },
        };
      });
    } else if (msg.type === "group.context") {
      set((s) => ({
        context: {
          ...s.context,
          [msg.room_id]: {
            used: msg.used_tokens,
            window: msg.window_tokens,
          },
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
    pendingRisks: {},
    elections: {},
    chainRunning: {},
    loadingHistory: {},
    context: {},
    agentMembers: {},
    lan: { status: null, blocklist: [], audit: [] },

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

    addAgentMember: (roomId, ref, displayName) =>
      attached?.send({
        type: "group.agent.add",
        room_id: roomId,
        ref,
        display_name: displayName,
      }),

    listAgentMembers: (roomId) =>
      attached?.send({ type: "group.agent.list", room_id: roomId }),

    muteAgentMember: (roomId, ref, muted) =>
      attached?.send({
        type: "group.agent.mute",
        room_id: roomId,
        member_ref: ref,
        muted,
      }),

    removeAgentMember: (roomId, ref) =>
      attached?.send({
        type: "group.agent.remove",
        room_id: roomId,
        member_ref: ref,
      }),

    issueMemberToken: (roomId, ref) =>
      attached?.send({
        type: "group.agent.token.issue",
        room_id: roomId,
        member_ref: ref,
      }),

    revokeMemberToken: (roomId, ref, tokenId) =>
      attached?.send({
        type: "group.agent.token.revoke",
        room_id: roomId,
        member_ref: ref,
        token_id: tokenId,
      }),

    unbanMemberToken: (roomId, ref, tokenId) =>
      attached?.send({
        type: "group.agent.token.unban",
        room_id: roomId,
        member_ref: ref,
        token_id: tokenId,
      }),

    stopAllChains: () => attached?.send({ type: "group.stop_all" }),

    setRoomLan: (roomId, enabled) =>
      attached?.send({
        type: "group.update",
        room_id: roomId,
        lan_enabled: enabled,
      }),

    refreshLanStatus: () => attached?.send({ type: "lan.status" }),

    refreshLanBlocklist: () => attached?.send({ type: "lan.blocklist" }),

    refreshAuthAudit: (limit) =>
      attached?.send({ type: "auth_audit.list", limit: limit ?? 100 }),

    blockIp: (ip, reason) => attached?.send({ type: "lan.block_ip", ip, reason }),

    unblockIp: (ip) => attached?.send({ type: "lan.unblock_ip", ip }),

    rebindIp: (tokenId, ip) =>
      attached?.send({ type: "lan.rebind_ip", token_id: tokenId, ip }),

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
