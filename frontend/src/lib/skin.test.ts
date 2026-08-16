// SPDX-License-Identifier: MIT
import { describe, expect, it } from "vitest";
import { applySkinToCss, clearSkinCss, resolveSkin } from "./skin";

describe("resolveSkin", () => {
  it("returns light defaults when skin is null", () => {
    const t = resolveSkin(null);
    expect(t.bg).toBe("#f5f5f2");
    expect(t.accent).toBe("#111111");
  });

  it("returns dark defaults for base dark", () => {
    const t = resolveSkin({ base: "dark", palette: {} });
    expect(t.bg).toBe("#0a0a0a");
    expect(t.accent).toBe("#f5f5f5");
  });

  it("overlays palette subset onto base defaults", () => {
    const t = resolveSkin({ base: "light", palette: { bg: "#faf8f5", accent: "#d4a04a" } });
    expect(t.bg).toBe("#faf8f5");
    expect(t.accent).toBe("#d4a04a");
    expect(t.border).toBe("rgba(17, 17, 17, 0.1)");
  });

  it("treats unknown base as light", () => {
    const t = resolveSkin({ base: "neon", palette: {} });
    expect(t.bg).toBe("#f5f5f2");
  });
});

describe("applySkinToCss / clearSkinCss", () => {
  it("writes inline css variables and clears them", () => {
    const root = document.documentElement;
    applySkinToCss(root, { ...resolveSkin(null), bg: "#faf8f5", accent: "#d4a04a", surface2: "rgba(0,0,0,0.03)" });
    expect(root.style.getPropertyValue("--bg")).toBe("#faf8f5");
    expect(root.style.getPropertyValue("--accent")).toBe("#d4a04a");
    expect(root.style.getPropertyValue("--surface-2")).toBe("rgba(0,0,0,0.03)");
    clearSkinCss(root);
    expect(root.style.getPropertyValue("--bg")).toBe("");
    expect(root.style.getPropertyValue("--accent")).toBe("");
  });
});
