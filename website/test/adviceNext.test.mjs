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

// THE ADVICE ONLY TINTS (2026-10-19): a pick behind More is filled where it stands - the row's layout is the same with and without
// advice (moved onto the bar, it reshuffled the row seconds after the item opened); clustersOf keeps the filled one in view
test("a pick waiting behind More is filled where it stands; nothing advised leaves the row as it was", () => {
  const list = [v("continue", "agent", { lead: true, label: "Continue" }), v("rerun", "more", { label: "Run it again" }), v("next", "next")];
  const r = rowOf({ ref: "", list }, { verb: "rerun", label: "Run it again" }), plain = rowOf({ ref: "", list });
  assert.deepEqual(r.more.filter((x) => x.tone === "p").map((x) => x.id), ["rerun"]);
  const ids = (x) => [...x.decide, ...x.agent, ...x.more].map((y) => y.id);
  assert.deepEqual(ids(r), ids(plain), "the same buttons in the same places");
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

test("the Advisor lights the row and the box is plain: no ghost text, no pill, no line over the row", () => {
  assert.match(src, /<AdvisorNext advice=\{shownAdvice\} onPropose=\{pressAdvice\} onErr=\{setErr\} \/>/);
  assert.match(src, /<ActionRow [^>]*advised=\{stripPick \|\| setupLit\}/);
  assert.doesNotMatch(src, /ghostText|tq-pill|tq-advised/);
  assert.doesNotMatch(css, /\.tq-pill|tq-advised/);
  // ...and NO decision draws a sentence (the owner, 2026-10-23 "the obvious move is silent", then 2026-10-26 "remove the advisor"): a
  // decided item leaves only an empty mark the walks read; its button is lit, a warning is in the task (advice.taskNote)
  assert.match(row, /return advice\?\.verb \? <div hidden data-tq-advice="" data-tq-silent="" data-tq-advice-verb=\{advice\.verb\} \/> : null;/);
  assert.doesNotMatch(row.slice(row.indexOf("export function AdvisorNext"), row.indexOf("function Cluster")), /tq-next/);
});

test("the task's own Open again line always stands - no strip says what to do in its place (2026-10-26)", () => {
  const page = fs.readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");
  assert.match(page, /<Typography className="tq-news"[^>]*>Open again: \{news\.line\}/);
  assert.match(src, /<div className="tq-asst-col" style=/);
  assert.doesNotMatch(css, /\.advising/);
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
test("the Advisor draws no button of its own; a move the row lacks joins the row, and a warning's Why? opens the reasoning", () => {
  const strip = row.slice(row.indexOf("export function AdvisorNext"), row.indexOf("function Cluster"));
  assert.doesNotMatch(strip, /NEXT/);
  assert.doesNotMatch(strip, /<button type="button" className="tq-ab/, "the line draws no button - the row has them all");
  assert.match(strip, /useVerbs\("advice", lacks \? \[\{ id: `advice:\$\{advice\.verb\}`/);
  assert.match(strip, /const lacks = !!\(advice\?\.verb && advice\.verb !== "next" && onPropose\) && !advisedAny\(theirs, advice\);/);
  // ...a refused press is said on the chat's error line (onErr) - there is no strip to say it on
  assert.match(strip, /catch \(err\) \{ onErr\?\.\(proposeFailed\(err\)\); \}/);
  // ...and every line in the task's Advisor section keeps its Why? (AdvisorNote, the owner 2026-10-26)
  const note = fs.readFileSync(new URL("../src/AdvisorNote.jsx", import.meta.url), "utf8");
  assert.match(note, /<button type="button" className="tq-next-why" aria-haspopup="dialog"[\s\S]{0,120}>Why\?<\/button>/);
  // ...reading the decision the row lit (its `rests`), never the older rows (the Advisor audit's judge, 2026-10-26)
  assert.match(note, /const a = note\.advice \|\| \{\}, rests = a\.rests \|\| \[\];/);
  assert.doesNotMatch(note, /\/api\/advice\/notes/);
  assert.match(note, /<Popover open=\{!!at\}/);
});

test("the clock menu offers the Advisor's notes for the item on the table", () => {
  assert.match(src, /Advisor's notes/);
  // ...the same decision the task shows, through the same filter, or nothing (the Advisor audit's judge, 2026-10-26)
  assert.match(src, /api\.get\("\/api\/advice", \{ params: \{ key: keyOnTable \} \}\)/);
  assert.match(src, /const note = d && taskNote\(d\), rests = \(note && d\.rests\) \|\| \[\];/);
});

// ...and a greyed one says why it is off rather than drawing nothing: the strip went blank with nothing lit when the draft was cleared
// (the advisor matrix, 2026-10-19)
test("a move the row cannot make lights nothing: a greyed button says why it is off on its own title, and nothing joins the row for it", () => {
  const strip = row.slice(row.indexOf("export function AdvisorNext"), row.indexOf("function Cluster"));
  assert.match(row, /title=\{\(v\.disabled && v\.why\) \|\| v\.title \|\| undefined\}/, "a greyed button: why it is off");
  assert.match(strip, /!advisedAny\(theirs, advice\)/, "a greyed button is not lacking: nothing joins the row for it");
  const list = [v("stop_agent", "agent", { label: "Stop and save", disabled: true }), v("next", "next")];
  assert.equal(advisedIn(list, { verb: "stop_agent", label: "Stop and save" }), null, "greyed: nothing to fill");
});

test("advised Send fills only a button that sends, and the card's other words for an act still match", () => {
  const list = [v("approve", "decide", { label: "Refresh the draft" }), v("remind", "decide", { label: "Remind me" }), v("next", "next")];
  assert.equal(advisedIn(list, { verb: "approve", label: "Send" }), null, "Refresh the draft is not Send");
  assert.equal(advisedIn([v("approve", "decide", { label: "Send" })], { verb: "approve", label: "Send" })?.label, "Send");
  assert.equal(advisedIn(list, { verb: "defer", label: "Remind me later" })?.label, "Remind me", "defer is the row's Remind me");
});

// THE LIT BUTTON IS THE ONE ON THE BAR (2026-10-19): a draft registers its own Mark done (`<rid>:done`, a card verb) beside the task's;
// found first, it was lit on the card a screen down while the bar's Mark done stood dark under "mark it done to move on"
test("an act the bar and the card both carry is lit on the bar", () => {
  const list = [v("7:approve", "decide", { card: true, tone: "p", label: "Send" }), v("7:done", "decide", { card: true, closes: true, label: "Mark done" }),
    v("done", "more", { label: "Mark done" }), v("next", "next")];
  assert.equal(advisedIn(list, { verb: "close", label: "Mark done" })?.id, "done");
  const r = rowOf({ ref: "", list }, { verb: "close", label: "Mark done" });
  assert.deepEqual(filled(r), ["done"]); assert.equal(r.lit, "");
  assert.equal(advisedIn([v("7:redraft", "decide", { card: true, label: "Redraft" })], { verb: "redraft", label: "Redraft" })?.id, "7:redraft", "no bar button: the card's");
  // ...and a chat draft's main move IS its Mark done (copy and close): that one, in the bar's first slot, not the task's it stands for
  const chat = [v("7:approve", "decide", { card: true, tone: "p", closes: true, label: "Mark done", verb: "close" }), v("done", "more", { label: "Mark done" })];
  assert.equal(advisedIn(chat, { verb: "close", label: "Mark done" })?.id, "7:approve");
});
