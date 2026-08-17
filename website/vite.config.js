// Builds straight into the Python package: taskuary/web/{index.html, assets/*} is what
// FastAPI serves and what pip/PyInstaller ship - node is a build-time dependency only.
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: { outDir: "../taskuary/web", emptyOutDir: true },
  server: { proxy: { "/api": "http://127.0.0.1:7787" } },
});
