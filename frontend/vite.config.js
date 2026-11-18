import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // Needed so file changes on Windows are picked up inside Docker
    watch: { usePolling: true },
    proxy: {
      "/api": { target: "http://backend:8000", changeOrigin: true },
      "/ws": { target: "ws://backend:8000", ws: true },
    },
  },
});