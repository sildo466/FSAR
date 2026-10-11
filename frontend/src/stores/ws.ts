// SPDX-License-Identifier: MIT
import { create } from "zustand";
import {
  WSClient,
  type AppVersion,
  type NotificationItem,
  type NotificationSettings,
  type ServerMsg,
} from "../lib/ws-client";
import { useSkinStore } from "./skin";

type Status = "connecting" | "connected" | "disconnected";

interface WSStore {
  status: Status;
  config: Record<string, unknown> | null;
  version: AppVersion | null;
  notifications: NotificationItem[];
  unread: number;
  notificationSettings: NotificationSettings | null;
  birthdayLetter: string | null;
  client: WSClient | null;
  init: () => void;
  send: (msg: Parameters<WSClient["send"]>[0]) => void;
}

const wsUrl = `ws://${window.location.hostname || "127.0.0.1"}:8765/ws`;
let initPromise: Promise<void> | null = null;

const BOOTSTRAP_FRAGMENT = "bootstrap";

function readBootstrapToken(): string {
  const raw = window.location.hash.replace(/^#/, "");
  if (!raw) return "";
  return new URLSearchParams(raw).get(BOOTSTRAP_FRAGMENT) ?? "";
}

function clearBootstrapToken(): void {
  // The token must not sit in the address bar or in history: it is single-use,
  // but a screenshot of the URL would hand it over anyway.
  window.history.replaceState(
    null,
    "",
    window.location.pathname + window.location.search,
  );
}

async function postBootstrap(token: string): Promise<void> {
  const response = await fetch("/api/auth/bootstrap", {
    method: "POST",
    credentials: "same-origin",
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token }),
  });
  if (!response.ok) throw new Error(`bootstrap failed (${response.status})`);
}

/** Establish the session the launcher opened this page for.
 *
 * A token that no longer works is not an error: the page may have been reloaded
 * after the session was already established from it, in which case the cookie
 * is what carries us.
 */
export async function ensureAdminSession(): Promise<void> {
  const token = readBootstrapToken();
  if (!token) return;
  await postBootstrap(token).catch(() => undefined);
  clearBootstrapToken();
}

export async function fetchWSTicket(): Promise<string> {
  const response = await fetch("/api/auth/ws-ticket", {
    credentials: "same-origin",
    cache: "no-store",
  });
  if (!response.ok) throw new Error("ws_ticket fetch failed");
  const payload = (await response.json()) as { ticket?: unknown };
  if (typeof payload.ticket !== "string" || !payload.ticket) {
    throw new Error("ws_ticket response invalid");
  }
  return payload.ticket;
}

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
  version: null,
  notifications: [],
  unread: 0,
  notificationSettings: null,
  birthdayLetter: null,
  client: null,
  init: () => {
    if (get().client || initPromise) return;
    initPromise = (async () => {
      try {
        await ensureAdminSession();
        const ticket = await fetchWSTicket();
        if (get().client) return;
        const client = new WSClient(wsUrl, ticket, fetchWSTicket);
    client.on((msg: ServerMsg) => {
      if (msg.type === "snapshot") {
        const nextConfig = { ...msg.config } as Record<string, unknown>;
        if (msg.onboarding) {
          nextConfig.onboarding = msg.onboarding;
        }
        set({
          config: nextConfig,
          version: msg.version ?? null,
          status: "connected",
          birthdayLetter: msg.birthday?.letter ?? null,
        });
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
      } else if (msg.type === "notifications.list_result") {
        set({
          notifications: msg.items,
          unread: msg.unread,
          notificationSettings: msg.settings,
        });
      } else if (msg.type === "notifications.read_result") {
        if (msg.cleared) {
          set({ notifications: [], unread: 0 });
        } else {
          // Only the ids the server actually changed — expanding one item must
          // not clear the unread marks on everything else.
          const done = new Set(msg.ids);
          set({
            unread: msg.unread,
            notifications: get().notifications.map((item) =>
              done.has(item.id) ? { ...item, read: 1 as const } : item,
            ),
          });
        }
      } else if (msg.type === "notifications.changed") {
        // The letters are written one at a time and the list is pull-only, so
        // without this the user would watch an empty page.
        get().send({ type: "notifications.list" });
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
      } else if (msg.type === "chat.default_model_fallback") {
        const current = (get().config ?? {}) as Record<string, unknown>;
        const chat = (current.chat ?? {}) as Record<string, unknown>;
        set({ config: { ...current, chat: { ...chat, default_model: msg.selected_chat_model } } });
      } else if (msg.type === "reflection.intensity_changed") {
        const current = (get().config ?? {}) as Record<string, unknown>;
        const reflection = (current.reflection ?? {}) as Record<string, unknown>;
        set({
          config: {
            ...current,
            reflection: { ...reflection, intensity: msg.intensity },
          },
        });
      } else if (msg.type === "skin.list") {
        useSkinStore.getState().receiveList(msg.skins);
      } else if (msg.type === "skin.changed") {
        useSkinStore.setState({ activeId: msg.skin_id });
      }
    });
        client.connect();
        set({ client });
      } catch {
        set({ status: "disconnected" });
      } finally {
        initPromise = null;
      }
    })();
  },
  send: (msg) => {
    get().client?.send(msg);
  },
}));
