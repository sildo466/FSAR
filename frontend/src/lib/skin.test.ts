// SPDX-License-Identifier: MIT
import { afterEach, describe, expect, it } from "vitest";
import { act, cleanup, renderHook } from "@testing-library/react";
import { useWS } from "../stores/ws";
import { useSkinStore } from "../stores/skin";
import { applySkinToCss, clearSkinCss, resolveSkin, useSkinApplication } from "./skin";

afterEach(() => cleanup());

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

describe("useSkinApplication", () => {
  it("applies tokens for active skin and clears on default", () => {
    useSkinStore.setState({
      skins: [{ id: "warm", name: "暖阳", base: "light", palette: { bg: "#faf8f5", accent: "#d4a04a" } }],
      status: "ready",
      activeId: "default",
    });
    renderHook(() => useSkinApplication());
    const root = document.documentElement;

    act(() => useSkinStore.setState({ activeId: "warm" }));
    expect(root.style.getPropertyValue("--bg")).toBe("#faf8f5");
    expect(root.style.getPropertyValue("--accent")).toBe("#d4a04a");
    expect(root.style.getPropertyValue("--border")).toBe("rgba(17, 17, 17, 0.1)");

    act(() => useSkinStore.setState({ activeId: "default" }));
    expect(root.style.getPropertyValue("--bg")).toBe("");
    expect(root.style.getPropertyValue("--accent")).toBe("");
  });

  it("clears css when active skin is missing", () => {
    useSkinStore.setState({ skins: [], status: "ready", activeId: "ghost" });
    renderHook(() => useSkinApplication());
    expect(document.documentElement.style.getPropertyValue("--bg")).toBe("");
  });

  it("sends skin.list once when ws client becomes available", () => {
    const sent: Array<Record<string, unknown>> = [];
    useWS.setState({ client: { send: (m: Record<string, unknown>) => sent.push(m) } as never });
    renderHook(() => useSkinApplication());
    expect(sent).toEqual([{ type: "skin.list" }]);
    useWS.setState({ client: null });
  });
});
