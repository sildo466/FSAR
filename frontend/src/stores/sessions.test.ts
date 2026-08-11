// SPDX-License-Identifier: MIT
import { beforeEach, describe, expect, it } from "vitest";
import type { ClientMsg, ServerMsg, SessionMeta } from "../lib/ws-client";
import { useSessions } from "./sessions";

class FakeClient {
  readonly sent: ClientMsg[] = [];
  private listeners = new Set<(message: ServerMsg) => void>();

  on(listener: (message: ServerMsg) => void) {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  send(message: ClientMsg) {
    this.sent.push(message);
  }

  emit(message: ServerMsg) {
    this.listeners.forEach((l) => l(message));
  }
}

const session: SessionMeta = {
  id: "session-1",
  title: "Existing conversation",
  pinned: false,
  created_at: "2026-07-11T00:00:00Z",
  updated_at: "2026-07-11T00:00:00Z",
  message_count: 2,
};

describe("useSessions", () => {
  beforeEach(() => {
    localStorage.clear();
    useSessions.setState({
      sessions: [],
      currentId: null,
      history: {},
      loadingHistory: false,
      listLoaded: false,
      liveHistory: {},
    });
  });

  it("keeps a new conversation as a local draft until the first message", () => {
    const client = new FakeClient();
    const detach = useSessions.getState().init(client as never);
    useSessions.setState({ sessions: [session], currentId: session.id });

    useSessions.getState().createNew();

    expect(useSessions.getState().currentId).toBeNull();
    expect(useSessions.getState().sessions).toEqual([session]);
    expect(client.sent).not.toContainEqual({ type: "conversation.create" });
    detach();
  });

  it("does not replace an optimistic first message with empty history", () => {
    const client = new FakeClient();
    const detach = useSessions.getState().init(client as never);

    client.emit({ type: "conversation.created", session });

    expect(useSessions.getState().currentId).toBe(session.id);
    expect(client.sent).not.toContainEqual({
      type: "conversation.history",
      conversation_id: session.id,
      limit: 100,
    });
    detach();
  });

  it("requests the list on attach so a missed connect-time push recovers", () => {
    const client = new FakeClient();
    const detach = useSessions.getState().init(client as never);

    expect(client.sent).toContainEqual({ type: "conversation.list" });
    detach();
  });

  it("does not re-request the list once it is already loaded", () => {
    useSessions.setState({ sessions: [session], listLoaded: true });
    const client = new FakeClient();
    const detach = useSessions.getState().init(client as never);

    expect(client.sent).not.toContainEqual({ type: "conversation.list" });
    detach();
  });

  it("auto-picks the saved conversation when the list arrives after attach", () => {
    localStorage.setItem("fsar.currentConversationId", session.id);
    const client = new FakeClient();
    const detach = useSessions.getState().init(client as never);

    client.emit({ type: "conversation.list", sessions: [session] });

    expect(client.sent).toContainEqual({
      type: "conversation.switch",
      conversation_id: session.id,
    });
    expect(client.sent).toContainEqual({
      type: "conversation.history",
      conversation_id: session.id,
      limit: 100,
    });
    detach();
  });

  it("keeps live streamed messages per conversation for navigation restore", () => {
    useSessions.getState().syncLive("session-1", [
      {
        id: "msg_1",
        role: "assistant",
        content: "checking…",
        tools: [{ callId: "c1", tool: "run_command", argsPreview: "{}" }],
      },
    ]);

    const cached = useSessions.getState().liveHistory["session-1"];
    expect(cached).toHaveLength(1);
    expect(cached?.[0].content).toBe("checking…");
    expect(cached?.[0].tools).toHaveLength(1);
    expect(useSessions.getState().liveHistory["other"]).toBeUndefined();
  });

  it("drops live history when the conversation is deleted", () => {
    useSessions.getState().syncLive("session-1", [
      { id: "msg_1", role: "assistant", content: "x" },
    ]);
    const client = new FakeClient();
    const detach = useSessions.getState().init(client as never);

    client.emit({ type: "conversation.deleted", conversation_id: "session-1" });

    expect(useSessions.getState().liveHistory["session-1"]).toBeUndefined();
    detach();
  });

  it("accumulates the chat stream globally even while Chat is unmounted", () => {
    const client = new FakeClient();
    const detach = useSessions.getState().init(client as never);

    client.emit({ type: "chat.thinking", message_id: "m1", conversation_id: "session-1" });
    client.emit({
      type: "chat.delta", message_id: "m1", conversation_id: "session-1", content: "工作进度",
    });
    client.emit({
      type: "chat.tool_call", message_id: "m1", conversation_id: "session-1",
      call_id: "c1", tool: "run_command", args: { command: "echo hi" }, risk: "SAFE",
    });
    client.emit({
      type: "chat.done", message_id: "m1", conversation_id: "session-1", outcome: "success",
    });

    const live = useSessions.getState().liveHistory["session-1"];
    expect(live).toHaveLength(1);
    expect(live?.[0].content).toBe("工作进度");
    expect(live?.[0].streaming).toBe(false);
    expect(live?.[0].tools).toHaveLength(1);
    expect(live?.[0].tools?.[0].tool).toBe("run_command");
    detach();
  });
});
