// A RUN OF CARDS IS ONE CARD WITH TABS (the owner, 2026-11-25: "we write 1 of 3 anyway so a little carousel thing on top that scrolls from one to
// the other is fine"): three posts waiting in line are one CardLine - a tab each, "1 of 3" - and each tab is the one review card it was, drawn by
// the same component; a press on the shown one settles it and the line slides on to the next that waits. Invented posts.
import test from "node:test";
import assert from "node:assert/strict";
import { lineAt, lineRuns, standsAlone } from "../src/cardLine.js";

const AXIOS = { name: "axios", setup(b) { b.onResolve({ filter: /^axios$/ }, () => ({ path: "axios", namespace: "stub" }));
  b.onLoad({ filter: /.*/, namespace: "stub" }, () => ({ loader: "js", contents: "const a = { get: async () => ({ data: {} }), post: async () => ({ data: {} }), put: async () => ({ data: {} }), interceptors: { request: { use() {} }, response: { use() {} } }, defaults: { headers: { common: {} } } }; export default { ...a, create: () => a };" })); } };
const page = async () => {
  const hold = setInterval(() => {}, 1000);
  try {
    const { build } = await import("esbuild");
    const out = await build({ stdin: { resolveDir: new URL("..", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"), loader: "jsx", contents: `
      import React from "react"; import { renderToStaticMarkup } from "react-dom/server.browser";
      import ReviewDecision from "./src/ReviewDecision.jsx"; import { CardLine } from "./src/Artifact.jsx";
      export const line = (tabs, rows) => renderToStaticMarkup(<CardLine tabs={tabs}>{rows.map((r) => <React.Fragment key={r.ReviewId}><ReviewDecision review={r} onChanged={() => {}} /></React.Fragment>)}</CardLine>);` },
      bundle: true, write: false, format: "esm", jsx: "automatic", platform: "node", logLevel: "silent", plugins: [AXIOS], define: { "process.env.NODE_ENV": '"production"' },
      loader: { ".css": "empty", ".png": "empty", ".svg": "empty", ".jpg": "empty", ".woff2": "empty", ".json": "json" } });
    const { writeFileSync } = await import("node:fs"), { join } = await import("node:path"), { pathToFileURL } = await import("node:url");
    const f = join((await import("../browser/tempdirs.mjs")).ownTemp("tq-line-"), "page.mjs"); writeFileSync(f, out.outputFiles[0].text);
    return import(pathToFileURL(f).href);
  } finally { clearInterval(hold); }
};
let P_; const P = { then: (a, b) => (P_ ||= page()).then(a, b) };

const NETS = [["x_post", "X"], ["linkedin_post", "LinkedIn"], ["reddit_post", "Reddit"]];
const post = ([type], i) => ({ ReviewId: 41 + i, TaskId: 7, Kind: "action", Status: "pending", CreatedAt: "2026-11-25 09:00:00",
  DraftText: JSON.stringify({ action: "run_tool", type, text: "We shipped the ledger export." }) });
const tabsOf = (done = [], front = 0) => NETS.map(([, name], i) => ({ key: String(41 + i), rids: [41 + i], name, done: done.includes(i), front: i === front }));

// The card gallery, 2026-11-25: after Don't send, the dropped email's tab read "✓ gail@..." - ticked like the one that went
test("a tab he said no to is crossed, never ticked like one that went", async () => {
  const { line } = await P, tabs = tabsOf([0, 1], 2).map((t, i) => (i === 1 ? { ...t, no: true } : t));
  const html = line(tabs, NETS.map(post));
  assert.deepEqual([...html.matchAll(/data-tq-line-tab="[^"]*"[^>]*>([^<]*)</g)].map((m) => m[1]), ["✓ X", "✗ LinkedIn", "Reddit"]);
  assert.deepEqual([...html.matchAll(/data-tq-tab-state="([^"]*)"/g)].map((m) => m[1]), ["done", "not-done", "waiting"]);
});

test("three cards waiting in line are one card: a tab each, the shown one marked, 1 of 3, each tab the one review card", async () => {
  const { line } = await P, html = line(tabsOf(), NETS.map(post));
  assert.equal((html.match(/role="tab"/g) || []).length, 3);
  assert.deepEqual([...html.matchAll(/data-tq-line-tab="[^"]*"[^>]*>([^<]*)</g)].map((m) => m[1]), ["X", "LinkedIn", "Reddit"]);
  assert.match(html, /aria-selected="true"[^>]*data-tq-line-tab="41"/);
  assert.match(html, /data-tq-card-queue="">1 of 3</);
  assert.equal((html.match(/data-tq-review-card=/g) || []).length, 3, "each tab draws the one card component");
  assert.equal((html.match(/data-tq-review-kind="post"/g) || []).length, 3);
  assert.equal((html.match(/<div[^>]*role="tabpanel"[^>]*inert=""[^>]*>/g) || []).length, 2, "only the shown card can be pressed or reached");
});

test("pressing the shown card's action slides on to the next that waits; a tab he opens stays until it is settled", () => {
  assert.equal(lineAt(tabsOf()), 0, "it opens on the card in front");
  assert.equal(lineAt(tabsOf([0], 1)), 1, "the front pressed: the next comes forward");
  assert.equal(lineAt(tabsOf([0, 1], 2)), 2);
  assert.equal(lineAt(tabsOf([0, 1, 2], -1), null, 1), 1, "all settled: it stays on the one he pressed last, saying what it did");
  assert.equal(lineAt(tabsOf(), { key: "43", done: false }), 2, "he opened Reddit to look");
  assert.equal(lineAt(tabsOf([2], 0), { key: "43", done: false }), 0, "Reddit pressed: on to the next that waits");
  assert.equal(lineAt(tabsOf([1], 0), { key: "42", done: false }), 2, "the next that waits after the one he pressed");
  assert.equal(lineAt(tabsOf([0], 1), { key: "41", done: true }), 0, "a settled one he opened stays open");
});

test("the one card stands at the row of the card in front, else the newest of its cards that has one; one with none is not drawn", () => {
  assert.equal(lineRuns([tabsOf([2], 0)], new Set(["41", "43"]))[0].at, "41", "a tab pressed behind the front never moves the card");
  const runs = [tabsOf([0], 1)];
  assert.equal(lineRuns(runs, new Set(["41", "42"]))[0].at, "42");
  assert.equal(lineRuns(runs, new Set(["41"]))[0].at, "41", "the next has no row yet: it stays where it stood");
  assert.deepEqual(lineRuns(runs, new Set()), []);
  assert.deepEqual(lineRuns([tabsOf().slice(0, 1)], new Set(["41"])), [], "a card alone is no carousel");
});

test("a card raised after his line while an older one still waits above it stands alone at its own row, never a tab of the card above", () => {
  const above = tabsOf().slice(0, 2), under = [{ key: "51", rids: [51], name: "Gail Moreno", done: false, front: true }];
  assert.deepEqual([...standsAlone([above, under])], ["51"]);
  assert.deepEqual(lineRuns([above, under], new Set(["41", "51"])).map((r) => r.tabs.map((t) => t.key)), [["41", "42"]], "the card above keeps its own tabs, and only those");
});
