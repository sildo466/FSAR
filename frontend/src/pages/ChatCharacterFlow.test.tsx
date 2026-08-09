// SPDX-License-Identifier: MIT
import { afterEach, beforeAll, expect, it } from "vitest";
import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render } from "@testing-library/react";
import type { ClientMsg, ServerMsg } from "../lib/ws-client";
import { useCardsStore } from "../stores/cards";
import { useSessions } from "../stores/sessions";
import { useWS } from "../stores/ws";
import { initI18n } from "../lib/i18nSetup";
import i18n from "../lib/i18nSetup";
import { Chat } from "./Chat";
import { CharacterSelector } from "../components/chat/CharacterSelector";

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

const FSAR_EN = { id: 1, name: "FSAR (en)", description: "", personality: "", is_default: 1, avatar_path: null };
const ORI = { id: 2, name: "Ori", description: "", personality: "", is_default: 0, avatar_path: "avatars/ori.png" };

let detachSessions: (() => void) | null = null;

function resetStores(client: FakeClient) {
  useWS.setState({ client: client as never, init: () => {} });
  useSessions.setState({
    sessions: [], currentId: null, history: {}, loadingHistory: false, listLoaded: true,
  });
  useCardsStore.setState({
    characters: [FSAR_EN, ORI],
    userCards: [],
    defaultUserCard: null,
    sessionCharacters: {},
    draftCharacterId: null,
  });
  // App owns this subscription in the real shell, not the chat route.
  detachSessions = useSessions.getState().init(client as never);
}

function SelectorHost() {
  const currentId = useSessions((s) => s.currentId);
  return <CharacterSelector sessionId={currentId ?? ""} />;
}

afterEach(() => {
  cleanup();
  detachSessions?.();
  detachSessions = null;
});

it("new conversation inherits the previous session's character", () => {
  const client = new FakeClient();
  resetStores(client);
  useSessions.setState({ currentId: "A", history: { A: [] } });
  useCardsStore.setState({ sessionCharacters: { A: 2 } });

  const { getByRole } = render(
    <>
      <SelectorHost />
      <Chat />
    </>
  );
  useCardsStore.getState().init(client as never);

  act(() => {
    useSessions.getState().createNew();
  });

  expect(getByRole("button", { name: "character" }).textContent).toContain("Ori");
});

it("keeps the picked character in selector and bubbles after draft send", () => {
  const client = new FakeClient();
  resetStores(client);

  const { getByRole, getByPlaceholderText, getAllByText } = render(
    <>
      <SelectorHost />
      <Chat />
    </>
  );
  useCardsStore.getState().init(client as never);

  act(() => {
    useCardsStore.getState().setDraftCharacter(2);
  });
  expect(getByRole("button", { name: "character" }).textContent).toContain("Ori");

  const input = getByPlaceholderText(i18n.t("chat.placeholderInput"));
  fireEvent.change(input, { target: { value: "Hello" } });
  fireEvent.keyDown(input, { key: "Enter" });

  const send = client.sent.find((m) => m.type === "chat.send");
  expect(send).toMatchObject({ type: "chat.send", character_id: 2 });

  act(() => {
    client.emit({
      type: "conversation.created",
      session: { id: "B", title: "", pinned: false, created_at: "", updated_at: "", message_count: 0 },
    });
  });
  act(() => {
    client.emit({ type: "card.session_character", session_id: "B", character_id: null });
  });
  act(() => {
    client.emit({
      type: "chat.thinking",
      message_id: "m1",
      conversation_id: "B",
      character_id: 2,
      character_name: "Ori",
    });
  });
  act(() => {
    client.emit({ type: "chat.delta", message_id: "m1", content: "Hi there", character_id: 2, character_name: "Ori" });
    client.emit({ type: "chat.done", message_id: "m1", outcome: "success", character_id: 2, character_name: "Ori" });
  });

  expect(getByRole("button", { name: "character" }).textContent).toContain("Ori");
  expect(getAllByText("Ori").length).toBeGreaterThanOrEqual(2);
  expect(document.body.textContent).not.toContain("FSAR (en)");
});

it("regenerate removes the last assistant bubble and sends chat.regenerate", () => {
  const client = new FakeClient();
  resetStores(client);
  useSessions.setState({
    currentId: "B",
    history: {
      B: [
        { id: 1, session_id: "B", role: "user", content: "Hello", summary: "", tags: "", timestamp: "" },
        { id: 2, session_id: "B", role: "assistant", content: "Old reply", summary: "", tags: "", timestamp: "" },
      ],
    },
  });

  const { getByRole, getByText, queryByText } = render(<Chat />);
  useCardsStore.getState().init(client as never);

  getByText("Old reply");
  fireEvent.click(getByRole("button", { name: "Regenerate response" }));

  expect(client.sent.find((m) => m.type === "chat.regenerate")).toMatchObject({
    type: "chat.regenerate",
    conversation_id: "B",
  });
  expect(queryByText("Old reply")).not.toBeInTheDocument();
  expect(useSessions.getState().history["B"].map((m) => m.role)).toEqual(["user"]);

  act(() => {
    client.emit({
      type: "chat.thinking",
      message_id: "m2",
      conversation_id: "B",
      character_id: 1,
      character_name: "FSAR (en)",
    });
    client.emit({ type: "chat.delta", message_id: "m2", content: "New reply" });
    client.emit({ type: "chat.done", message_id: "m2", outcome: "success" });
  });
  getByText("New reply");
});
