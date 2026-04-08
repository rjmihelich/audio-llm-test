import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"

const apiTarget = process.env.VITE_API_TARGET || "http://localhost:8000"

export default defineConfig({
  base: "/pipeline-studio/",
  plugins: [react(), tailwindcss()],
  server: {
    port: 5174,
    hmr: {
      path: "/pipeline-studio/",
    },
    proxy: {
      "/api/pipelines": {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
})
