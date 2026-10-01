// SPDX-License-Identifier: MIT
import { beforeEach, describe, expect, it } from "vitest";
import { applyGroupEvent, applyRiskEvent, useGroup } from "./group";
import type { GroupMessage, RoomSummary } from "../lib/ws-client";

function assistant(id: string, characterId: number, name: string): GroupMessage {
  return {
    id,
    role: "assistant",
    content: "",
    character_id: characterId,
    character_name: name,
  };
}

const emptyState = {
  rooms: [],
  currentRoomId: null,
  messages: {},
  pendingRisks: {},
  elections: {},
  chainRunning: {},
  loadingHistory: {},
  context: {},
  agentMembers: {},
};

describe("applyGroupEvent", () => {
  it("appends a new speaker message on speaker.start", () => {
    const next = applyGroupEvent([], {
      type: "group.speaker.start",
      room_id: 1,
      message_id: "m1",
      character_id: 7,
      character_name: "Mira",
    });
    expect(next).toHaveLength(1);
    expect(next[0]).toMatchObject({
      id: "m1",
      role: "assistant",
      character_id: 7,
      character_name: "Mira",
      streaming: true,
    });
  });

  it("resets an existing message in place on speaker.start", () => {
    // A regenerate re-streams the same row, so the bubble must be overwritten
    // rather than duplicated or appended to.
    const live = [{ ...assistant("42", 7, "Mira"), content: "old text", row_id: 42 }];
    const next = applyGroupEvent(live, {
      type: "group.speaker.start",
      room_id: 1,
      message_id: "42",
      character_id: 7,
      character_name: "Mira",
    });
    expect(next).toHaveLength(1);
    expect(next[0].content).toBe("");
    expect(next[0].streaming).toBe(true);
    expect(next[0].row_id).toBe(42);
  });

  it("appends a distinct speaker message", () => {
    const live = [assistant("m1", 7, "Mira")];
    const next = applyGroupEvent(live, {
      type: "group.speaker.start",
      room_id: 1,
      message_id: "m2",
      character_id: 8,
      character_name: "Kai",
    });
    expect(next).toHaveLength(2);
    expect(next[1].id).toBe("m2");
  });

  it("accumulates deltas into the matching message", () => {
    const live = [assistant("m1", 7, "Mira")];
    const next = applyGroupEvent(live, {
      type: "group.speaker.delta",
      room_id: 1,
      message_id: "m1",
      content: "Hello",
    });
    expect(next[0].content).toBe("Hello");
    expect(next[0].streaming).toBe(true);
  });

  it("ignores deltas for unknown message ids", () => {
    const next = applyGroupEvent([], {
      type: "group.speaker.delta",
      room_id: 1,
      message_id: "nope",
      content: "x",
    });
    expect(next).toHaveLength(0);
  });

  it("clears streaming on speaker.done", () => {
    const live = [
      { ...assistant("m1", 7, "Mira"), content: "hi", streaming: true },
    ];
    const next = applyGroupEvent(live, {
      type: "group.speaker.done",
      room_id: 1,
      message_id: "m1",
    });
    expect(next[0].streaming).toBe(false);
  });

  it("records the row id reported on speaker.done", () => {
    // Without it a reply produced in this session has no row id, and
    // regenerate (which addresses rows) silently does nothing.
    const live = [{ ...assistant("m1", 7, "Mira"), streaming: true }];
    const next = applyGroupEvent(live, {
      type: "group.speaker.done",
      room_id: 1,
      message_id: "m1",
      row_id: 77,
    });
    expect(next[0].row_id).toBe(77);
  });

  it("takes the server's final text on speaker.done", () => {
    // Deltas stream before the speaker marker is stripped, so the done event
    // is authoritative for what is actually stored.
    const live = [
      {
        ...assistant("m1", 7, "Mira"),
        content: "[Mira]: hello there",
        streaming: true,
      },
    ];
    const next = applyGroupEvent(live, {
      type: "group.speaker.done",
      room_id: 1,
      message_id: "m1",
      content: "hello there",
    });
    expect(next[0].content).toBe("hello there");
  });

  it("drops the bubble when the speaker produced nothing", () => {
    const live = [{ ...assistant("m1", 7, "Mira"), streaming: true }];
    const next = applyGroupEvent(live, {
      type: "group.speaker.done",
      room_id: 1,
      message_id: "m1",
      failed: true,
    });
    expect(next).toHaveLength(0);
  });

  it("ignores unrelated events", () => {
    const live = [assistant("m1", 7, "Mira")];
    const next = applyGroupEvent(live, { type: "heartbeat", ts: 0 });
    expect(next).toBe(live);
  });
});

