// SPDX-License-Identifier: MIT
import { afterEach, describe, expect, it, vi } from "vitest";
import { ensureAdminSession, fetchWSTicket } from "./ws";

function setHash(hash: string) {
  window.history.replaceState(null, "", `/${hash}`);
}

afterEach(() => {
  vi.unstubAllGlobals();
  setHash("");
});

describe("ensureAdminSession", () => {
  it("does nothing when the URL carries no token", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await ensureAdminSession();

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("exchanges the fragment token and clears the fragment", async () => {
    setHash("#bootstrap=abc");
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 });
    vi.stubGlobal("fetch", fetchMock);

    await ensureAdminSession();

    expect(fetchMock).toHaveBeenCalledWith("/api/auth/bootstrap", {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: "abc" }),
    });
    expect(window.location.hash).toBe("");
  });

  it("clears a stale token instead of failing the page", async () => {
    setHash("#bootstrap=stale");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 403 }));

    await expect(ensureAdminSession()).resolves.toBeUndefined();

    expect(window.location.hash).toBe("");
  });
});

describe("fetchWSTicket", () => {
  it("returns the ticket", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ticket: "t1" }),
    }));

    await expect(fetchWSTicket()).resolves.toBe("t1");
  });

  it("raises when the server answers without a session", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 401 }));

    await expect(fetchWSTicket()).rejects.toThrow("ws_ticket fetch failed");
  });
});
