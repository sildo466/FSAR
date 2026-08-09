// SPDX-License-Identifier: MIT
import { afterEach, beforeAll, expect, it } from "vitest";
import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { Link, MemoryRouter, Route, Routes } from "react-router-dom";
import { useEffect } from "react";
import type { ClientMsg, ServerMsg, SessionMeta, StoredMessage } from "../lib/ws-client";
import { useCardsStore } from "../stores/cards";
import { useSessions } from "../stores/sessions";
import { useWS } from "../stores/ws";
import { initI18n } from "../lib/i18nSetup";
import { Chat } from "./Chat";
import { CharacterSelector } from "../components/chat/CharacterSelector";

beforeAll(async () => {
  await initI18n("en");
});

const session: SessionMeta = {
  id: "conv-1",
  title: "Earlier conversation",
  pinned: false,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
  message_count: 2,
};

function storedMessage(id: number, role: string, content: string): StoredMessage {
  return {
    id,
    session_id: session.id,
    role,
    content,
    summary: "",
    tags: "",
    timestamp: session.created_at,
  };
}

// Models the server closely enough to matter here: conversation.list is
// pushed once at connect time and otherwise only on request, so a client that
// attaches late must ask for it or never see it.
class FakeClient {
  readonly sent: ClientMsg[] = [];
  private listeners = new Set<(message: ServerMsg) => void>();

  on(listener: (message: ServerMsg) => void) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  send(message: ClientMsg) {
    this.sent.push(message);
    if (message.type === "conversation.list") {
      this.emit({ type: "conversation.list", sessions: [session] });
    } else if (message.type === "conversation.switch") {
      this.emit({
        type: "conversation.switched",
        conversation_id: message.conversation_id,
        session,
      });
    } else if (message.type === "conversation.history") {
      this.emit({
        type: "conversation.history",
        conversation_id: message.conversation_id,
        messages: [
          storedMessage(1, "user", "hello there"),
          { ...storedMessage(2, "assistant", "hi from Ori"), character_id: 2, character_name: "Ori" },
        ],
      });
    } else if (message.type === "card.list_session_character") {
      this.emit({
        type: "card.session_character",
        session_id: message.session_id,
        character_id: 2,
      });
    }
  }

  emit(message: ServerMsg) {
    this.listeners.forEach((listener) => listener(message));
  }
}

const FSAR_EN = { id: 1, name: "FSAR (en)", description: "", personality: "", is_default: 1, avatar_path: null };
const ORI = { id: 2, name: "Ori", description: "", personality: "", is_default: 0, avatar_path: null };

afterEach(cleanup);

// Mirrors app.tsx: the sessions subscription is owned by the shell, not by
// the chat route, so it survives navigating away and back.
function Shell({ client }: { client: FakeClient }) {
  const initSessions = useSessions((s) => s.init);
  const initCards = useCardsStore((s) => s.init);
  useEffect(() => initSessions(client as never), [client, initSessions]);
  useEffect(() => initCards(client as never), [client, initCards]);
  const currentId = useSessions((s) => s.currentId);
  return (
    <Routes>
      <Route
        path="/"
        element={
          <>
            <CharacterSelector sessionId={currentId ?? ""} />
            <Chat />
          </>
        }
      />
      <Route
        path="/settings/workspace"
        element={
          <>
            <div>workspace page</div>
            <Link to="/">back to chat</Link>
          </>
        }
      />
    </Routes>
  );
}

it("keeps history and character after visiting the workspace route", () => {
  localStorage.setItem("fsar.currentConversationId", session.id);
  const client = new FakeClient();
  useWS.setState({ client: client as never, init: () => {} });
  useSessions.setState({
    sessions: [], currentId: null, history: {}, loadingHistory: false, listLoaded: false,
  });
  useCardsStore.setState({
    characters: [FSAR_EN, ORI],
    userCards: [],
    defaultUserCard: null,
    sessionCharacters: {},
    draftCharacterId: null,
  });

  // The app boots on the workspace route, exactly as a full-page <a href>
  // navigation does. The chat route never mounts, so it never sees the
  // connect-time conversation.list.
  render(
    <MemoryRouter initialEntries={["/settings/workspace"]}>
      <Shell client={client} />
    </MemoryRouter>
  );
  expect(screen.getByText("workspace page")).toBeInTheDocument();

  // Returning to chat is client-side routing — nothing reconnects.
  act(() => {
    fireEvent.click(screen.getByText("back to chat"));
  });

  expect(useSessions.getState().currentId).toBe(session.id);
  expect(screen.getByText("hello there")).toBeInTheDocument();
  expect(screen.getByText("hi from Ori")).toBeInTheDocument();
  expect(screen.getByLabelText("character")).toHaveTextContent("Ori");
});

it("populates the store for a non-chat route that needs the session list", () => {
  const client = new FakeClient();
  useWS.setState({ client: client as never, init: () => {} });
  useSessions.setState({
    sessions: [], currentId: null, history: {}, loadingHistory: false, listLoaded: false,
  });

  render(
    <MemoryRouter initialEntries={["/settings/workspace"]}>
      <Shell client={client} />
    </MemoryRouter>
  );

  // The workspace page's per-conversation bindings list reads this store, so
  // it stays empty unless the subscription outlives the chat route.
  expect(useSessions.getState().sessions).toEqual([session]);
});
