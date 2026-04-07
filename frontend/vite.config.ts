import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const apiTarget = process.env.VITE_API_TARGET || "http://localhost:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    allowedHosts: ["llmtest.ryanmihelich.com"],
    proxy: {
      "/api/speech/generate-wavs/stream": {
        target: apiTarget,
        changeOrigin: true,
        // SSE must not be buffered or compressed
        headers: { "Accept-Encoding": "identity" },
      },
      "/api/ws": {
        target: apiTarget,
        changeOrigin: true,
        ws: true,
      },
      "/api": {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
});