describe("useGroup store", () => {
  beforeEach(() => {
    useGroup.setState(emptyState);
  });

  it("stores the room list", () => {
    useGroup.getState().applyServerMsg({
      type: "group.list.ok",
      rooms: [
        {
          id: 1,
          name: "Island",
          description: "",
          scenario_prompt: "",
          session_id: "s1",
          user_card_id: null,
          pinned: false,
          max_rounds: 0,
          created_at: "",
          updated_at: "",
          members: [7],
          agent_members: [],
          agent_mode: false,
          lan_enabled: false,
          workspace_id: null,
          goal: "",
          phase: "chat",
        },
      ],
    });
    expect(useGroup.getState().rooms).toHaveLength(1);
  });

  it("switches to a newly created room", () => {
    useGroup.getState().applyServerMsg({
      type: "group.created",
      room: {
        id: 5,
        name: "New",
        description: "",
        scenario_prompt: "",
        session_id: "s5",
        user_card_id: null,
        pinned: false,
        max_rounds: 0,
        created_at: "",
        updated_at: "",
        members: [7, 8],
        agent_members: [],
        agent_mode: false,
        lan_enabled: false,
        workspace_id: null,
        goal: "",
        phase: "chat",
      },
    });
    expect(useGroup.getState().currentRoomId).toBe(5);
  });

  it("drops a deleted room and its live state", () => {
    useGroup.setState({
      ...emptyState,
      rooms: [
        {
          id: 3,
          name: "R",
          description: "",
          scenario_prompt: "",
          session_id: "s3",
          user_card_id: null,
          pinned: false,
          max_rounds: 0,
          created_at: "",
          updated_at: "",
          members: [7],
          agent_members: [],
          agent_mode: false,
          lan_enabled: false,
          workspace_id: null,
          goal: "",
          phase: "chat",
        },
      ],
      currentRoomId: 3,
      messages: { 3: [assistant("m1", 7, "Mira")] },
    });
    useGroup.getState().applyServerMsg({ type: "group.deleted", room_id: 3 });
    const state = useGroup.getState();
    expect(state.rooms).toHaveLength(0);
    expect(state.currentRoomId).toBeNull();
    expect(state.messages[3]).toBeUndefined();
  });

  it("merges updated rooms in place", () => {
    useGroup.setState({
      ...emptyState,
      rooms: [
        {
          id: 4,
          name: "Before",
          description: "",
          scenario_prompt: "",
          session_id: "s4",
          user_card_id: null,
          pinned: false,
          max_rounds: 0,
          created_at: "",
          updated_at: "",
          members: [7],
          agent_members: [],
          agent_mode: false,
          lan_enabled: false,
          workspace_id: null,
          goal: "",
          phase: "chat",
        },
      ],
    });
    useGroup.getState().applyServerMsg({
      type: "group.updated",
      room: {
        id: 4,
        name: "After",
        description: "",
        scenario_prompt: "",
        session_id: "s4",
        user_card_id: null,
        pinned: true,
        max_rounds: 0,
        created_at: "",
        updated_at: "",
        members: [7, 8],
        agent_members: [],
        agent_mode: false,
        lan_enabled: false,
        workspace_id: null,
        goal: "",
        phase: "chat",
      },
    });
    expect(useGroup.getState().rooms[0].name).toBe("After");
    expect(useGroup.getState().rooms[0].members).toEqual([7, 8]);
  });

  it("stores history messages as non streaming", () => {
    useGroup.getState().applyServerMsg({
      type: "group.history.ok",
      room_id: 1,
      messages: [{ ...assistant("11", 7, "Mira"), row_id: 11, streaming: true }],
    });
    const stored = useGroup.getState().messages[1];
    expect(stored).toHaveLength(1);
    expect(stored[0].streaming).toBe(false);
    expect(stored[0].row_id).toBe(11);
  });

  it("collects election candidates one by one", () => {
    useGroup.getState().applyServerMsg({
      type: "group.elect.started",
      room_id: 1,
      chain_id: "c1",
      round: 1,
      candidates: [7, 8],
    });
    expect(useGroup.getState().chainRunning[1]).toBe(true);
    // The strip must not blank out here — see the "keeps the previous round's
    // candidates" regression test below.
    expect(useGroup.getState().elections[1]).toBeUndefined();

    useGroup.getState().applyServerMsg({
      type: "group.elect.candidate",
      room_id: 1,
      chain_id: "c1",
      round: 1,
      character_id: 7,
      character_name: "Mira",
      eagerness: 8,
      reason: "wants to speak",
    });
    expect(useGroup.getState().elections[1]).toEqual([
      {
        character_id: 7,
        character_name: "Mira",
        eagerness: 8,
        reason: "wants to speak",
      },
    ]);
  });

  it("replaces a repeated candidate instead of duplicating it", () => {
    const start = {
      type: "group.elect.started" as const,
      room_id: 1,
      chain_id: "c1",
      round: 1,
      candidates: [7],
    };
    useGroup.getState().applyServerMsg(start);
    const candidate = {
      type: "group.elect.candidate" as const,
      room_id: 1,
      chain_id: "c1",
      round: 1,
      character_id: 7,
      character_name: "Mira",
      eagerness: 3,
      reason: "meh",
    };
    useGroup.getState().applyServerMsg(candidate);
    useGroup.getState().applyServerMsg({ ...candidate, eagerness: 9 });
    expect(useGroup.getState().elections[1]).toHaveLength(1);
    expect(useGroup.getState().elections[1][0].eagerness).toBe(9);
  });

  it("marks the chain as no longer running when it finishes", () => {
    useGroup.setState({ ...emptyState, chainRunning: { 1: true } });
    useGroup.getState().applyServerMsg({
      type: "group.chain.finished",
      room_id: 1,
      chain_id: "c1",
      reason: "settled",
    });
    expect(useGroup.getState().chainRunning[1]).toBe(false);
  });
});


