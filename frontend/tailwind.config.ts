import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        surface: "var(--surface)",
        text: "var(--text)",
        "text-muted": "var(--text-muted)",
        "text-faint": "var(--text-faint)",
        border: "var(--border)",
        "border-strong": "var(--border-strong)",
      },
      fontFamily: {
        sans: ["Inter Variable", "Inter", "system-ui", "sans-serif"],
        display: ["Geist Sans Variable", "Geist Sans", "system-ui", "sans-serif"],
        mono: ["Geist Mono Variable", "Geist Mono", "monospace"],
      },
    },
  },
} satisfies Config;
