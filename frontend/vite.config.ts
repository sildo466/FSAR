import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { extensions: [".tsx", ".ts", ".jsx", ".js", ".json"] },
  server: { port: 1420, strictPort: true },
  // wlipsync ships a single-file bundle that uses top-level await for its
  // WASM initialization; needs es2022+ (chrome89+ / safari15+).
  build: { target: "es2022" },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
