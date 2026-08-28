// SPDX-License-Identifier: MIT
import { describe, expect, it } from "vitest";
import { VAD_ASSET_BASE_PATH } from "./vadAssets";

describe("vadAssets", () => {
  it("points at the static-assets vad dir served by the backend", () => {
    expect(VAD_ASSET_BASE_PATH).toBe("/assets/vad/");
  });
});
