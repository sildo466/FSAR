import { create } from "zustand";

interface ChatUIState {
  mode: "agent" | "companion";
  setMode: (mode: "agent" | "companion") => void;
}

export const useChatUI = create<ChatUIState>((set) => ({
  mode: "agent",
  setMode: (mode) => set({ mode }),
}));
