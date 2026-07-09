// SPDX-License-Identifier: Apache-2.0
import { create } from "zustand";
import type { ServerMsg } from "../lib/ws-client";

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
  refresh: () => Promise<void>;
  setSessionCharacter: (sessionId: string, characterId: number) => Promise<void>;
  handleWsMessage: (msg: ServerMsg) => void;
}

const send = (msg: ServerMsg extends { type: string } ? any : never) => {
  const w = window as unknown as { __WS?: { send: (m: unknown) => Promise<unknown> } };
  return w.__WS?.send(msg);
};

export const useCardsStore = create<CardsState>((set, get) => ({
  characters: [],
  userCards: [],
  defaultUserCard: null,
  refresh: async () => {
    const chars = (await send({ type: "card.list", kind: "character" })) as { cards: CardSummary[] };
    const users = (await send({ type: "card.list", kind: "user" })) as { cards: UserCardSummary[] };
    set({ characters: chars.cards ?? [], userCards: users.cards ?? [] });
    set({ defaultUserCard: (users.cards ?? []).find((u) => u.is_default === 1) ?? null });
  },
  setSessionCharacter: async (sessionId, characterId) => {
    await send({ type: "card.set_session_character", session_id: sessionId, character_id: characterId });
  },
  handleWsMessage: (msg) => {
    if (msg.type === "card.user_card_renamed") {
      const cur = get().defaultUserCard;
      if (cur && cur.id === msg.user_card_id) {
        set({ defaultUserCard: { ...cur, name: msg.name } });
      }
      set({
        userCards: get().userCards.map((u) =>
          u.id === msg.user_card_id ? { ...u, name: msg.name } : u
        ),
      });
    }
    if (msg.type === "card.emotion_state_updated") {
      set({
        characters: get().characters.map((c) =>
          c.id === msg.character_id ? { ...c, emotion_state: msg.state } : c
        ),
      });
    }
  },
}));
