import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Build output goes into the FastAPI static tree so the backend can serve the
// 3D app. The 2D app/static/index.html stays until phase 5 archive.
export default defineConfig({
  plugins: [react()],
  base: "/3d/",
  build: {
    outDir: "../app/static/3d",
    emptyOutDir: false,
  },
  server: {
    port: 5174,
    proxy: {
      "/ws": { target: "ws://localhost:8000", ws: true },
      "/api": { target: "http://localhost:8000" },
    },
  },
});
