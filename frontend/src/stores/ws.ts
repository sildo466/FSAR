// SPDX-License-Identifier: Apache-2.0
import { create } from "zustand";
import { WSClient, type ServerMsg } from "../lib/ws-client";

type Status = "connecting" | "connected" | "disconnected";

interface WSStore {
  status: Status;
  config: Record<string, unknown> | null;
  client: WSClient | null;
  init: () => void;
  send: (msg: Parameters<WSClient["send"]>[0]) => void;
}

const wsUrl = `ws://${window.location.hostname || "127.0.0.1"}:8765/ws`;

export const useWS = create<WSStore>((set, get) => ({
  status: "connecting",
  config: null,
  client: null,
  init: () => {
    if (get().client) return;
    const client = new WSClient(wsUrl);
    client.on((msg: ServerMsg) => {
      if (msg.type === "snapshot") {
        set({ config: msg.config, status: "connected" });
      } else if (msg.type === "heartbeat") {
        set({ status: "connected" });
      } else if (msg.type === "settings.changed") {
        set({ config: { ...get().config, ...msg.patch } });
      }
    });
    client.connect();
    set({ client });
  },
  send: (msg) => {
    get().client?.send(msg);
  },
}));
