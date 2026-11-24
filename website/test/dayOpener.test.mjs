// THE DAY'S OPEN TASKS BY NAME (the owner, 2026-11-24: the "What's open" card read "Tasks · you · 1" and named nothing): under the Tasks row each
// of its first three rows as the rail draws it - its title, then where it stands (the row's own state word) - a link that opens it, the rest
// "+N more". Server-rendered through the real card; invented people only.
import test from "node:test";
import assert from "node:assert/strict";

const AXIOS = { name: "axios", setup(b) { b.onResolve({ filter: /^axios$/ }, () => ({ path: "axios", namespace: "stub" }));
  b.onLoad({ filter: /.*/, namespace: "stub" }, () => ({ loader: "js", contents: "const a = { get: async () => ({ data: {} }), post: async () => ({ data: {} }), interceptors: { request: { use() {} }, response: { use() {} } }, defaults: { headers: { common: {} } } }; export default { ...a, create: () => a };" })); } };
const page = async () => {
  if (typeof navigator === "undefined") globalThis.navigator = { userAgent: "node", platform: "", language: "en-US" };
  const hold = setInterval(() => {}, 1000);
  try {
    const { build } = await import("esbuild");
    const out = await build({ stdin: { resolveDir: new URL("..", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"), loader: "jsx", contents: `
      import React from "react"; import { renderToStaticMarkup } from "react-dom/server.browser";
      import { DayOpener } from "./src/assistantCards.jsx"; import { summarize } from "./src/walkSummary.js";
      export const draw = (items) => renderToStaticMarkup(<DayOpener groups={summarize(items).groups} />);` },
      bundle: true, write: false, format: "esm", jsx: "automatic", platform: "node", logLevel: "silent", plugins: [AXIOS],
      define: { "process.env.NODE_ENV": '"production"', "import.meta.env.BASE_URL": '"/"' },
      loader: { ".css": "empty", ".png": "empty", ".svg": "empty", ".jpg": "empty", ".woff2": "empty", ".json": "json" } });
    const { writeFileSync } = await import("node:fs"), { join } = await import("node:path"), { pathToFileURL } = await import("node:url");
    const f = join((await import("../browser/tempdirs.mjs")).ownTemp("tq-day-"), "page.mjs"); writeFileSync(f, out.outputFiles[0].text);
    return import(pathToFileURL(f).href);
  } finally { clearInterval(hold); }
};

const task = (n, title, state) => ({ key: `processing:t${n}`, kind: "todo", lane: "yours", tid: n, title, who: "You", shows: { who: "You", state } });

test("the open tasks are named under the Tasks row - title and where it stands, three at most, then +N more", async () => {
  const m = await page();
  const one = m.draw([task(1, "Send Erin the August statement", "waiting for your input")]);
  assert.match(one, /data-tq-day-named=""><button[^>]*class="tq-day-task"[^>]*><span class="t">Send Erin the August statement<\/span><span class="st"> - waiting for your input<\/span>/);
  assert.doesNotMatch(one, /\+\d+ more/);
  const five = m.draw([1, 2, 3, 4, 5].map((n) => task(n, `Task number ${n}`, "waiting for their input")));
  assert.deepEqual([...five.matchAll(/<span class="t">([^<]+)<\/span>/g)].map((x) => x[1]), ["Task number 1", "Task number 2", "Task number 3"]);
  assert.match(five, /class="tq-day-task more"[^>]*>\+2 more</);
});
