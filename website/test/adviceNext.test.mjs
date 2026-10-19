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

test("the advised verb is the one filled button, whatever the row would have filled - and with no advice, none is", () => {
  const list = [v("approve", "decide", { tone: "p", label: "Send" }), v("continue", "agent", { label: "Continue" }), v("done", "more", { label: "Mark done" }), v("next", "next")];
  assert.deepEqual(filled(rowOf({ ref: "", list })), []);
  assert.deepEqual(filled(rowOf({ ref: "", list }, { verb: "approve", label: "Send" })), ["approve"]);
  assert.deepEqual(filled(rowOf({ ref: "", list }, { verb: "continue", label: "Continue" })), ["continue"]);
  assert.deepEqual(filled(rowOf({ ref: "", list }, { verb: "close", label: "Mark done" })), ["done"]);   // Mark done is the advisor's close
});

test("a pick waiting behind More comes onto the bar, filled; nothing advised leaves the row as it was", () => {
  const list = [v("continue", "agent", { lead: true, label: "Continue" }), v("rerun", "more", { label: "Run it again" }), v("next", "next")];
  const r = rowOf({ ref: "", list }, { verb: "rerun", label: "Run it again" });
  assert.deepEqual(filled(r), ["rerun"]); assert.ok(!r.more.some((x) => x.id === "rerun"));
  assert.deepEqual(filled(rowOf({ ref: "", list }, null)), filled(rowOf({ ref: "", list })));
  assert.deepEqual(filled(rowOf({ ref: "", list }, { verb: "chase", label: "Chase them" })), []);   // not on the row: nothing dark (AdvisorNext adds it)
});

test("the advisor's Reply is the task's Write reply: matched by the verb's id, so no second Reply is drawn", () => {
  const list = [v("reply", "decide", { tone: "p", label: "Write reply" }), v("continue", "agent", { label: "Continue" }), v("done", "more", { label: "Mark done" })];
  assert.equal(advisedIn(list, { verb: "reply", label: "Reply" })?.id, "reply");
  assert.deepEqual(filled(rowOf({ ref: "", list }, { verb: "continue", label: "Continue" })), ["continue"]);
});

test("a greyed verb is never the advised one", () => {
  const list = [v("continue", "agent", { lead: true, label: "Continue" }), v("done", "more", { label: "Mark done", disabled: true }), v("next", "next")];
  assert.deepEqual(filled(rowOf({ ref: "", list }, { verb: "close", label: "Mark done" })), []);
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
  assert.match(page, /<Typography className="tq-news"[^>]*>Open again: \{news\.line\}/);
  assert.match(src, /className=\{shownAdvice \? "tq-asst-col advising" : "tq-asst-col"\}/);
  assert.match(css, /\.tq-asst-col\.advising \.tq-news \{ display: none; \}/);
});

test("the strip gives the suggestion, not the move's name: a lead-in that is the verb goes, any other sentence stays whole", () => {
  assert.equal(suggestion("Reply: Gail is directly asking your access decision for this group.", "Reply", "reply"), "Gail is directly asking your access decision for this group.");
  assert.equal(suggestion("Reply because Erin is directly asking for your okay.", "Reply", "reply"), "Erin is directly asking for your okay.");
  assert.equal(suggestion("Continue - the coding agent was cut off, not finished.", "Continue", "continue"), "The coding agent was cut off, not finished.");
  assert.equal(suggestion("Erin: the list is approved, send it.", "Reply", "reply"), "Erin: the list is approved, send it.");   // a name, not the verb
  assert.equal(suggestion("You usually merge these.", "Mark done", "close"), "You usually merge these.");
});

// ...and a move the row has no button for (Not ours, Take it myself, Chase) JOINS THE ROW, never a button beside the line (the owner,
// 2026-10-16: "the advisor should just highlight the button in the button row not add new ones? check this for all advisor lines")
test("the strip has no NEXT tag and no button of its own; a move the row lacks joins the row, and Why? opens the reasoning", () => {
  const strip = row.slice(row.indexOf("export function AdvisorNext"), row.indexOf("function Cluster"));
  assert.doesNotMatch(strip, /NEXT/);
  assert.doesNotMatch(strip, /<button type="button" className="tq-ab/, "the line draws no button - the row has them all");
  assert.match(strip, /useVerbs\("advice", lacks \? \[\{ id: `advice:\$\{advice\.verb\}`/);
  assert.match(strip, /const lacks = !!\(advice\?\.verb && advice\.line && onPropose\) && !advisedAny\(theirs, advice\);/);
  assert.match(strip, /suggestion\(advice\.line, advice\.label, advice\.verb\)/);
  assert.match(strip, /className="tq-next-why"[^>]*>Why\?<\/button>/);
  assert.match(strip, /api\.get\("\/api\/advice\/notes", \{ params: \{ key: advice\.key/);
  assert.match(strip, /<Popover open=\{!!at\}/);
});

test("the clock menu offers the Advisor's notes for the item on the table", () => {
  assert.match(src, /Advisor's notes/);
  assert.match(src, /api\.get\("\/api\/advice\/notes", \{ params: \{ key/);
});

test("a move the row cannot make is no advice: a greyed or missing button draws no strip", () => {
  const strip = row.slice(row.indexOf("export function AdvisorNext"), row.indexOf("function Cluster"));
  assert.match(strip, /const onRow = advisedIn\(verbs\.list, advice\);\s*if \(!onRow\) return null;/, "a greyed button: no line");
  assert.match(strip, /!advisedAny\(theirs, advice\)/, "a greyed button is not lacking: nothing joins the row for it");
  const list = [v("stop_agent", "agent", { label: "Stop and save", disabled: true }), v("next", "next")];
  assert.equal(advisedIn(list, { verb: "stop_agent", label: "Stop and save" }), null, "greyed: nothing to fill, so nothing to say");
});

test("advised Send fills only a button that sends, and the card's other words for an act still match", () => {
  const list = [v("approve", "decide", { label: "Refresh the draft" }), v("remind", "decide", { label: "Remind me" }), v("next", "next")];
  assert.equal(advisedIn(list, { verb: "approve", label: "Send" }), null, "Refresh the draft is not Send");
  assert.equal(advisedIn([v("approve", "decide", { label: "Send" })], { verb: "approve", label: "Send" })?.label, "Send");
  assert.equal(advisedIn(list, { verb: "defer", label: "Remind me later" })?.label, "Remind me", "defer is the row's Remind me");
});
