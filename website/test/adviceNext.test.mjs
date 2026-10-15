// The Advisor's next step (2026-10-13): written at the foot of the canvas over the action row, the filled button on that row is the
// one it advises, and the prompt box is the owner's own again - no ghost text, no pill. rowOf is the real function; the wiring is read
// from the source, the way the composer's other tests do.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { advisedIn, rowOf } from "../src/actionRow.js";
import { suggestion } from "../src/advice.js";

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

test("the advisor's Reply is the task's Write reply: matched by the verb's id, so no second Reply is drawn", () => {
  const list = [v("reply", "decide", { tone: "p", label: "Write reply" }), v("continue", "agent", { label: "Continue session" }), v("done", "more", { label: "Mark done" })];
  assert.equal(advisedIn(list, { verb: "reply", label: "Reply" })?.id, "reply");
  assert.deepEqual(filled(rowOf({ ref: "", list }, { verb: "continue", label: "Continue session" })), ["continue"]);
});

test("a greyed verb is never the advised one", () => {
  const list = [v("continue", "agent", { lead: true, label: "Continue session" }), v("done", "more", { label: "Mark done", disabled: true }), v("next", "next")];
  assert.deepEqual(filled(rowOf({ ref: "", list }, { verb: "close", label: "Mark done" })), ["continue"]);
});

test("the next step sits over the row and the box is plain: no ghost text, no pill", () => {
  assert.match(src, /<AdvisorNext advice=\{shownAdvice\}/);
  assert.match(src, /<ActionRow [^>]*advised=\{shownAdvice\}/);
  assert.doesNotMatch(src, /ghostText|tq-pill|tq-advised/);
  assert.doesNotMatch(css, /\.tq-pill|tq-advised/);
  assert.match(row, /if \(!advice\?\.verb \|\| !advice\.line\) return null;/);                // nothing to say draws nothing
  assert.match(css, /\.tq-next \{/);
});

test("while the NEXT strip stands, the task's own Open again line is hidden - only on the canvas", () => {
  const page = fs.readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");
  assert.match(page, /<Typography className="tq-news"[^>]*>\{tx\("Open again:"\)\} \{news\.line\}/);
  assert.match(src, /className=\{shownAdvice \? "tq-asst-col advising" : "tq-asst-col"\}/);
  assert.match(css, /\.tq-asst-col\.advising \.tq-news \{ display: none; \}/);
});

test("the strip gives the suggestion, not the move's name: a lead-in that is the verb goes, any other sentence stays whole", () => {
  assert.equal(suggestion("Reply: Gail is directly asking your access decision for this group.", "Reply", "reply"), "Gail is directly asking your access decision for this group.");
  assert.equal(suggestion("Reply because Erin is directly asking for your okay.", "Reply", "reply"), "Erin is directly asking for your okay.");
  assert.equal(suggestion("Continue session - coder was cut off, not finished.", "Continue session", "continue"), "Coder was cut off, not finished.");
  assert.equal(suggestion("Erin: the list is approved, send it.", "Reply", "reply"), "Erin: the list is approved, send it.");   // a name, not the verb
  assert.equal(suggestion("You usually merge these.", "Mark done", "close"), "You usually merge these.");
});

test("the strip has no NEXT tag and no button of its own - the buttons are the row's - and Why? opens the Advisor's reasoning", () => {
  const strip = row.slice(row.indexOf("export function AdvisorNext"), row.indexOf("function Cluster"));
  assert.doesNotMatch(strip, /NEXT|className="tq-ab/);
  assert.match(strip, /suggestion\(advice\.line, advice\.label, advice\.verb\)/);
  assert.match(strip, /className="tq-next-why"[^>]*>\{tx\("Why\?"\)\}<\/button>/);
  assert.match(strip, /api\.get\("\/api\/advice\/notes", \{ params: \{ key: advice\.key/);
  assert.match(strip, /<Popover open=\{!!at\}/);
});

test("the clock menu offers the Advisor's notes for the item on the table", () => {
  assert.match(src, /Advisor's notes/);
  assert.match(src, /api\.get\("\/api\/advice\/notes", \{ params: \{ key/);
});

test("a move the row cannot make is no advice: a greyed or missing button draws no strip", () => {
  const strip = row.slice(row.indexOf("export function AdvisorNext"), row.indexOf("function Cluster"));
  assert.match(strip, /if \(!onRow\) return null;/);
  const list = [v("stop_agent", "agent", { label: "Save and end session", disabled: true }), v("next", "next")];
  assert.equal(advisedIn(list, { verb: "stop_agent", label: "Save and end session" }), null, "greyed: nothing to fill, so nothing to say");
});
