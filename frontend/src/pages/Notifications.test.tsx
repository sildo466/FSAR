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
  await initI18n("zh-Hans");
});

beforeEach(() => {
  client = new FakeClient();
  useWS.setState({
    client: client as never,
    notifications: [],
    unread: 0,
    notificationSettings: null,
  });
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
    expect(screen.getByText(/本次有 2 条/)).toBeTruthy();
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

// The feed lands in the ws store rather than in the page's own listener: the
// sidebar reads `unread` from the same slice, so the store is its only home.
function pushFeed(feed: { items: unknown[]; unread: number; settings?: unknown }) {
  useWS.setState({
    notifications: feed.items as never,
    unread: feed.unread,
    notificationSettings: (feed.settings ?? null) as never,
  });
}

const FEED = {
  type: "notifications.list_result",
  items: [
    {
      id: 1,
      kind: "release",
      title: "FSAR v0.7.0",
      body: "notes",
      ref: "v0.7.0",
      url: "https://github.com/sildo466/FSAR/releases/tag/v0.7.0",
      payload: { tag: "v0.7.0", channel: "stable" },
      read: 0,
      created_at: "2026-09-25T10:00:00",
    },
    {
      id: 2,
      kind: "review",
      title: "Quarantined content in chunk",
      body: "ignore previous",
      ref: "4",
      url: null,
      payload: { store: "chunk", record_ref: "4" },
      read: 1,
      created_at: "2026-09-24T10:00:00",
    },
  ],
  unread: 1,
  kinds: ["review", "release", "announcement"],
  settings: {
    review: { enabled: true },
    release: { enabled: true, include_prerelease: false },
    announcement: { enabled: true },
  },
};

describe("Notifications feed", () => {
  it("requests the feed on mount", () => {
    render(<Notifications />);
    expect(client.sent).toContainEqual({ type: "notifications.list" });
  });

  it("renders a stable release notification with localized copy", async () => {
    const screen = render(<Notifications />);
    pushFeed(FEED);
    await waitFor(() => screen.getByTestId("notification-1"));
    expect(screen.getByText("正式版更新 0.7.0")).toBeTruthy();
  });

  it("filters to unread only", async () => {
    const screen = render(<Notifications />);
    pushFeed(FEED);
    await waitFor(() => screen.getByTestId("filter-unread"));
    fireEvent.click(screen.getByTestId("filter-unread"));
    expect(screen.queryByText(/ignore previous/)).toBeNull();
  });

  it("filters by kind", async () => {
    const screen = render(<Notifications />);
    pushFeed(FEED);
    await waitFor(() => screen.getByTestId("filter-kind-review"));
    fireEvent.click(screen.getByTestId("filter-kind-review"));
    expect(screen.queryByText(/正式版更新/)).toBeNull();
  });

  it("marks everything read", async () => {
    const screen = render(<Notifications />);
    pushFeed(FEED);
    await waitFor(() => screen.getByTestId("mark-all-read"));
    fireEvent.click(screen.getByTestId("mark-all-read"));
    expect(client.sent).toContainEqual({ type: "notifications.mark_read" });
  });

  it("sends clear after confirmation", async () => {
    const screen = render(<Notifications />);
    pushFeed(FEED);
    await waitFor(() => screen.getByTestId("clear-all"));
    fireEvent.click(screen.getByTestId("clear-all"));
    const confirm = await screen.findByTestId("clear-all-confirm");
    fireEvent.click(confirm);
    expect(client.sent).toContainEqual({ type: "notifications.clear" });
  });
});
