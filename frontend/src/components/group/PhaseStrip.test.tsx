// SPDX-License-Identifier: MIT
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { PhaseStrip } from "./PhaseStrip";
import type { RoomPhase } from "../../stores/group";

function renderStrip(phase: RoomPhase, reason = "") {
  const onSetGoal = vi.fn();
  const onConfirmDone = vi.fn();
  render(
    <PhaseStrip
      phase={phase}
      reason={reason}
      onSetGoal={onSetGoal}
      onConfirmDone={onConfirmDone}
    />
  );
  return { onSetGoal, onConfirmDone };
}

afterEach(cleanup);

describe("PhaseStrip", () => {
  it("carries the phase and the reason it changed", () => {
    renderStrip("review", "all_blocked");
    const strip = screen.getByTestId("phase-strip");
    expect(strip.getAttribute("data-phase")).toBe("review");
    expect(strip.getAttribute("data-reason")).toBe("all_blocked");
  });

  it("offers the goal field before planning has begun", () => {
    renderStrip("chat");
    expect(screen.getByTestId("goal-form")).toBeTruthy();
  });

  it("takes the goal field away once the room is moving", () => {
    renderStrip("working");
    expect(screen.queryByTestId("goal-form")).toBeNull();
  });

  it("offers the confirm button only in review", () => {
    renderStrip("working");
    expect(screen.queryByTestId("confirm-done")).toBeNull();
  });

  it("offers the confirm button in review", () => {
    renderStrip("review");
    expect(screen.getByTestId("confirm-done")).toBeTruthy();
  });

  it("hands the goal back to the caller", () => {
    const { onSetGoal } = renderStrip("chat");
    fireEvent.change(screen.getByTestId("goal-input"), {
      target: { value: "ship the parser" },
    });
    fireEvent.submit(screen.getByTestId("goal-form"));
    expect(onSetGoal).toHaveBeenCalledWith("ship the parser");
  });

  it("trims the goal before handing it over", () => {
    const { onSetGoal } = renderStrip("chat");
    fireEvent.change(screen.getByTestId("goal-input"), {
      target: { value: "  ship it  " },
    });
    fireEvent.submit(screen.getByTestId("goal-form"));
    expect(onSetGoal).toHaveBeenCalledWith("ship it");
  });

  it("does not hand over an empty goal", () => {
    const { onSetGoal } = renderStrip("chat");
    fireEvent.change(screen.getByTestId("goal-input"), { target: { value: "   " } });
    fireEvent.submit(screen.getByTestId("goal-form"));
    expect(onSetGoal).not.toHaveBeenCalled();
  });

  it("reports the confirm click", () => {
    const { onConfirmDone } = renderStrip("review");
    fireEvent.click(screen.getByTestId("confirm-done"));
    expect(onConfirmDone).toHaveBeenCalled();
  });

  it("shows no reason line when nothing has moved yet", () => {
    renderStrip("chat");
    expect(screen.queryByTestId("phase-reason")).toBeNull();
  });
});
