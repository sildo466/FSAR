// SPDX-License-Identifier: MIT
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
}
