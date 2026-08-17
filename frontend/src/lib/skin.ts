// SPDX-License-Identifier: MIT
import { useEffect, useRef } from "react";
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

export const ELEMENT_KEYS = {
  input: ["bg", "border", "text"],
  button: ["bg", "text", "hover", "image", "imageOpacity"],
  switch: ["on", "off", "thumb"],
  chip: ["bg", "border"],
  card: ["bg", "border", "image", "imageOpacity"],
} as const;
export type ElementName = keyof typeof ELEMENT_KEYS;
export type SkinElementsInput = Partial<Record<ElementName, Partial<Record<string, unknown>>>>;

export interface ElementTokens {
  input: { bg: string; border: string; text: string };
  button: { bg: string; text: string; hover: string; image: string | null; imageOpacity: number };
  switch: { on: string; off: string; thumb: string };
  chip: { bg: string; border: string };
  card: { bg: string; border: string; image: string | null; imageOpacity: number };
}
export interface PatternTokens { image: string | null; opacity: number; }
export type SkinPatternInput = Partial<PatternTokens>;
export interface ResolvedSkin {
  colors: TokenMap;
  elements: ElementTokens;
  pattern: PatternTokens;
}

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

function clamp01(n: unknown, fallback: number): number {
  if (typeof n !== "number" || Number.isNaN(n)) return fallback;
  return Math.min(1, Math.max(0, n));
}
function str(v: unknown): string | null {
  return typeof v === "string" && v !== "" ? v : null;
}

export function resolveSkin(skin: {
  base?: string;
  palette?: Partial<TokenMap>;
  elements?: SkinElementsInput;
  pattern?: SkinPatternInput;
} | null): ResolvedSkin {
  if (!skin) {
    const colors = { ...DEFAULT_TOKENS.light };
    return { colors, elements: deriveElements(colors, undefined), pattern: { image: null, opacity: 0.06 } };
  }
  const base: BaseMode = skin.base === "dark" ? "dark" : "light";
  const colors = { ...DEFAULT_TOKENS[base], ...(skin.palette ?? {}) };
  const elements = deriveElements(colors, skin.elements);
  const pattern: PatternTokens = {
    image: str(skin.pattern?.image),
    opacity: clamp01(skin.pattern?.opacity, 0.06),
  };
  return { colors, elements, pattern };
}

function deriveElements(colors: TokenMap, overrides: SkinElementsInput | undefined): ElementTokens {
  const o = overrides ?? {};
  const inputO = o.input ?? {};
  const buttonO = o.button ?? {};
  const switchO = o.switch ?? {};
  const chipO = o.chip ?? {};
  const cardO = o.card ?? {};
  return {
    input: {
      bg: str(inputO.bg) ?? colors.glass,
      border: str(inputO.border) ?? colors.glassBorder,
      text: str(inputO.text) ?? colors.text,
    },
    button: {
      bg: str(buttonO.bg) ?? colors.accent,
      text: str(buttonO.text) ?? colors.bg,
      hover: str(buttonO.hover) ?? colors.accent,
      image: str(buttonO.image),
      imageOpacity: clamp01(buttonO.imageOpacity, 1),
    },
    switch: {
      on: str(switchO.on) ?? colors.accent,
      off: str(switchO.off) ?? colors.borderStrong,
      thumb: str(switchO.thumb) ?? colors.surface2,
    },
    chip: {
      bg: str(chipO.bg) ?? colors.glowFaint,
      border: str(chipO.border) ?? colors.border,
    },
    card: {
      bg: str(cardO.bg) ?? colors.glass,
      border: str(cardO.border) ?? colors.glassBorder,
      image: str(cardO.image),
      imageOpacity: clamp01(cardO.imageOpacity, 1),
    },
  };
}

const ELEMENT_VAR_MAP: Array<[string, (e: ElementTokens) => string]> = [
  ["--input-bg", (e) => e.input.bg],
  ["--input-border", (e) => e.input.border],
  ["--input-text", (e) => e.input.text],
  ["--button-bg", (e) => e.button.bg],
  ["--button-text", (e) => e.button.text],
  ["--button-hover", (e) => e.button.hover],
  ["--button-bg-image", (e) => e.button.image ? `url("${e.button.image}")` : "none"],
  ["--button-bg-opacity", (e) => String(e.button.imageOpacity)],
  ["--switch-on", (e) => e.switch.on],
  ["--switch-off", (e) => e.switch.off],
  ["--switch-thumb", (e) => e.switch.thumb],
  ["--chip-bg", (e) => e.chip.bg],
  ["--chip-border", (e) => e.chip.border],
  ["--card-bg", (e) => e.card.bg],
  ["--card-border", (e) => e.card.border],
  ["--card-bg-image", (e) => e.card.image ? `url("${e.card.image}")` : "none"],
  ["--card-bg-opacity", (e) => String(e.card.imageOpacity)],
] as const;

export function applySkinToCss(root: HTMLElement, resolved: ResolvedSkin): void {
  for (const { key, cssVar } of TOKENS) root.style.setProperty(cssVar, resolved.colors[key]);
  for (const [cssVar, pick] of ELEMENT_VAR_MAP) root.style.setProperty(cssVar, pick(resolved.elements));
  if (resolved.pattern.image) {
    const tint = toRgba(resolved.colors.bg, 1 - resolved.pattern.opacity) ?? "rgba(0,0,0,0.94)";
    root.style.setProperty("--app-texture", `linear-gradient(${tint}, ${tint}), url("${resolved.pattern.image}")`);
  } else {
    root.style.removeProperty("--app-texture");
  }
}

export function clearSkinCss(root: HTMLElement): void {
  for (const { cssVar } of TOKENS) root.style.removeProperty(cssVar);
  for (const [cssVar] of ELEMENT_VAR_MAP) root.style.removeProperty(cssVar);
  root.style.removeProperty("--app-texture");
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

  const hydratedRef = useRef(false);
  useEffect(() => {
    if (!config || hydratedRef.current) return;
    hydratedRef.current = true;
    const style = (config.style ?? {}) as { skin_id?: unknown };
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
    const resolved = resolveSkin(skin);
    applySkinToCss(root, resolved);
    applyBackgroundToCss(root, resolveBackground(resolved.colors.bg, skin.background));
  }, [activeId, skins]);
}
