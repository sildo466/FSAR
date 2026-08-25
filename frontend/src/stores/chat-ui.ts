import { create } from "zustand";

export type ChatMode = "agent" | "companion" | "character";

const LS_KEY = "fsar.chatMode";
const MODES: ChatMode[] = ["agent", "companion", "character"];

function loadSavedMode(): ChatMode {
  try {
    const saved = localStorage.getItem(LS_KEY);
    if (saved === "companion" || saved === "character" || saved === "agent") {
      return saved;
    }
  } catch {
    /* ignore */
  }
  return "agent";
}

function saveMode(mode: ChatMode) {
  try {
    localStorage.setItem(LS_KEY, mode);
  } catch {
    /* ignore */
  }
}

interface ChatUIState {
  mode: ChatMode;
  setMode: (mode: ChatMode) => void;
}

export const useChatUI = create<ChatUIState>((set) => ({
  mode: loadSavedMode(),
  setMode: (mode) => {
    saveMode(mode);
    set({ mode });
  },
}));