describe("group chat regressions", () => {
  beforeEach(() => {
    useGroup.setState(emptyState);
  });

  it("appends the echoed user message", () => {
    // The server used to persist the user's line without ever sending it, so
    // it only appeared after a reload.
    useGroup.getState().applyServerMsg({
      type: "group.user_message",
      room_id: 1,
      message_id: "7",
      row_id: 7,
      content: "hello",
      user_name: "tester",
    });
    const stored = useGroup.getState().messages[1];
    expect(stored).toHaveLength(1);
    expect(stored[0]).toMatchObject({
      id: "7",
      role: "user",
      content: "hello",
      user_name: "tester",
      row_id: 7,
    });
  });

  it("does not double-append an echoed message", () => {
    const echo = {
      type: "group.user_message" as const,
      room_id: 1,
      message_id: "7",
      row_id: 7,
      content: "hello",
      user_name: "tester",
    };
    useGroup.getState().applyServerMsg(echo);
    useGroup.getState().applyServerMsg(echo);
    expect(useGroup.getState().messages[1]).toHaveLength(1);
  });

  it("keeps the previous round's candidates when a new election opens", () => {
    useGroup.getState().applyServerMsg({
      type: "group.elect.started",
      room_id: 1,
      chain_id: "c1",
      round: 1,
      candidates: [7],
    });
    useGroup.getState().applyServerMsg({
      type: "group.elect.candidate",
      room_id: 1,
      chain_id: "c1",
      round: 1,
      character_id: 7,
      character_name: "Mira",
      eagerness: 8,
      reason: "eager",
    });
    useGroup.getState().applyServerMsg({
      type: "group.elect.started",
      room_id: 1,
      chain_id: "c1",
      round: 2,
      candidates: [7],
    });
    // Clearing here made the status strip blink out and back every round.
    expect(useGroup.getState().elections[1]).toHaveLength(1);
    expect(useGroup.getState().chainRunning[1]).toBe(true);
  });

  it("stores the room's context gauge", () => {
    useGroup.getState().applyServerMsg({
      type: "group.context",
      room_id: 1,
      used_tokens: 1234,
      window_tokens: 128000,
    });
    expect(useGroup.getState().context[1]).toEqual({
      used: 1234,
      window: 128000,
    });
  });
});

describe("agent member messages", () => {
  beforeEach(() => {
    useGroup.setState(emptyState);
  });

  it("puts an external member's line on the assistant side, named", () => {
    useGroup.getState().applyServerMsg({
      type: "group.user_message",
      room_id: 1,
      message_id: "4",
      row_id: 4,
      content: "on it",
      user_name: "Claude",
      speaker_kind: "agent",
      member_ref: "claude-laptop",
    });
    const live = useGroup.getState().messages[1];
    expect(live).toHaveLength(1);
    expect(live[0].role).toBe("assistant");
    expect(live[0].character_name).toBe("Claude");
    expect(live[0].speaker_kind).toBe("agent");
    expect(live[0].member_ref).toBe("claude-laptop");
  });

  it("still treats a plain user message as the user side", () => {
    useGroup.getState().applyServerMsg({
      type: "group.user_message",
      room_id: 1,
      message_id: "5",
      row_id: 5,
      content: "hi",
      user_name: "You",
    });
    const live = useGroup.getState().messages[1];
    expect(live[0].role).toBe("user");
    expect(live[0].user_name).toBe("You");
    expect(live[0].speaker_kind ?? null).toBeNull();
  });
});

