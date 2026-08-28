import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { viteStaticCopy } from "vite-plugin-static-copy";

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    viteStaticCopy({
      targets: [
        {
          src: "node_modules/@ricky0123/vad-web/dist/vad.worklet.bundle.min.js",
          dest: "assets/vad",
        },
        {
          src: "node_modules/@ricky0123/vad-web/dist/*.onnx",
          dest: "assets/vad",
        },
        {
          src: "node_modules/onnxruntime-web/dist/*.wasm",
          dest: "assets/vad",
        },
        {
          src: "node_modules/onnxruntime-web/dist/*.mjs",
          dest: "assets/vad",
        },
      ],
    }),
  ],
  resolve: { extensions: [".tsx", ".ts", ".jsx", ".js", ".json"] },
  server: { port: 1420, strictPort: true },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
