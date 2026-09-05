// SPDX-License-Identifier: MIT
import { create } from "zustand";

const LS_KEY = "fsar.liveSubtitlesVisible";

function loadVisible(): boolean {
  try {
    const saved = localStorage.getItem(LS_KEY);
    if (saved === "1") return true;
    if (saved === "0") return false;
  } catch {
    /* ignore */
  }
  return true;
}

function saveVisible(visible: boolean) {
  try {
    localStorage.setItem(LS_KEY, visible ? "1" : "0");
  } catch {
    /* ignore */
  }
}

interface LiveUiState {
  subtitlesVisible: boolean;
  toggleSubtitles: () => void;
}

export const useLiveUi = create<LiveUiState>((set, get) => ({
  subtitlesVisible: loadVisible(),
  toggleSubtitles: () => {
    const next = !get().subtitlesVisible;
    saveVisible(next);
    set({ subtitlesVisible: next });
  },
}));
