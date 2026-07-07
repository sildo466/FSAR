// SPDX-License-Identifier: Apache-2.0
import { create } from "zustand";

export type Theme = "light" | "dark" | "system";
export type Density = "comfortable" | "compact";
export type Motion = "subtle" | "full" | "none";

interface UIState {
  theme: Theme;
  density: Density;
  motion: Motion;
  fontScale: number;
  perPageOverrides: Record<string, { theme?: Theme; density?: Density; motion?: Motion }>;

  setTheme: (t: Theme) => void;
  setDensity: (d: Density) => void;
  setMotion: (m: Motion) => void;
  setFontScale: (s: number) => void;
  setOverride: (page: string, key: "theme" | "density" | "motion", value: Theme | Density | Motion | null) => void;
}

const DEFAULT: Omit<UIState,
  "setTheme" | "setDensity" | "setMotion" | "setFontScale" | "setOverride"
> = {
  theme: "system",
  density: "comfortable",
  motion: "subtle",
  fontScale: 1.0,
  perPageOverrides: {},
};

export const useUI = create<UIState>((set) => ({
  ...DEFAULT,
  setTheme: (theme) => set({ theme }),
  setDensity: (density) => set({ density }),
  setMotion: (motion) => set({ motion }),
  setFontScale: (fontScale) => set({ fontScale }),
  setOverride: (page, key, value) =>
    set((s) => {
      const next = { ...s.perPageOverrides };
      const inner = { ...(next[page] || {}) };
      if (value === null) delete inner[key];
      else (inner as Record<string, Theme | Density | Motion>)[key] = value;
      if (Object.keys(inner).length === 0) delete next[page];
      else next[page] = inner;
      return { perPageOverrides: next };
    }),
}));
