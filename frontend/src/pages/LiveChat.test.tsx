// SPDX-License-Identifier: MIT
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import { LiveChat } from "./LiveChat";

vi.mock("../components/live/AvatarCanvas", () => ({
  AvatarCanvas: () => <div data-testid="avatar-canvas" />,
}));

afterEach(() => cleanup());

const config = { characterId: 1, userCardId: null, model: null };

describe("LiveChat", () => {
  it("shows the subtitle slot, a disabled mic, and an exit button", () => {
    render(<LiveChat config={config} onExit={vi.fn()} />);
    expect(screen.getByText(/live subtitles/i)).toBeTruthy();
    const mic = screen.getByRole("button", { name: /mic/i }) as HTMLButtonElement;
    expect(mic.disabled).toBe(true);
    expect(screen.getByRole("button", { name: /exit/i })).toBeTruthy();
  });

  it("calls onExit when the exit button is clicked", () => {
    const onExit = vi.fn();
    render(<LiveChat config={config} onExit={onExit} />);
    fireEvent.click(screen.getByRole("button", { name: /exit/i }));
    expect(onExit).toHaveBeenCalledTimes(1);
  });
});