describe("tool steps and approvals in a room", () => {
  beforeEach(() => {
    useGroup.setState(emptyState);
  });

  it("keeps a character's steps on that character's message", () => {
    const called = applyGroupEvent([assistant("m1", 7, "Mira")], {
      type: "chat.tool_call",
      message_id: "m1",
      conversation_id: "s1",
      call_id: "c1",
      tool: "read_file",
      args: { path: "a.txt" },
      risk: "SAFE",
    });
    expect(called[0].tools).toHaveLength(1);
    expect(called[0].tools?.[0].tool).toBe("read_file");

    const done = applyGroupEvent(called, {
      type: "chat.tool_result",
      conversation_id: "s1",
      call_id: "c1",
      result: "ok",
      latency_ms: 12,
    });
    expect(done[0].tools?.[0].result).toBe("ok");
    expect(done[0].tools).toHaveLength(1);
  });

  it("ignores a step for a message the room does not have", () => {
    const next = applyGroupEvent([assistant("m1", 7, "Mira")], {
      type: "chat.tool_call",
      message_id: "other",
      conversation_id: "s1",
      call_id: "c1",
      tool: "read_file",
      args: {},
      risk: "SAFE",
    });
    expect(next[0].tools).toBeUndefined();
  });

  it("queues a call that needs a decision", () => {
    const next = applyRiskEvent(undefined, {
      type: "chat.tool_call",
      message_id: "m1",
      conversation_id: "s1",
      call_id: "c1",
      tool: "run_command",
      args: { command: "ls" },
      risk: "HIGH",
    }, 1);
    expect(next[1]).toHaveLength(1);
    expect(next[1][0].callId).toBe("c1");
    expect(next[1][0].risk).toBe("HIGH");
  });

  it("does not queue a call the engine already ruled safe", () => {
    const next = applyRiskEvent(undefined, {
      type: "chat.tool_call",
      message_id: "m1",
      conversation_id: "s1",
      call_id: "c1",
      tool: "read_file",
      args: {},
      risk: "SAFE",
    }, 1);
    expect(next[1] ?? []).toHaveLength(0);
  });

  it("drops the entry once the call has a result", () => {
    const queued = applyRiskEvent(undefined, {
      type: "chat.tool_call",
      message_id: "m1",
      conversation_id: "s1",
      call_id: "c1",
      tool: "run_command",
      args: {},
      risk: "HIGH",
    }, 1);
    const cleared = applyRiskEvent(queued, {
      type: "chat.tool_result",
      conversation_id: "s1",
      call_id: "c1",
      result: "ok",
      latency_ms: 3,
    }, 1);
    expect(cleared[1]).toHaveLength(0);
  });

  it("keeps approvals for another room apart", () => {
    const queued = applyRiskEvent(undefined, {
      type: "chat.tool_call",
      message_id: "m1",
      conversation_id: "s1",
      call_id: "c1",
      tool: "run_command",
      args: {},
      risk: "HIGH",
    }, 1);
    const other = applyRiskEvent(queued, {
      type: "chat.tool_call",
      message_id: "m2",
      conversation_id: "s2",
      call_id: "c2",
      tool: "run_command",
      args: {},
      risk: "MEDIUM",
    }, 2);
    expect(other[1]).toHaveLength(1);
    expect(other[2]).toHaveLength(1);
  });

  it("routes a tool event to the room that owns the conversation", () => {
    useGroup.setState({
      ...emptyState,
      rooms: [{ id: 4, session_id: "s4" } as unknown as RoomSummary],
      messages: { 4: [assistant("m9", 7, "Mira")] },
    });

    useGroup.getState().applyServerMsg({
      type: "chat.tool_call",
      message_id: "m9",
      conversation_id: "s4",
      call_id: "c1",
      tool: "read_file",
      args: {},
      risk: "HIGH",
    });

    const state = useGroup.getState();
    expect(state.messages[4][0].tools).toHaveLength(1);
    expect(state.pendingRisks[4]).toHaveLength(1);
  });

  it("drops a tool event for a conversation no room owns", () => {
    useGroup.setState({
      ...emptyState,
      rooms: [{ id: 4, session_id: "s4" } as unknown as RoomSummary],
      messages: { 4: [assistant("m9", 7, "Mira")] },
    });

    useGroup.getState().applyServerMsg({
      type: "chat.tool_call",
      message_id: "m9",
      conversation_id: "somewhere-else",
      call_id: "c1",
      tool: "read_file",
      args: {},
      risk: "HIGH",
    });

    const state = useGroup.getState();
    expect(state.messages[4][0].tools).toBeUndefined();
    expect(state.pendingRisks[4] ?? []).toHaveLength(0);
  });
});
