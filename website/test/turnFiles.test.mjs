// THE FILES ONE TURN MADE ARE ONE ARTIFACT (the owner, 2026-11-24: "it put in 9 files as cards? it should combine them" ... "like the bulk
// action card, same idea"): a turn that wrote nine facility workbooks drew nine stacked frames. Now: one frame, its count as the label, the bulk
// card's rows (Artifact Items) one per file, and one preview - of the first, then of the row he picks. A single file is drawn as it was.
import test from "node:test";
import assert from "node:assert/strict";
import { fileKind, filesLabel, sizeWords } from "../src/taskOutputs.js";

const wb = (i) => ({ id: `output:Site ${i}.xlsx`, path: `Site ${i}.xlsx`, name: `Site ${i}.xlsx`, kind: "output", preview: "sheet", size: 20480 + i,
  url: `/api/task-outputs/7/Site%20${i}.xlsx`, after: "comment-4" });
const NINE = Array.from({ length: 9 }, (_, i) => wb(i + 1));

test("a group's label is a plain count by kind, from one wording function", () => {
  assert.equal(filesLabel(NINE), "9 workbooks");
  assert.equal(filesLabel([wb(1), { name: "summary.pdf" }, { name: "chart.png" }]), "3 files");
  assert.equal(filesLabel([{ name: "a.pdf" }, { name: "b.pdf" }]), "2 PDFs");
  assert.equal(fileKind({ name: "notes.zip" }), "file");
  assert.deepEqual([sizeWords(512), sizeWords(20480), sizeWords(3 * 1048576), sizeWords(undefined)], ["512 B", "20 KB", "3.0 MB", ""]);
});

// ...the real components, server-rendered, no network
const AXIOS = { name: "axios", setup(b) { b.onResolve({ filter: /^axios$/ }, () => ({ path: "axios", namespace: "stub" }));
  b.onLoad({ filter: /.*/, namespace: "stub" }, () => ({ loader: "js", contents: "const a = { get: async () => ({ data: {} }), post: async () => ({ data: {} }), head: async () => ({}), interceptors: { request: { use() {} }, response: { use() {} } }, defaults: { headers: { common: {} } } }; export default { ...a, create: () => a };" })); } };
const bundle = async (contents, plugins = [AXIOS]) => {
  const hold = setInterval(() => {}, 1000);
  try {
    const { build } = await import("esbuild");
    const out = await build({ stdin: { resolveDir: new URL("..", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"), loader: "jsx", contents },
      bundle: true, write: false, format: "esm", jsx: "automatic", platform: "node", logLevel: "silent", plugins, define: { "process.env.NODE_ENV": '"production"' },
      loader: { ".css": "empty", ".png": "empty", ".svg": "empty", ".jpg": "empty", ".woff2": "empty", ".json": "json" } });
    const { writeFileSync } = await import("node:fs"), { join } = await import("node:path"), { pathToFileURL } = await import("node:url");
    const f = join((await import("../browser/tempdirs.mjs")).ownTemp("tq-files-"), "page.mjs"); writeFileSync(f, out.outputFiles[0].text);
    return import(pathToFileURL(f).href);
  } finally { clearInterval(hold); }
};
let P_; const P = { then: (a, b) => (P_ ||= bundle(`import React from "react"; import { renderToStaticMarkup } from "react-dom/server.browser";
  import TurnFiles from "./src/TurnFiles.jsx"; export const draw = (files) => renderToStaticMarkup(<TurnFiles files={files} />);`)).then(a, b) };
const count = (html, re) => (html.match(re) || []).length;

test("nine files one turn made are one artifact: its label, nine rows, one preview", async () => {
  globalThis.localStorage ||= { getItem: () => null };
  const html = (await P).draw(NINE);
  assert.equal(count(html, /class="[^"]*tq-turn-frame/g), 1, "one frame, not nine");
  assert.match(html, /data-tq-file-group="9"/);
  assert.match(html, /data-tq-artifact-label="">9 workbooks</);
  assert.equal(count(html, /data-tq-bulk-row=/g), 9, "the bulk card's rows, one per file");
  assert.equal(count(html, /data-tq-download=""/g), 9, "a Download on each row");
  assert.match(html, /data-tq-download-all=""/);
  assert.equal(count(html, /data-tq-picked=""/g), 1);
  assert.match(html, /data-tq-turn-file="Site 1.xlsx"/, "the first is shown until he picks another");
  assert.match(html, />workbook · 20 KB</);
});

test("one file is drawn as before: its own frame, its name row, its preview, no list", async () => {
  const html = (await P).draw([wb(1)]);
  assert.equal(count(html, /class="[^"]*tq-turn-frame/g), 1);
  assert.match(html, /data-tq-turn-file="Site 1.xlsx"/);
  assert.match(html, /class="tq-published-name"/);
  assert.doesNotMatch(html, /data-tq-file-group|data-tq-bulk-row|data-tq-download-all/);
});

