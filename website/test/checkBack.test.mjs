import test from "node:test";
import assert from "node:assert/strict";
import { checkBackLine, checkBackOf, checkBackWhen } from "../src/checkBack.js";

test("a check-back reads as a short day and an hour", () => {
  const now = new Date(2026, 10, 6, 15, 0);                       // Fri Nov 6, 3 PM local
  assert.equal(checkBackWhen("2026-11-10 09:00:00", now), "Tue 9 AM");
  assert.equal(checkBackWhen("2026-11-07 14:30:00", now), "Sat 2:30 PM");
  assert.equal(checkBackLine("2026-11-10 09:00:00", now), "Checks back Tue 9 AM");
  assert.equal(checkBackWhen("2026-11-20 09:00:00", now), "Nov 20 9 AM");   // a week or more away names its date
  assert.equal(checkBackLine("", now), ""); assert.equal(checkBackLine("not a date", now), "");
});

test("only an open task with one waiting has a chip", () => {
  assert.deepEqual(checkBackOf({ CheckBackAt: "2026-11-10 09:00:00", CheckBackWhat: "the refund cleared", Status: "open" }),
    { at: "2026-11-10 09:00:00", what: "the refund cleared" });
  assert.equal(checkBackOf({ CheckBackAt: "", Status: "open" }), null);
  assert.equal(checkBackOf({ CheckBackAt: "2026-11-10 09:00:00", Status: "done" }), null);
  assert.equal(checkBackOf(null), null);
});

// WHOLE BESIDE THE STATUS (walk 19): in a tight task head the chip's box shrank and "Checks back Thu 7 A" ran under the "waiting for Dana's
// input" pill, its × and clock drawn through it. Drawn by the real component (server-rendered, MUI's own styles inline): its box never shrinks
test("the check-back chip's box keeps its width in a tight head, so it never runs under the status beside it", async () => {
  const { build } = await import("esbuild"), resolveDir = new URL("..", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");
  const out = await build({ stdin: { resolveDir, loader: "jsx", contents: `
    import React from "react"; import { renderToStaticMarkup } from "react-dom/server.browser"; import CheckBackChip from "./src/CheckBackChip.jsx";
    export const html = (t) => renderToStaticMarkup(<CheckBackChip task={t} />);` }, bundle: true, write: false, format: "esm", jsx: "automatic",
    platform: "node", logLevel: "silent", define: { "process.env.NODE_ENV": '"production"' },
    plugins: [{ name: "axios", setup(b) { b.onResolve({ filter: /^axios$/ }, () => ({ path: "axios", namespace: "stub" }));
      b.onLoad({ filter: /.*/, namespace: "stub" }, () => ({ loader: "js", contents: "const a = { delete: async () => ({}), interceptors: { request: { use() {} }, response: { use() {} } } }; export default { ...a, create: () => a };" })); } }],
    loader: { ".css": "empty", ".png": "empty", ".svg": "empty", ".woff2": "empty", ".json": "json" } });
  const { writeFileSync } = await import("node:fs"), { join } = await import("node:path"), { pathToFileURL } = await import("node:url");
  const f = join((await import("../browser/tempdirs.mjs")).ownTemp("tq-cb-"), "chip.mjs"); writeFileSync(f, out.outputFiles[0].text);
  const { html } = await import(pathToFileURL(f).href);
  const at = new Date(Date.now() + 2 * 864e5), day = `${at.getFullYear()}-${String(at.getMonth() + 1).padStart(2, "0")}-${String(at.getDate()).padStart(2, "0")}`;
  const got = html({ TaskId: 2, Status: "waiting", CheckBackAt: `${day} 07:00:00`, CheckBackWhat: "the corrected quote" });
  const cls = /<span class="([^"]+)" data-tq-check-back=/.exec(got)?.[1]?.split(" ").find((c) => c.startsWith("css-"));
  assert.ok(cls, got.slice(0, 300));
  const rule = new RegExp(`\.${cls}\{[^}]*\}`).exec(got)?.[0] || "";
  assert.match(rule, /flex-shrink:0/, rule);
});
