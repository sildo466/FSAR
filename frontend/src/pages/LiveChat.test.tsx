// SPDX-License-Identifier: MIT
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import { LiveChat } from "./LiveChat";
import { initI18n } from "../lib/i18nSetup";
import i18n from "../lib/i18nSetup";

const liveVoice = vi.hoisted(() => ({
  muted: false,
  listening: true,
  userSpeaking: false,
  permissionDenied: false,
  vadError: null,
  asrNotConfigured: false,
  userLines: [] as { id: string; role: "user"; text: string }[],
  busy: false,
  level: 0,
  subscribeLevel: vi.fn(() => () => {}),
  toggleMute: vi.fn(),
  retryVad: vi.fn(),
  sendNow: vi.fn(),
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

beforeAll(async () => {
  await initI18n("en");
});

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
    const mic = screen.getByRole("button", { name: i18n.t("live.micToggle.mute") });
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
