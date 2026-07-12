import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { extensions: [".tsx", ".ts", ".jsx", ".js", ".json"] },
  server: { port: 1420, strictPort: true },
  test: { environment: "jsdom" },
});
