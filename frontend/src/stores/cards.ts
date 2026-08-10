// SPDX-License-Identifier: MIT
import { create } from "zustand";
import type { ClientMsg, ServerMsg } from "../lib/ws-client";
import { WSClient } from "../lib/ws-client";

export interface CardSummary {
  id: number;
  name: string;
  description: string;
  personality: string;
  scenario?: string;
  is_default: number;
  avatar_path?: string | null;
  emotion_state?: Record<string, number>;
  emotion_schema?: unknown[];
  emotion_formulas?: Record<string, string>;
  tts_voice?: string;
  tts_instructions?: string;
  tts_autoplay_on_card?: number;
  [k: string]: unknown;
}

export interface UserCardSummary {
  id: number;
  name: string;
  description: string;
  communication_style?: string;
  preferences?: Record<string, unknown>;
  interests?: string[];
  is_default: number;
  avatar_path?: string | null;
  [k: string]: unknown;
}

interface CardsState {
  characters: CardSummary[];
  userCards: UserCardSummary[];
  defaultUserCard: UserCardSummary | null;
  sessionCharacters: Record<string, number | null>;
  draftCharacterId: number | null;
  init: (client: WSClient) => () => void;
  refresh: () => void;
  loadSessionCharacter: (sessionId: string) => void;
  setSessionCharacter: (sessionId: string, characterId: number) => void;
  setDraftCharacter: (characterId: number) => void;
  setDefault: (kind: "character" | "user", id: number) => void;
}

export const useCardsStore = create<CardsState>((set, get) => {
  let attached: WSClient | null = null;

  const applyServerMsg = (msg: ServerMsg) => {
    if (msg.type === "card.list_result") {
      if (msg.kind === "character") {
        const list = (msg.cards ?? []) as CardSummary[];
        set({ characters: list });
      } else if (msg.kind === "user") {
        const list = (msg.cards ?? []) as UserCardSummary[];
        set({
          userCards: list,
          defaultUserCard: list.find((u) => u.is_default === 1) ?? null,
        });
      }
    } else if (msg.type === "card.default_changed") {
      if (msg.kind === "character") {
        set((state) => ({
          characters: state.characters.map((card) => ({
            ...card,
            is_default: card.id === msg.id ? 1 : 0,
          })),
        }));
      } else if (msg.kind === "user") {
        set((state) => {
          const userCards = state.userCards.map((card) => ({
            ...card,
            is_default: card.id === msg.id ? 1 : 0,
          }));
          return {
            userCards,
            defaultUserCard: userCards.find((card) => card.id === msg.id) ?? null,
          };
        });
      }
    } else if (msg.type === "card.session_character_set" || msg.type === "card.session_character") {
      // A null lookup arriving after a known binding (race with
      // conversation.created) must not clobber the real character.
      if (
        msg.type === "card.session_character" &&
        msg.character_id == null &&
        get().sessionCharacters[msg.session_id] != null
      ) {
        return;
      }
      set((state) => ({
        sessionCharacters: {
          ...state.sessionCharacters,
          [msg.session_id]: msg.character_id,
        },
      }));
    } else if (msg.type === "chat.thinking" && msg.conversation_id && msg.character_id != null) {
      set((state) => ({
        sessionCharacters: {
          ...state.sessionCharacters,
          [msg.conversation_id!]: msg.character_id!,
        },
        draftCharacterId: null,
      }));
    }
  };

  const send = (msg: ClientMsg) => attached?.send(msg);

  return {
    characters: [],
    userCards: [],
    defaultUserCard: null,
    sessionCharacters: {},
    draftCharacterId: null,
    init: (client) => {
      attached = client;
      const detach = client.on(applyServerMsg);
      get().refresh();
      return () => {
        detach();
        attached = null;
      };
    },
    refresh: () => {
      send({ type: "card.list", kind: "character" });
      send({ type: "card.list", kind: "user" });
    },
    loadSessionCharacter: (sessionId) => {
      send({ type: "card.list_session_character", session_id: sessionId });
    },
    setSessionCharacter: (sessionId, characterId) => {
      set((state) => ({
        sessionCharacters: {
          ...state.sessionCharacters,
          [sessionId]: characterId,
        },
      }));
      send({ type: "card.set_session_character", session_id: sessionId, character_id: characterId });
    },
    setDraftCharacter: (characterId) => set({ draftCharacterId: characterId }),
    setDefault: (kind, id) => {
      send({ type: "card.set_default", kind, id });
    },
  };
});
