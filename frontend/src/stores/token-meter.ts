// SPDX-License-Identifier: MIT
import { create } from "zustand";
import type { ServerMsg, WSClient } from "../lib/ws-client";

interface TokenMeterState {
  used: number;
  window: number;
  init: (client: WSClient) => () => void;
}

/** Live per-conversation context usage pushed by the engine (like the TUI
 * gauge): used/window tokens for the active chat. Backend emits
 * ``chat.context`` on turn start and each main agent-loop iteration. */
export const useTokenMeter = create<TokenMeterState>((set) => ({
  used: 0,
  window: 0,
  init: (client) =>
    client.on((msg: ServerMsg) => {
      if (msg.type === "chat.context") {
        set({ used: msg.used_tokens, window: msg.window_tokens });
      }
    }),
}));