// ...picking a row: TurnFiles drawn through a hook stub, its own children expanded, the preview read off the tree
test("picking a row shows that file in the one preview", async () => {
  let slots = [], at = 0, draw;
  globalThis.__R = { useState: (v) => { const i = at++; if (!(i in slots)) slots[i] = v; return [slots[i], (n) => { slots[i] = n; draw(); }]; },
    jsx: (type, props) => ({ type, props: props || {} }), Fragment: "Fragment" };
  globalThis.__R.jsxs = globalThis.__R.jsx;
  const stub = { "react": "export const { useState } = globalThis.__R; export default globalThis.__R;", "react/jsx-runtime": "export const { jsx, jsxs, Fragment } = globalThis.__R;",
    "@mui/material": "export const Box = 'Box', Button = 'Button';", "./fileSave.js": "export const attUrl = (f) => f.url, useSave = () => ['', () => {}, ''];",
    "./PublishedPages.jsx": "export const CopyFile = 'CopyFile', FileDialog = 'FileDialog', Preview = 'Preview', isText = () => false;",
    "./Artifact.jsx": "export default 'Artifact'; export const Items = 'Items';", "./theme.jsx": "export const INK = '';" };
  const { default: TurnFiles } = await bundle(`export { default } from "./src/TurnFiles.jsx";`, [{ name: "stubs", setup(b) {
    b.onResolve({ filter: /.*/ }, (a) => (a.path in stub ? { path: a.path, namespace: "stub" } : undefined));
    b.onLoad({ filter: /.*/, namespace: "stub" }, (a) => ({ contents: stub[a.path], loader: "js" })); } }]);
  let tree;
  const expand = (n) => Array.isArray(n) ? n.map(expand) : n && typeof n === "object" && typeof n.type === "function" ? expand(n.type(n.props))
    : n && typeof n === "object" ? { ...n, props: { ...n.props, children: expand(n.props.children) } } : n;
  draw = () => { at = 0; tree = expand(TurnFiles({ files: NINE })); };
  const find = (n, ok, out = []) => { if (Array.isArray(n)) n.forEach((x) => find(x, ok, out)); else if (n && typeof n === "object") { if (ok(n)) out.push(n); find(n.props.children, ok, out); } return out; };
  draw();
  const items = () => find(tree, (n) => n.type === "Items")[0].props.items, shown = () => find(tree, (n) => n.type === "Preview").map((n) => n.props.page.name);
  assert.equal(find(tree, (n) => n.type === "Artifact").length, 1);
  assert.equal(items().length, 9);
  assert.deepEqual(shown(), ["Site 1.xlsx"]);
  items()[3].onPick();
  assert.deepEqual(shown(), ["Site 4.xlsx"], "one preview, now the one he picked");
  assert.deepEqual(items().map((x) => !!x.picked), NINE.map((_, i) => i === 3));
});
