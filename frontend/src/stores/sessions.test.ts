// SPDX-License-Identifier: MIT
import { beforeEach, describe, expect, it } from "vitest";
import type { ClientMsg, ServerMsg, SessionMeta } from "../lib/ws-client";
import { useSessions } from "./sessions";

class FakeClient {
  readonly sent: ClientMsg[] = [];
  private listener: ((message: ServerMsg) => void) | null = null;

  on(listener: (message: ServerMsg) => void) {
    this.listener = listener;
    return () => {
      this.listener = null;
    };
  }

  send(message: ClientMsg) {
    this.sent.push(message);
  }

  emit(message: ServerMsg) {
    this.listener?.(message);
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
});
