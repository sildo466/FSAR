// SPDX-License-Identifier: MIT
import { afterEach, describe, expect, it } from "vitest";
import { act, cleanup, renderHook } from "@testing-library/react";
import { useWS } from "../stores/ws";
import { useSkinStore } from "../stores/skin";
import { applyBackgroundToCss, applySkinToCss, clearSkinCss, resolveBackground, resolveSkin, toRgba, useSkinApplication } from "./skin";

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

  it("does not revert active skin on unrelated config changes", () => {
    useSkinStore.setState({ skins: [], status: "ready", activeId: "default" });
    useWS.setState({ config: { style: { skin_id: "night" } } });
    renderHook(() => useSkinApplication());
    expect(useSkinStore.getState().activeId).toBe("night");

    act(() => useSkinStore.setState({ activeId: "warm" }));
    act(() => useWS.setState({ config: { style: { skin_id: "night" }, other: true } }));
    expect(useSkinStore.getState().activeId).toBe("warm");

    useWS.setState({ config: null });
  });
});

describe("toRgba", () => {
  it("parses hex short / hex long / rgb / rgba", () => {
    expect(toRgba("#fa8", 0.5)).toBe("rgba(255, 170, 136, 0.5)");
    expect(toRgba("#faf8f5", 0.85)).toBe("rgba(250, 248, 245, 0.85)");
    expect(toRgba("rgb(17, 17, 17)", 0.1)).toBe("rgba(17, 17, 17, 0.1)");
    expect(toRgba("rgba(255, 255, 255, 0.72)", 0.3)).toBe("rgba(255, 255, 255, 0.3)");
  });
  it("returns null for unparseable input", () => {
    expect(toRgba("bogus", 0.5)).toBeNull();
  });
});

describe("resolveBackground", () => {
  it("builds overlay from bg color at chatOverlay alpha", () => {
    const r = resolveBackground("#faf8f5", { chatImage: "/skin-assets/warm/bg.png", chatOverlay: 0.88 });
    expect(r.chatImage).toBe("/skin-assets/warm/bg.png");
    expect(r.overlay).toBe("rgba(250, 248, 245, 0.88)");
  });
  it("defaults alpha to 0.85 and clamps", () => {
    expect(resolveBackground("#000", { chatImage: "x" }).overlay).toBe("rgba(0, 0, 0, 0.85)");
    expect(resolveBackground("#000", { chatImage: "x", chatOverlay: 2 }).overlay).toBe("rgba(0, 0, 0, 1)");
  });
  it("returns nulls when no image", () => {
    expect(resolveBackground("#faf8f5", undefined)).toEqual({ chatImage: null, overlay: null });
    expect(resolveBackground("#faf8f5", { chatImage: "", chatOverlay: 0.85 })).toEqual({ chatImage: null, overlay: null });
  });
});

describe("applyBackgroundToCss", () => {
  it("writes image+overlay vars and removes them when empty", () => {
    const root = document.documentElement;
    applyBackgroundToCss(root, { chatImage: "/skin-assets/warm/bg.png", overlay: "rgba(250, 248, 245, 0.88)" });
    expect(root.style.getPropertyValue("--chat-bg-image")).toBe('url("/skin-assets/warm/bg.png")');
    expect(root.style.getPropertyValue("--chat-bg-overlay")).toBe("rgba(250, 248, 245, 0.88)");
    applyBackgroundToCss(root, { chatImage: null, overlay: null });
    expect(root.style.getPropertyValue("--chat-bg-image")).toBe("");
    expect(root.style.getPropertyValue("--chat-bg-overlay")).toBe("");
  });
});
