// SPDX-License-Identifier: MIT
import { afterEach, beforeAll, expect, it } from "vitest";
import { act, cleanup, fireEvent, render } from "@testing-library/react";
import type { ClientMsg, ServerMsg } from "../lib/ws-client";
import { useCardsStore } from "../stores/cards";
import { useSessions } from "../stores/sessions";
import { useWS } from "../stores/ws";
import { initI18n } from "../lib/i18nSetup";
import { Chat } from "./Chat";
import i18n from "../lib/i18nSetup";

beforeAll(async () => {
  await initI18n("en");
});

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

  emit(message: ServerMsg) {
    this.listeners.forEach((listener) => listener(message));
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
  const input = getByPlaceholderText(i18n.t("chat.placeholderInput"));
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
  const input = getByPlaceholderText(i18n.t("chat.placeholderInput"));
  fireEvent.change(input, { target: { value: "Hello" } });
  fireEvent.keyDown(input, { key: "Enter" });
  fireEvent.click(getByText(i18n.t("chat.stop")));

  expect(client.sent).toContainEqual({
    type: "chat.cancel",
    conversation_id: "session-1",
  });
});

it("shows live parent and sub-agent status", () => {
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

  const { getByText } = render(<Chat />);
  act(() => {
    client.emit({
      type: "agent.run.started",
      task_id: "task-1",
      message_id: "message-1",
      tier: "max",
    });
    client.emit({
      type: "agent.status",
      task_id: "task-1",
      agent_id: "task-1",
      parent_id: null,
      depth: 0,
      kind: "main",
      label: "Coordinator",
      status: "delegating",
      detail: "Dispatching work",
    });
    client.emit({
      type: "agent.status",
      task_id: "task-1",
      agent_id: "agent-1",
      parent_id: "task-1",
      depth: 1,
      kind: "subagent",
      label: "Verifier",
      status: "working",
      detail: "Using web_search",
    });
  });

  expect(getByText("Coordinator")).toBeTruthy();
  expect(getByText("Verifier")).toBeTruthy();
  expect(getByText("Using web_search")).toBeTruthy();
});
