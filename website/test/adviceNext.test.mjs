// The Advisor's next step (2026-10-13): written at the foot of the canvas over the action row, the filled button on that row is the
// one it advises, and the prompt box is the owner's own again - no ghost text, no pill. rowOf is the real function; the wiring is read
// from the source, the way the composer's other tests do.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { rowOf } from "../src/actionRow.js";

const src = fs.readFileSync(new URL("../src/AssistantView.jsx", import.meta.url), "utf8");
const row = fs.readFileSync(new URL("../src/ActionRow.jsx", import.meta.url), "utf8");
const css = fs.readFileSync(new URL("../src/assistantView.css", import.meta.url), "utf8");
const v = (id, group, extra = {}) => ({ id, group, tone: "s", label: id, title: "", disabled: false, why: "", promote: true, lead: false, ...extra });
const filled = (r) => [...r.decide, ...r.agent, r.next].filter((x) => x && x.tone === "p").map((x) => x.id);

test("the advised verb is the one filled button, whatever the row would have filled", () => {
  const list = [v("approve", "decide", { tone: "p", label: "Send & close" }), v("continue", "agent", { label: "Continue session" }), v("done", "more", { label: "Mark done" }), v("next", "next")];
  assert.deepEqual(filled(rowOf({ ref: "", list })), ["approve"]);
  assert.deepEqual(filled(rowOf({ ref: "", list }, { verb: "continue", label: "Continue session" })), ["continue"]);
  assert.deepEqual(filled(rowOf({ ref: "", list }, { verb: "close", label: "Mark done" })), ["done"]);   // Mark done is the advisor's close
});

test("a pick waiting behind More comes onto the bar, filled; nothing advised leaves the row as it was", () => {
  const list = [v("continue", "agent", { lead: true, label: "Continue session" }), v("rerun", "more", { label: "Run it again" }), v("next", "next")];
  const r = rowOf({ ref: "", list }, { verb: "rerun", label: "Run it again" });
  assert.deepEqual(filled(r), ["rerun"]); assert.ok(!r.more.some((x) => x.id === "rerun"));
  assert.deepEqual(filled(rowOf({ ref: "", list }, null)), filled(rowOf({ ref: "", list })));
  assert.deepEqual(filled(rowOf({ ref: "", list }, { verb: "chase", label: "Chase them" })), ["continue"]);   // not on the row: unchanged
});

test("a greyed verb is never the advised one", () => {
  const list = [v("continue", "agent", { lead: true, label: "Continue session" }), v("done", "more", { label: "Mark done", disabled: true }), v("next", "next")];
  assert.deepEqual(filled(rowOf({ ref: "", list }, { verb: "close", label: "Mark done" })), ["continue"]);
});

test("the next step sits over the row and the box is plain: no ghost text, no pill", () => {
  assert.match(src, /<AdvisorNext advice=\{advice\}/);
  assert.match(src, /<ActionRow [^>]*advised=\{advice\}/);
  assert.match(src, /runChip\(\{ verb: advice\.verb, label: advice\.label, revision: advice\.revision \}\)/);   // a pick the row lacks: same chip path
  assert.doesNotMatch(src, /ghostText|tq-pill|tq-advised/);
  assert.doesNotMatch(css, /\.tq-pill|tq-advised/);
  assert.match(row, /if \(!advice\?\.verb \|\| !advice\.line\) return null;/);                // nothing to say draws nothing
  assert.match(css, /\.tq-next \{/);
});

test("the clock menu offers the Advisor's notes for the item on the table", () => {
  assert.match(src, /Advisor's notes/);
  assert.match(src, /api\.get\("\/api\/advice\/notes", \{ params: \{ key/);
});
