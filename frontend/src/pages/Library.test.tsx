import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { ClientMsg, ServerMsg } from "../lib/ws-client";
import { initI18n } from "../lib/i18nSetup";
import { fetchWSToken, useWS } from "../stores/ws";
import { Library } from "./Library";
import { open } from "@tauri-apps/plugin-dialog";

vi.mock("@tauri-apps/plugin-dialog", () => ({ open: vi.fn() }));
vi.mock("../stores/ws", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../stores/ws")>();
  return { ...actual, fetchWSToken: vi.fn() };
});

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
}

beforeAll(async () => {
  await initI18n("en");
});

beforeEach(() => {
  (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__ = {};
  vi.mocked(fetchWSToken).mockReset();
  vi.mocked(open).mockReset();
  useWS.setState({ client: new FakeClient() as never });
});

afterEach(() => {
  delete (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__;
  vi.unstubAllGlobals();
  cleanup();
});

describe("Library skill install", () => {
  it("does not request an install when folder selection is cancelled", async () => {
    vi.mocked(open).mockResolvedValue(null);
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const screen = render(<Library />);

    fireEvent.click(screen.getByRole("button", { name: "Install Skill" }));

    await waitFor(() => expect(open).toHaveBeenCalled());
    expect(fetchMock).not.toHaveBeenCalled();
    expect(fetchWSToken).not.toHaveBeenCalled();
  });

  it("posts the selected folder with bearer authentication", async () => {
    vi.mocked(open).mockResolvedValue("C:\\skills\\demo");
    vi.mocked(fetchWSToken).mockResolvedValue("test-token");
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ name: "demo", scripts: 1, references: 2, templates: 3 }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const screen = render(<Library />);

    fireEvent.click(screen.getByRole("button", { name: "Install Skill" }));

    await screen.findByText("Installed demo: 1 scripts, 2 references, 3 templates.");
    expect(fetchMock).toHaveBeenCalledWith("/api/skill/install", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        Authorization: "Bearer test-token",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ folder_path: "C:\\skills\\demo" }),
    });
  });

  it("shows server errors and re-enables the install button", async () => {
    vi.mocked(open).mockResolvedValue("C:\\skills\\bad");
    vi.mocked(fetchWSToken).mockResolvedValue("test-token");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({ detail: "missing_name" }),
    }));
    const screen = render(<Library />);

    fireEvent.click(screen.getByRole("button", { name: "Install Skill" }));

    await screen.findByRole("alert");
    expect(screen.getByText("Install failed: missing_name")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Install Skill" }) as HTMLButtonElement).disabled).toBe(false);
  });
});
