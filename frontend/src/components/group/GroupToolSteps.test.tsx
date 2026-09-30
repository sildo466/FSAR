// SPDX-License-Identifier: MIT
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { GroupToolSteps } from "./GroupToolSteps";

const steps = [
  { callId: "c1", tool: "read_file", argsPreview: "one", result: "r1", latencyMs: 1 },
  { callId: "c2", tool: "edit", argsPreview: "two", result: "r2", latencyMs: 2 },
  { callId: "c3", tool: "run_command", argsPreview: "three" },
];

afterEach(cleanup);

describe("GroupToolSteps", () => {
  it("renders nothing when the turn ran no tools", () => {
    const { container } = render(<GroupToolSteps steps={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("folds the older steps away and leaves the newest showing", () => {
    render(<GroupToolSteps steps={steps} />);
    const folded = screen.getByTestId("folded-tool-steps");
    // jsdom does not lay out <details>, so "folded" is the open attribute
    // rather than visibility — a closed details element IS the fold.
    expect(folded.getAttribute("open")).toBeNull();
    // And the newest step is outside it, so it is on screen either way.
    expect(folded.contains(screen.getByText("run_command"))).toBe(false);
  });

  it("says how many steps are folded away", () => {
    render(<GroupToolSteps steps={steps} />);
    expect(screen.getByTestId("folded-tool-steps").textContent).toContain("2");
  });

  it("shows every step once the reader opens it", () => {
    render(<GroupToolSteps steps={steps} defaultOpen />);
    const folded = screen.getByTestId("folded-tool-steps");
    expect(folded.getAttribute("open")).not.toBeNull();
    expect(folded.textContent).toContain("read_file");
    expect(folded.textContent).toContain("edit");
  });

  it("does not fold a single step", () => {
    render(<GroupToolSteps steps={[steps[0]]} />);
    expect(screen.queryByTestId("folded-tool-steps")).toBeNull();
    expect(screen.getByText("read_file")).toBeTruthy();
  });
});
