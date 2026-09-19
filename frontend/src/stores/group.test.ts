// SPDX-License-Identifier: MIT
import { beforeEach, describe, expect, it } from "vitest";
import { applyGroupEvent, useGroup } from "./group";
import type { GroupMessage } from "../lib/ws-client";

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
  elections: {},
  chainRunning: {},
  loadingHistory: {},
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
    expect(useGroup.getState().elections[1]).toEqual([]);

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
