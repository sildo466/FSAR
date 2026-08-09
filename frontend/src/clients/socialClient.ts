import { fetchWSToken, useWS } from "../stores/ws";

export type PlatformStatus = {
  platform: "telegram" | "feishu" | "wechat";
  state: "running" | "paused" | "unknown";
  configured?: boolean;
  login_required?: boolean;
  account_id?: string;
};

async function authenticatedFetch(path: string, init?: RequestInit) {
  const token = await fetchWSToken();
  const response = await fetch(path, {
    ...init,
    headers: { ...init?.headers, Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({})) as { detail?: string };
    throw new Error(payload.detail || `Request failed (${response.status})`);
  }
  return response;
}

export function patchSocial(patch: Record<string, unknown>): Promise<void> {
  const client = useWS.getState().client;
  if (!client) return Promise.reject(new Error("FSAR is disconnected"));
  return new Promise((resolve, reject) => {
    const keys = Object.keys(patch);
    let detach = () => {};
    const timeout = window.setTimeout(() => {
      detach();
      reject(new Error("Save timed out"));
    }, 5000);
    detach = client.on((message) => {
      if (message.type === "settings.changed") {
        if (!keys.some((key) => key in message.patch)) return;
        window.clearTimeout(timeout);
        detach();
        resolve();
      } else if (message.type === "error" && message.code === "bad_social_setting") {
        window.clearTimeout(timeout);
        detach();
        reject(new Error(message.message || "Invalid channel settings"));
      }
    });
    client.send({ type: "settings.patch", patch });
  });
}

export async function fetchSocialStatuses(): Promise<PlatformStatus[]> {
  const response = await authenticatedFetch("/api/social/status", { cache: "no-store" });
  const payload = await response.json() as { statuses?: PlatformStatus[] };
  return Array.isArray(payload.statuses) ? payload.statuses : [];
}

export async function beginWechatQr(): Promise<{ qrcode: string; scan_data: string }> {
  const response = await authenticatedFetch("/api/social/wechat/qr", { method: "POST" });
  return response.json();
}

export async function resetWechatQr(): Promise<{ qrcode: string; scan_data: string }> {
  const response = await authenticatedFetch("/api/social/wechat/qr/reset", { method: "POST" });
  return response.json();
}

export async function checkWechatQr(): Promise<{ status: string; account_id?: string }> {
  const response = await authenticatedFetch("/api/social/wechat/qr/status", { cache: "no-store" });
  return response.json();
}
