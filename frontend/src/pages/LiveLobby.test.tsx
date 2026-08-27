// SPDX-License-Identifier: MIT
import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { LiveLobby } from "./LiveLobby";

vi.mock("../components/live/ModelPicker", () => ({
  ModelPicker: ({ onSelect }: { onSelect: (n: string | null) => void }) => (
    <button onClick={() => onSelect("girl.vrm")}>pick</button>
  ),
}));

const characters = [{ id: 1, name: "Mio", description: "d", personality: "p", is_default: 0 }];
const userCards = [{ id: 9, name: "You", description: "d", is_default: 0 }];

describe("LiveLobby", () => {
  it("Start is disabled until a character is chosen", () => {
    render(
      <LiveLobby characters={characters} userCards={userCards} onStart={vi.fn()} />
    );
    expect(
      (screen.getByRole("button", { name: /start/i }) as HTMLButtonElement).disabled
    ).toBe(true);
    fireEvent.change(screen.getByLabelText(/character/i), {
      target: { value: "1" },
    });
    expect(
      (screen.getByRole("button", { name: /start/i }) as HTMLButtonElement).disabled
    ).toBe(false);
  });
});
