// SPDX-License-Identifier: MIT
import { describe, expect, it } from "vitest";
import {
  computeMouthOpen,
  mapPresetToLive2DExpression,
} from "./Live2DAvatar";

describe("mapPresetToLive2DExpression", () => {
  it("passes through known expression names", () => {
    expect(mapPresetToLive2DExpression("happy")).toBe("happy");
    expect(mapPresetToLive2DExpression("sad")).toBe("sad");
  });
  it("maps relaxed to the empty expression", () => {
    expect(mapPresetToLive2DExpression("relaxed")).toBe("");
  });
});

describe("computeMouthOpen", () => {
  it("clamps volume to 0..1", () => {
    expect(computeMouthOpen(0.5)).toBeCloseTo(0.5);
    expect(computeMouthOpen(2)).toBe(1);
    expect(computeMouthOpen(-1)).toBe(0);
  });
});
