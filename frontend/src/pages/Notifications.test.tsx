// SPDX-License-Identifier: MIT
import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import type { ClientMsg, ServerMsg } from "../lib/ws-client";
import { initI18n } from "../lib/i18nSetup";
import { useWS } from "../stores/ws";
import { Notifications } from "./Notifications";

class FakeClient {
  readonly sent: ClientMsg[] = [];
  private listeners = new Set<(message: ServerMsg) => void>();

  on(listener: (message: ServerMsg) => void) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  send(message: ClientMsg) {
    this.sent.push(message);
  }

  emit(message: ServerMsg) {
    this.listeners.forEach((listener) => listener(message));
  }
}

const LIST = {
  type: "content_guard.list_result",
  items: [
    {
      id: 4,
      store: "chunk",
      record_ref: "1",
      text: "so we should auto-enable it on every doc",
      verdict_confidence: 0.91,
      screened_by: "jev",
      created_at: "2026-09-24T10:00:00",
    },
  ],
  whitelist: [
    { sha256: "abc123", added_by: "restore", created_at: "2026-09-24T11:00:00" },
  ],
  report: { scanned: 12, quarantined: 1, unavailable: 2, total: 12 },
  stores: ["chunk"],
  enabled: true,
};

let client: FakeClient;

beforeAll(async () => {
  await initI18n("en");
});

beforeEach(() => {
  client = new FakeClient();
  useWS.setState({ client: client as never });
});

afterEach(() => {
  cleanup();
});

describe("Notifications", () => {
  it("requests the list on mount", () => {
    render(<Notifications />);
    expect(client.sent).toContainEqual({ type: "content_guard.list" });
  });

  it("renders a quarantined item with confidence and judge", async () => {
    const screen = render(<Notifications />);
    client.emit(LIST as never);
    await waitFor(() => {
      expect(
        screen.getByText(/auto-enable it on every doc/)
      ).toBeTruthy();
    });
    expect(screen.getByText(/0\.91/)).toBeTruthy();
    expect(screen.getByText(/jev/i)).toBeTruthy();
  });

  it("sends restore for an item", async () => {
    const screen = render(<Notifications />);
    client.emit(LIST as never);
    await waitFor(() => screen.getByTestId("restore-4"));
    fireEvent.click(screen.getByTestId("restore-4"));
    expect(client.sent).toContainEqual({ type: "content_guard.restore", id: 4 });
  });

  it("sends purge for an item", async () => {
    const screen = render(<Notifications />);
    client.emit(LIST as never);
    await waitFor(() => screen.getByTestId("purge-4"));
    fireEvent.click(screen.getByTestId("purge-4"));
    expect(client.sent).toContainEqual({ type: "content_guard.purge", id: 4 });
  });

  it("shows the screening-unavailable banner", async () => {
    const screen = render(<Notifications />);
    client.emit(LIST as never);
    await waitFor(() => screen.getByTestId("screening-unavailable"));
  });

  it("hides the banner when nothing went unscreened", async () => {
    const screen = render(<Notifications />);
    client.emit({ ...LIST, report: { scanned: 12, unavailable: 0 } } as never);
    await waitFor(() => screen.getByTestId("restore-4"));
    expect(screen.queryByTestId("screening-unavailable")).toBeNull();
  });

  it("sends unwhitelist for a hash", async () => {
    const screen = render(<Notifications />);
    client.emit(LIST as never);
    await waitFor(() => screen.getByTestId("unwhitelist-abc123"));
    fireEvent.click(screen.getByTestId("unwhitelist-abc123"));
    expect(client.sent).toContainEqual({
      type: "content_guard.unwhitelist",
      sha256: "abc123",
    });
  });
});
