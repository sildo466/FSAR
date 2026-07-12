// SPDX-License-Identifier: Apache-2.0
import { afterEach, expect, it } from "vitest";
import { cleanup, fireEvent, render } from "@testing-library/react";
import type { ClientMsg, ServerMsg } from "../lib/ws-client";
import { useCardsStore } from "../stores/cards";
import { useSessions } from "../stores/sessions";
import { useWS } from "../stores/ws";
import { Chat } from "./Chat";

class FakeClient {
  readonly sent: ClientMsg[] = [];
  private listeners = new Set<(message: ServerMsg) => void>();

  on(listener: (message: ServerMsg) => void) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  send(message: ClientMsg) {
    this.sent.push(message);
  }
}

afterEach(cleanup);

it("shows thinking immediately and sends the selected draft character", () => {
  const client = new FakeClient();
  useWS.setState({ client: client as never, init: () => {} });
  useSessions.setState({
    sessions: [],
    currentId: null,
    history: {},
    loadingHistory: false,
    listLoaded: true,
  });
  useCardsStore.setState({
    characters: [{
      id: 7,
      name: "Coding Coach",
      description: "",
      personality: "",
      is_default: 0,
      avatar_path: null,
    }],
    userCards: [],
    defaultUserCard: null,
    sessionCharacters: {},
    draftCharacterId: 7,
  });

  const { getByPlaceholderText, container } = render(<Chat />);
  const input = getByPlaceholderText("Ask FSAR anything…");
  fireEvent.change(input, { target: { value: "Hello" } });
  fireEvent.keyDown(input, { key: "Enter" });

  expect(container.querySelector(".animate-pulse")).toBeTruthy();
  expect(client.sent).toContainEqual({
    type: "chat.send",
    conversation_id: undefined,
    character_id: 7,
    content: "Hello",
    mode: "agent",
  });
});

it("sends cancel while a reply is in progress", () => {
  const client = new FakeClient();
  useWS.setState({ client: client as never, init: () => {} });
  useSessions.setState({
    sessions: [], currentId: "session-1", history: { "session-1": [] },
    loadingHistory: false, listLoaded: true,
  });
  useCardsStore.setState({
    characters: [], userCards: [], defaultUserCard: null,
    sessionCharacters: {}, draftCharacterId: null,
  });

  const { getByPlaceholderText, getByText } = render(<Chat />);
  const input = getByPlaceholderText("Ask FSAR anything…");
  fireEvent.change(input, { target: { value: "Hello" } });
  fireEvent.keyDown(input, { key: "Enter" });
  fireEvent.click(getByText("Stop"));

  expect(client.sent).toContainEqual({
    type: "chat.cancel",
    conversation_id: "session-1",
  });
});
