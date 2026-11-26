// A SET RAISED IN ONE CALL IS ONE CARD WITH A TAB EACH (the owner, 2026-11-26: the same post for three networks - never two unrelated cards):
// one frame, its tabs and "1 of 3" in its head, each tab the one review card it is, drawn by the same component; a press on the shown one
// settles it and NEVER changes the tab shown. Invented posts.
import test from "node:test";
import assert from "node:assert/strict";
import { lineAt, lineStep, shownTab } from "../src/cardLine.js";

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
  // ...(its own card, by its own key: the page keeps the tab shown per card - cardLine.shownTab)
  const { line } = await P, tabs = tabsOf([0, 1], 2).map((t, i) => ({ ...t, key: `7${t.key}`, ...(i === 1 ? { no: true } : {}) }));
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

// The owner, 2026-11-26: he approved one tab of two, the card slid on to the other, and what he had just approved "disappeared" - "cards or
// anything generated on chat never go away". And three posts in one card, with no way he saw to reach the third but Dismiss on the first two
test("a press never changes the card shown: the pressed tab stays, saying what it did, and only he moves on", () => {
  assert.equal(lineAt(tabsOf()), 0, "it opens on the card in front");
  const shown = tabsOf()[0].key;
  assert.equal(lineAt(tabsOf([0], 1), shown), 0, "tab 1 approved: still tab 1, though the next is in front now");
  assert.equal(lineAt(tabsOf([0, 1], 2), shown), 0);
  assert.equal(lineAt(tabsOf([0, 1, 2], -1), shown), 0, "all settled: still the one he is on");
  assert.equal(lineAt(tabsOf([2], 0), "43"), 2, "he opened Reddit and dismissed it: it stays, crossed");
  assert.equal(lineAt(tabsOf([0, 1], 2)), 2, "a card first drawn after presses opens on the one that waits");
  assert.equal(lineAt(tabsOf([0, 1, 2], -1)), 2, "none waits: the last");
});

test("the arrows beside the count step to the card before and after, round the ends", () => {
  const tabs = tabsOf();
  assert.deepEqual([lineStep(tabs, 0, 1), lineStep(tabs, 1, 1), lineStep(tabs, 2, 1)], [1, 2, 0]);
  assert.deepEqual([lineStep(tabs, 0, -1), lineStep(tabs, 2, -1)], [2, 1]);
  assert.equal(lineStep(tabsOf([0, 1], 2), 0, 1), 1, "a settled card is a step like any other: he can look back at what he pressed");
});

test("the tab he is on is kept for the card as long as the page is open, through a redraw of the card elsewhere in the chat", () => {
  const tabs = tabsOf().map((t) => ({ ...t, key: `k${t.key}` }));
  assert.equal(shownTab(tabs), "k41", "first drawn: the card in front");
  assert.equal(shownTab(tabs, "k43"), "k43", "he steps to Reddit");
  assert.equal(shownTab(tabs.map((t, i) => ({ ...t, done: i === 2, front: i === 0 }))), "k43", "drawn anew after his press: still Reddit");
});

test("the card draws an arrow each side of the count, each a button with its name", async () => {
  const { line } = await P, html = line(tabsOf(), NETS.map(post));
  assert.deepEqual([...html.matchAll(/<button[^>]*aria-label="([^"]*)"[^>]*data-tq-line-step="(-?1)"/g)].map((m) => [m[1], m[2]]), [["Previous card", "-1"], ["Next card", "1"]]);
  assert.ok(html.indexOf('data-tq-line-step="-1"') < html.indexOf("data-tq-card-queue") && html.indexOf("data-tq-card-queue") < html.indexOf('data-tq-line-step="1"'));
  assert.equal((html.match(/role="tablist"[^>]*>(.*?)data-tq-line-step/s)?.[1].match(/role="tab"/g) || []).length, 3, "the tab names stay, each a press");
});

// The owner, 2026-11-26: "did you move the tabs switcher on to the actual card as it looks really weird now" - the tab names and the count are
// the card's own head, inside its one frame, never a row floating over it in the chat
test("the tabs and the count are in the card's own frame, and each item lies in that one frame", async () => {
  const { line } = await P, html = line(tabsOf().map((t) => ({ ...t, key: `9${t.key}` })), NETS.map(post));
  assert.match(html, /^(<style[^>]*>.*?<\/style>)*<div class="[^"]*tq-turn-frame[^"]*"[^>]*data-tq-card-line="3"/s, "the card is the one frame");
  const head = html.indexOf("data-tq-line-head"), frame = html.indexOf("tq-turn-frame");
  assert.ok(frame >= 0 && frame < head && head < html.indexOf('role="tabpanel"'), "its head, with the tabs, comes inside the frame and over the items");
  assert.ok(html.indexOf('role="tablist"') > head && html.indexOf("data-tq-card-queue") > head);
});
