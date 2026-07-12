// SPDX-License-Identifier: Apache-2.0
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
});
