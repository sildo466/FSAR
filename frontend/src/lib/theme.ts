// SPDX-License-Identifier: MIT
import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { useUI, type Theme } from "../stores/ui";

function systemPrefersDark(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

export function useThemeApplication(): "light" | "dark" {
  const theme = useUI((s) => s.theme);

  const resolved: "light" | "dark" =
    theme === "system" ? (systemPrefersDark() ? "dark" : "light") : theme;

  useEffect(() => {
    const root = document.documentElement;
    root.setAttribute("data-theme", resolved);
    return () => {
      root.removeAttribute("data-theme");
    };
  }, [resolved]);

  useEffect(() => {
    if (typeof window === "undefined" || theme !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = () => {
      const r = mq.matches ? "dark" : "light";
      document.documentElement.setAttribute("data-theme", r);
    };
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [theme]);

  return resolved;
}

export function useMotionApplication(): void {
  const motion = useUI((s) => s.motion);
  useEffect(() => {
    const root = document.documentElement;
    root.setAttribute("data-motion", motion);
    return () => {
      root.removeAttribute("data-motion");
    };
  }, [motion]);
}

export function useFontScaleApplication(): void {
  const scale = useUI((s) => s.fontScale);
  const fontSet = useUI((s) => s.fontSet);
  useEffect(() => {
    const root = document.documentElement;
    root.style.setProperty("--font-scale", String(scale));
    root.setAttribute("data-font-set", fontSet);
    return () => {
      root.style.removeProperty("--font-scale");
      root.removeAttribute("data-font-set");
    };
  }, [scale, fontSet]);
}

export function useDensityClass(): string {
  const density = useUI((s) => s.density);
  return density === "compact" ? "density-compact" : "";
}

export function cycleTheme(current: Theme): Theme {
  if (current === "light") return "dark";
  if (current === "dark") return "system";
  return "light";
}

export function useResolvedStyle() {
  const location = useLocation();
  const theme = useUI((s) => s.theme);
  const density = useUI((s) => s.density);
  const motion = useUI((s) => s.motion);
  const overrides = useUI((s) => s.perPageOverrides);

  const page = location.pathname === "/" ? "chat" : location.pathname.slice(1);
  const o = overrides[page] || {};
  return {
    theme: o.theme ?? theme,
    density: o.density ?? density,
    motion: o.motion ?? motion,
    page,
  };
}
