// SPDX-License-Identifier: MIT
import { describe, expect, it } from "vitest";
import { buildModelUrl, getModelKind } from "./modelKind";

describe("getModelKind", () => {
  it("returns none for null", () => {
    expect(getModelKind(null)).toBe("none");
  });
  it("returns vrm for .vrm names", () => {
    expect(getModelKind("girl.vrm")).toBe("vrm");
  });
  it("returns live2d for .model3.json paths", () => {
    expect(getModelKind("hiyori/hiyori.model3.json")).toBe("live2d");
  });
  it("is case-insensitive", () => {
    expect(getModelKind("Hiyori/HIYORI.MODEL3.JSON")).toBe("live2d");
  });
});

describe("buildModelUrl", () => {
  it("encodes each path segment without breaking slashes", () => {
    expect(buildModelUrl("hiyori/hiyori.model3.json")).toBe(
      "/api/models/hiyori/hiyori.model3.json"
    );
  });
  it("encodes spaces and special chars per segment", () => {
    expect(buildModelUrl("my girl/a vrm.vrm")).toBe(
      "/api/models/my%20girl/a%20vrm.vrm"
    );
  });
});
