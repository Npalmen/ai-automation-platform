import path from "node:path"
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"

export default defineConfig({
  base: "/app/",
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  build: {
    outDir: "dist-customer",
    sourcemap: false,
    emptyOutDir: true,
    rollupOptions: {
      input: {
        index: path.resolve(__dirname, "customer.html"),
      },
    },
  },
  server: {
    proxy: {
      "/health": "http://localhost:8000",
    },
  },
})
