// SPDX-License-Identifier: MIT
import { describe, expect, it, vi } from "vitest";
import { isWebGLAvailable } from "./webgl";

describe("isWebGLAvailable", () => {
  it("returns a boolean without throwing in jsdom", () => {
    vi.stubGlobal("HTMLCanvasElement", class {
      getContext(): null {
        return null;
      }
    } as unknown as typeof HTMLCanvasElement);
    expect(typeof isWebGLAvailable()).toBe("boolean");
  });
});
