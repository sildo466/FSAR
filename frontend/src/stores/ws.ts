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

function applyDotPatch(
  config: Record<string, unknown>,
  patch: Record<string, unknown>,
): Record<string, unknown> {
  const next = structuredClone(config);
  for (const [key, value] of Object.entries(patch)) {
    const parts = key.split(".");
    let cur: Record<string, unknown> = next;
    for (const p of parts.slice(0, -1)) {
      if (typeof cur[p] !== "object" || cur[p] === null) cur[p] = {};
      cur = cur[p] as Record<string, unknown>;
    }
    cur[parts[parts.length - 1]] = value;
  }
  return next;
}

export const useWS = create<WSStore>((set, get) => ({
  status: "connecting",
  config: null,
  client: null,
  init: () => {
    if (get().client) return;
    const client = new WSClient(wsUrl);
    client.on((msg: ServerMsg) => {
      if (msg.type === "snapshot") {
        const nextConfig = { ...msg.config } as Record<string, unknown>;
        if (msg.onboarding) {
          nextConfig.onboarding = msg.onboarding;
        }
        set({ config: nextConfig, status: "connected" });
      } else if (msg.type === "onboarding.state") {
        const current = (get().config ?? {}) as Record<string, unknown>;
        set({
          config: {
            ...current,
            onboarding: {
              required: msg.required,
              completed: msg.completed,
              completed_steps: msg.completed_steps,
              current_step: msg.current_step,
            },
          },
        });
      } else if (msg.type === "onboarding.completed") {
        const current = (get().config ?? {}) as Record<string, unknown>;
        const ob = (current.onboarding ?? {}) as Record<string, unknown>;
        set({
          config: {
            ...current,
            onboarding: { ...ob, required: false, completed: true },
          },
        });
      } else if (msg.type === "provider.created") {
        const current = (get().config ?? {}) as Record<string, unknown>;
        const llm = (current.llm ?? {}) as Record<string, unknown>;
        set({
          config: {
            ...current,
            llm: { ...llm, providers: msg.providers, active: msg.active },
          },
        });
      } else if (msg.type === "heartbeat") {
        set({ status: "connected" });
      } else if (msg.type === "settings.changed") {
        set({ config: applyDotPatch(get().config ?? {}, msg.patch) });
      } else if (msg.type === "llm.provider_changed") {
        const current = (get().config ?? {}) as Record<string, unknown>;
        const llm = (current.llm ?? {}) as Record<string, unknown>;
        set({
          config: { ...current, llm: { ...llm, active: msg.provider_id } },
        });
      } else if (msg.type === "reflection.intensity_changed") {
        const current = (get().config ?? {}) as Record<string, unknown>;
        const reflection = (current.reflection ?? {}) as Record<string, unknown>;
        set({
          config: {
            ...current,
            reflection: { ...reflection, intensity: msg.intensity },
          },
        });
      }
    });
    client.connect();
    set({ client });
  },
  send: (msg) => {
    get().client?.send(msg);
  },
}));
