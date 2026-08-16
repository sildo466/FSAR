// SPDX-License-Identifier: MIT
import { create } from "zustand";
import type { TokenKey } from "../lib/skin";

export interface Skin {
  id: string;
  name: string;
  base: "light" | "dark";
  palette: Partial<Record<TokenKey, string>>;
}

interface SkinState {
  skins: Skin[];
  status: "idle" | "loading" | "ready";
  activeId: "default" | string;
  receiveList: (skins: Skin[]) => void;
  hydrate: (id: unknown) => void;
  setActive: (send: (msg: { type: "skin.set_active"; skin_id: string }) => void, id: string) => void;
}

export const useSkinStore = create<SkinState>((set) => ({
  skins: [],
  status: "idle",
  activeId: "default",
  receiveList: (skins) => set({ skins, status: "ready" }),
  hydrate: (id) => {
    if (typeof id === "string" && id !== "") set({ activeId: id });
  },
  setActive: (send, id) => {
    set({ activeId: id });
    send({ type: "skin.set_active", skin_id: id });
  },
}));
