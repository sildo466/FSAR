import { create } from "zustand";

export type ChatMode = "agent" | "companion" | "character";

interface ChatUIState {
  mode: ChatMode;
  setMode: (mode: ChatMode) => void;
}

export const useChatUI = create<ChatUIState>((set) => ({
  mode: "agent",
  setMode: (mode) => set({ mode }),
}));
