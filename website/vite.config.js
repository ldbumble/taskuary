// Builds straight into the Python package: taskuary/web/{index.html, assets/*} is what
// FastAPI serves and what pip/PyInstaller ship - node is a build-time dependency only.
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: { outDir: "../taskuary/web", emptyOutDir: true },
  // TASKUARY_API points the dev server at another backend (a --demo instance, a blank home) without touching the one you run
  server: { proxy: { "/api": { target: process.env.TASKUARY_API || "http://127.0.0.1:7787", ws: true } } },
});
