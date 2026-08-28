// SPDX-License-Identifier: MIT
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MicToggle } from "./MicToggle";

afterEach(() => cleanup());

describe("MicToggle", () => {
  it("calls onToggle on click", () => {
    const onToggle = vi.fn();
    render(
      <MicToggle muted={false} listening onToggle={onToggle} userSpeaking={false} />
    );
    fireEvent.click(screen.getByRole("button"));
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it("labels itself as muted when muted", () => {
    render(<MicToggle muted listening onToggle={vi.fn()} userSpeaking={false} />);
    expect(screen.getByLabelText(/unmute/i)).toBeTruthy();
  });
});
