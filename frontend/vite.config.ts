import path from "node:path"
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"

export default defineConfig({
  base: "/ops/",
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  build: {
    sourcemap: false,
  },
  server: {
    proxy: {
      "/health": "http://localhost:8000",
      "/auth/admin": "http://localhost:8000",
      "/admin": "http://localhost:8000",
    },
  },
})
