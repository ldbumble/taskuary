// Builds straight into the Python package: taskuary/web/{index.html, assets/*} is what
// FastAPI serves and what pip/PyInstaller ship - node is a build-time dependency only.
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

// Outside the static demo every reader of demoApi.js checks DEMO first and never touches the recording, yet the
// recording (400 KB of fixtures plus the scripted world) was parsed and run on every page load. There the module
// is demoOff.js, which answers the same names with "not the demo".
const demoOff = (mode) => loadEnv(mode, fileURLToPath(new URL(".", import.meta.url)), "VITE_").VITE_DEMO === "1" ? []
  : [{ find: /^\.\/demoApi\.js$/, replacement: fileURLToPath(new URL("./src/demoOff.js", import.meta.url)) }];
export default defineConfig(({ mode }) => ({
  plugins: [react()],
  resolve: { alias: demoOff(mode) },
  build: { outDir: "../taskuary/web", emptyOutDir: true },
  // TASKUARY_API points the dev server at another backend (a --demo instance, a blank home) without touching the one you run
  server: { proxy: { "/api": { target: process.env.TASKUARY_API || "http://127.0.0.1:7787", ws: true } } },
}));
