// SPDX-License-Identifier: MIT
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { LiveBackground } from "./LiveBackground";

afterEach(() => cleanup());

describe("LiveBackground", () => {
  it("renders the deepspace layer for the default scene", () => {
    render(<LiveBackground scene="deepspace" />);
    const el = screen.getByTestId("live-bg");
    expect(el.className).toContain("deepspace");
  });
  it("renders an image layer when scene is image:<path>", () => {
    render(<LiveBackground scene="image:/skin-assets/a/bg.png" />);
    const el = screen.getByTestId("live-bg");
    expect(el.className).not.toContain("deepspace");
  });
});
