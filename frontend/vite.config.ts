import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const normalizeHtmlLineEndings = {
  name: "normalize-html-line-endings",
  enforce: "pre" as const,
  transformIndexHtml(html: string) {
    // Vite injects the bundle tag with LF. Normalizing the CRLF source first
    // prevents a mixed-terminator release file and keeps git diff checks clean.
    return html.replace(/\r\n?/g, "\n");
  },
};

// Build output goes into the FastAPI static tree so the backend can serve the
// 3D app. The 2D app/static/index.html stays until phase 5 archive.
export default defineConfig({
  plugins: [normalizeHtmlLineEndings, react()],
  base: "/3d/",
  build: {
    outDir: "../app/static/3d",
    emptyOutDir: false,
    rollupOptions: {
      output: {
        // Stable entry filename prevents index.html from pointing at an
        // uncommitted content-hash bundle after a clean checkout/deploy.
        entryFileNames: "assets/app.js",
      },
    },
  },
  server: {
    port: 5174,
    proxy: {
      "/ws": { target: "ws://localhost:8000", ws: true },
      "/api": { target: "http://localhost:8000" },
    },
  },
});
