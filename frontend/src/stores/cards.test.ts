// SPDX-License-Identifier: Apache-2.0
import { beforeEach, describe, expect, it } from "vitest";
import type { ClientMsg, ServerMsg } from "../lib/ws-client";
import { useCardsStore } from "./cards";

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

describe("useCardsStore", () => {
  beforeEach(() => {
    useCardsStore.setState({
      characters: [],
      userCards: [],
      defaultUserCard: null,
      sessionCharacters: {},
      draftCharacterId: null,
    });
  });

  it("applies a confirmed default user change", () => {
    const client = new FakeClient();
    const detach = useCardsStore.getState().init(client as never);
    client.emit({
      type: "card.list_result",
      kind: "user",
      cards: [
        { id: 1, name: "Sildo466", is_default: 1 },
        { id: 2, name: "Lisdo89", is_default: 0 },
      ],
    });

    client.emit({ type: "card.default_changed", kind: "user", id: 2 });

    const state = useCardsStore.getState();
    expect(state.defaultUserCard?.name).toBe("Lisdo89");
    expect(state.userCards.find((card) => card.id === 1)?.is_default).toBe(0);
    expect(state.userCards.find((card) => card.id === 2)?.is_default).toBe(1);
    detach();
  });

  it("tracks the selected character before and after a session exists", () => {
    const client = new FakeClient();
    const detach = useCardsStore.getState().init(client as never);

    useCardsStore.getState().setDraftCharacter(7);
    expect(useCardsStore.getState().draftCharacterId).toBe(7);

    useCardsStore.getState().setSessionCharacter("session-1", 7);
    expect(useCardsStore.getState().sessionCharacters["session-1"]).toBe(7);
    expect(client.sent).toContainEqual({
      type: "card.set_session_character",
      session_id: "session-1",
      character_id: 7,
    });

    client.emit({
      type: "chat.thinking",
      message_id: "message-1",
      conversation_id: "session-2",
      character_id: 7,
      character_name: "Coding Coach",
    });
    expect(useCardsStore.getState().sessionCharacters["session-2"]).toBe(7);
    expect(useCardsStore.getState().draftCharacterId).toBeNull();
    detach();
  });
});
