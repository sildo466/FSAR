// SPDX-License-Identifier: MIT
import { useEffect } from "react";
import { useWS } from "../stores/ws";
import { useSkinStore } from "../stores/skin";

export type BaseMode = "light" | "dark";

export const TOKENS = [
  { key: "bg", cssVar: "--bg" },
  { key: "surface", cssVar: "--surface" },
  { key: "surface2", cssVar: "--surface-2" },
  { key: "text", cssVar: "--text" },
  { key: "textMuted", cssVar: "--text-muted" },
  { key: "textFaint", cssVar: "--text-faint" },
  { key: "border", cssVar: "--border" },
  { key: "borderStrong", cssVar: "--border-strong" },
  { key: "glass", cssVar: "--glass" },
  { key: "glassStrong", cssVar: "--glass-strong" },
  { key: "glassBorder", cssVar: "--glass-border" },
  { key: "glowSoft", cssVar: "--glow-soft" },
  { key: "glowFaint", cssVar: "--glow-faint" },
  { key: "success", cssVar: "--success" },
  { key: "warning", cssVar: "--warning" },
  { key: "danger", cssVar: "--danger" },
  { key: "accent", cssVar: "--accent" },
] as const;

export type TokenKey = (typeof TOKENS)[number]["key"];
export type TokenMap = Record<TokenKey, string>;

export const DEFAULT_TOKENS: Record<BaseMode, TokenMap> = {
  light: {
    bg: "#f5f5f2",
    surface: "rgba(255, 255, 255, 0.72)",
    surface2: "rgba(255, 255, 255, 0.9)",
    text: "#111111",
    textMuted: "#727272",
    textFaint: "#a5a5a5",
    border: "rgba(17, 17, 17, 0.1)",
    borderStrong: "rgba(17, 17, 17, 0.2)",
    glass: "rgba(255, 255, 255, 0.58)",
    glassStrong: "rgba(255, 255, 255, 0.82)",
    glassBorder: "rgba(17, 17, 17, 0.12)",
    glowSoft: "rgba(17, 17, 17, 0.14)",
    glowFaint: "rgba(17, 17, 17, 0.07)",
    success: "#16865b",
    warning: "#ad7414",
    danger: "#b94a4a",
    accent: "#111111",
  },
  dark: {
    bg: "#0a0a0a",
    surface: "rgba(20, 20, 20, 0.72)",
    surface2: "rgba(28, 28, 28, 0.92)",
    text: "#f5f5f5",
    textMuted: "#929292",
    textFaint: "#5e5e5e",
    border: "rgba(255, 255, 255, 0.09)",
    borderStrong: "rgba(255, 255, 255, 0.18)",
    glass: "rgba(255, 255, 255, 0.06)",
    glassStrong: "rgba(255, 255, 255, 0.1)",
    glassBorder: "rgba(255, 255, 255, 0.12)",
    glowSoft: "rgba(255, 255, 255, 0.18)",
    glowFaint: "rgba(255, 255, 255, 0.07)",
    success: "#55d39c",
    warning: "#f3bb54",
    danger: "#f08080",
    accent: "#f5f5f5",
  },
};

export function resolveSkin(skin: { base?: string; palette?: Partial<TokenMap> } | null): TokenMap {
  if (!skin) return { ...DEFAULT_TOKENS.light };
  const base: BaseMode = skin.base === "dark" ? "dark" : "light";
  return { ...DEFAULT_TOKENS[base], ...(skin.palette ?? {}) };
}

export function applySkinToCss(root: HTMLElement, tokens: TokenMap): void {
  for (const { key, cssVar } of TOKENS) root.style.setProperty(cssVar, tokens[key]);
}

export function clearSkinCss(root: HTMLElement): void {
  for (const { cssVar } of TOKENS) root.style.removeProperty(cssVar);
  root.style.removeProperty("--chat-bg-image");
  root.style.removeProperty("--chat-bg-overlay");
}

export interface SkinBackground {
  chatImage: string;
  chatOverlay: number;
}

export interface ResolvedBackground {
  chatImage: string | null;
  overlay: string | null;
}

export function toRgba(color: string, alpha: number): string | null {
  const s = color.trim();
  let m: RegExpMatchArray | null;
  if ((m = s.match(/^#([0-9a-f]{3})$/i))) {
    const [r, g, b] = [...m[1]].map((c) => parseInt(c + c, 16));
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }
  if ((m = s.match(/^#([0-9a-f]{6})$/i))) {
    return `rgba(${parseInt(m[1].slice(0, 2), 16)}, ${parseInt(m[1].slice(2, 4), 16)}, ${parseInt(m[1].slice(4, 6), 16)}, ${alpha})`;
  }
  if ((m = s.match(/^rgb\((\d+),\s*(\d+),\s*(\d+)\)$/i))) {
    return `rgba(${m[1]}, ${m[2]}, ${m[3]}, ${alpha})`;
  }
  if ((m = s.match(/^rgba\((\d+),\s*(\d+),\s*(\d+),\s*[\d.]+\)$/i))) {
    return `rgba(${m[1]}, ${m[2]}, ${m[3]}, ${alpha})`;
  }
  return null;
}

export function resolveBackground(
  bgColor: string,
  background: Partial<SkinBackground> | undefined,
): ResolvedBackground {
  const img = background?.chatImage;
  if (!img) return { chatImage: null, overlay: null };
  const raw = background?.chatOverlay ?? 0.85;
  const clamped = Math.min(1, Math.max(0, raw));
  const overlay = toRgba(bgColor, clamped);
  return { chatImage: img, overlay };
}

export function applyBackgroundToCss(root: HTMLElement, resolved: ResolvedBackground): void {
  if (resolved.chatImage) {
    root.style.setProperty("--chat-bg-image", `url("${resolved.chatImage}")`);
  } else {
    root.style.removeProperty("--chat-bg-image");
  }
  if (resolved.overlay) {
    root.style.setProperty("--chat-bg-overlay", resolved.overlay);
  } else {
    root.style.removeProperty("--chat-bg-overlay");
  }
}

export function useSkinApplication(): void {
  const client = useWS((s) => s.client);
  const config = useWS((s) => s.config);
  const activeId = useSkinStore((s) => s.activeId);
  const skins = useSkinStore((s) => s.skins);

  useEffect(() => {
    if (!client) return;
    useWS.getState().send({ type: "skin.list" });
  }, [client]);

  useEffect(() => {
    const style = (config?.style ?? {}) as { skin_id?: unknown };
    useSkinStore.getState().hydrate(style.skin_id);
  }, [config]);

  useEffect(() => {
    const root = document.documentElement;
    if (activeId === "default") {
      clearSkinCss(root);
      return;
    }
    const skin = skins.find((s) => s.id === activeId);
    if (!skin) {
      clearSkinCss(root);
      return;
    }
    const tokens = resolveSkin(skin);
    applySkinToCss(root, tokens);
    applyBackgroundToCss(root, resolveBackground(tokens.bg, skin.background));
  }, [activeId, skins]);
}
