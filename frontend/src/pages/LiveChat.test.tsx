// SPDX-License-Identifier: MIT
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import { LiveChat } from "./LiveChat";

const liveVoice = vi.hoisted(() => ({
  muted: false,
  listening: true,
  userSpeaking: false,
  permissionDenied: false,
  vadError: null,
  asrNotConfigured: false,
  userLines: [] as { id: string; role: "user"; text: string }[],
  busy: false,
  toggleMute: vi.fn(),
  retryVad: vi.fn(),
}));

vi.mock("../components/live/AvatarCanvas", () => ({
  AvatarCanvas: () => <div data-testid="avatar-canvas" />,
}));

vi.mock("../components/live/useLiveVoice", () => ({
  useLiveVoice: () => liveVoice,
}));

vi.mock("../stores/sessions", () => ({
  useSessions: (selector: (s: unknown) => unknown) =>
    selector({ liveHistory: {} }),
}));

vi.mock("../stores/cards", () => ({
  useCardsStore: (selector: (s: unknown) => unknown) =>
    selector({ characters: [] }),
}));

afterEach(() => {
  cleanup();
  liveVoice.userLines = [];
  liveVoice.vadError = null;
  liveVoice.asrNotConfigured = false;
});

const config = { characterId: 1, userCardId: null, model: null };

describe("LiveChat", () => {
  it("shows an enabled mic toggle wired to the voice hook", () => {
    render(<LiveChat config={config} onExit={vi.fn()} />);
    const mic = screen.getByRole("button", { name: /mute mic/i });
    expect(mic).toBeTruthy();
    fireEvent.click(mic);
    expect(liveVoice.toggleMute).toHaveBeenCalledTimes(1);
  });

  it("renders user subtitle lines from the hook", () => {
    liveVoice.userLines = [{ id: "u1", role: "user", text: "hello there" }];
    render(<LiveChat config={config} onExit={vi.fn()} />);
    expect(screen.getByText("hello there")).toBeTruthy();
  });

  it("calls onExit when the exit button is clicked", () => {
    const onExit = vi.fn();
    render(<LiveChat config={config} onExit={onExit} />);
    fireEvent.click(screen.getByRole("button", { name: /exit/i }));
    expect(onExit).toHaveBeenCalledTimes(1);
  });
});
