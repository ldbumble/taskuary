// The Assistant is a router (the owner, 2026-10-19: "it should just surface the correct button"): a typed act comes back as the row's
// own button, lit - never a card to confirm, never a button of its own, and nothing runs until the owner presses it.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { lightOf, litAfter, litOn, litPick, litPull } from "../src/assistantLight.js";
import { rowOf } from "../src/actionRow.js";
import { label } from "../src/buttons.js";

const src = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");

test("\"mark this done\" fills the row's own Mark done and adds no button", () => {
  const lit = lightOf({ verb: "close", label: label("close"), key: "msg:4", tid: 7 });
  const v = (id, l, extra = {}) => ({ id, label: l, group: "decide", tone: "s", ...extra });
  const list = [v("reply", label("reply")), v("done", label("close"), { group: "more" }), v("remind", label("defer"), { group: "more" }), v("next", label("next"), { group: "next" })];
  const row = rowOf({ list, ref: "TQ-0007" }, litPick(lit, { key: "msg:4", tid: 7 }));
  const all = [...row.decide, ...row.agent, ...row.more];
  assert.deepEqual(all.filter((x) => x.tone === "p").map((x) => x.id), ["done"]);
  assert.equal(all.length, list.length - 1, "the same buttons - Next aside - and not one more");
});

test("the light lands on its item - by key, or by its task - and goes out when the table moves on", () => {
  const lit = lightOf({ verb: "defer", label: label("defer"), key: "task:12", tid: 12 });
  assert.equal(litPull(lit, { key: "msg:3", tid: 3 }), "task:12", "not on the table: brought up the rail's road");
  assert.equal(litPick(lit, { key: "msg:3", tid: 3 }), null);
  const up = { key: "msg:40", tid: 12 };                    // the task came up as its mail's row
  assert.ok(litOn(lit, up)); assert.equal(litPull(lit, up), null);
  const landed = litAfter(lit, up);
  assert.equal(landed.landed, true);
  assert.deepEqual(litPick(landed, up), { verb: "defer", label: label("defer"), line: "" });
  assert.equal(litAfter(landed, { key: "msg:41", tid: 13 }), null, "another item puts it out");
  assert.equal(litAfter(lit, { key: "msg:41", tid: 13 }), lit, "...but not before it has landed");
  assert.equal(lightOf(null), null);
  assert.equal(litPick(lightOf({ verb: "", key: "task:12", tid: 12 }), up), null, "brought up with nothing to light");
});

test("a typed turn draws no proposal card and runs nothing: it lights, opens a page, or fills New", () => {
  const view = src("AssistantView.jsx");
  const at = view.indexOf("const send = async"), body = view.slice(at, view.indexOf("const sendEmoji", at));
  assert.doesNotMatch(body, /proposalOf|runProposal|prop\?\.auto|kind: "proposal"/);
  assert.match(body, /const l = lightOf\(data\.light\);/);
  assert.match(body, /if \(data\.new\) browseRef\.current\?\.\("new", \{ \.\.\.data\.new, aid \}\);/);
  assert.match(body, /const page = "open" in data \? data\.open : firstAppLink\(data\.say\);/);
  // "send Erin the answer": the draft lands in the item's own reply box, and its Send is lit - drafting is not sending
  assert.match(view, /setLit\(\{ verb: "approve", label: btn\("approve"\), line: "", key: `review:\$\{data\.reviewId\}`/);
  // the lit act outranks the Advisor's line, which would name another button; any press puts it out
  assert.match(view, /<ActionRow advised=\{stripPick \|\| setupLit\}( hold=\{[^}]*\})?( early=\{[^}]*\})? \/>/);
  assert.match(view, /const shownAdvice = table\.speaks && !litNow \?/);
  assert.match(src("advice.js"), /pick: lit \|\| \(noAi \? \{ none: "no_ai", for: key \} : shown \|\| quiet\)/, "the light first, then no AI's way out, then the Advisor's decision, then Next (advice.stripWord)");
  assert.match(view, /useEffect\(\(\) => onPressed\(\(\) => setLit\(null\)\), \[\]\);/);
});

// THE LIT BUTTON IS THE WHOLE ANSWER (the owner, 2026-10-23: "what the heck is Lit"): no "Lit Mark done on TQ-0026." line in the chat and
// no "Press Mark done when you're sure." over the row - the filled button says it. A strip line is drawn only when a light carries one
test("a lit button says no line, in the chat or over the row", () => {
  const lit = lightOf({ verb: "close", label: label("close"), key: "msg:4", tid: 7 });
  assert.equal(lit.line, ""); assert.equal(litPick(lit, { key: "msg:4", tid: 7 }).line, "");
  const view = src("AssistantView.jsx"), light = src("assistantLight.js");
  assert.doesNotMatch(view + light.replace(/\/\/.*$/gm, ""), /when you're sure/);
  assert.doesNotMatch(light, /export const pressLine/);
  // ...and not even a light that carries one: no strip stands over the row to say it (the owner, 2026-10-26: "remove the advisor")
  assert.doesNotMatch(view + src("CanvasItem.jsx"), /data-tq-advice="lit"/);
  // ...and the one-row chat bar's pop-up, holding only the owner's own line when the answer was a lit button, shuts itself after a moment
  // (default chosen 2026-10-26) - never over an error or an answer still on its way
  assert.match(view, /if \(!popOpen \|\| popPending \|\| err \|\| popLast\?\.role !== "user"\) return undefined;\s*const t = setTimeout\(\(\) => setPopOpen\(false\), POP_LIT_MS\);/);
  assert.match(view, /const POP_LIT_MS = \d{3,4};/);
  // ...and a reply that only lit or pressed is no chat line at all: only words get one
  assert.match(view, /if \(data\.say \|\| data\.options\?\.length \|\| data\.chips\?\.length\)\s+setMsgs\(\(m\) => \[\.\.\.m, \{ id: aid, role: "assistant"/);
  assert.doesNotMatch(view, /Thinking about this one/, "no Thinking under it - or anywhere (the owner, 2026-10-23)");
  assert.match(view, /lit: litNow,/);
  assert.match(src("CanvasItem.jsx"), /<ActionRow inline advised=\{pick\} \/>/);
});

// A TYPED PUT-DOWN WAS PRESSED (concierge._put_down): the card wears the button's badge (and a Close with a note its note), and on the table
// it is put down as the row's own press puts it down - folded, the next item up
test("a typed put-down folds its card with the press badge and the note", () => {
  const view = src("AssistantView.jsx");
  const at = view.indexOf("const send = async"), body = view.slice(at, view.indexOf("const sendEmoji", at));
  assert.match(body, /const pr = data\.pressed;\s+if \(pr\?\.label\) \{\s+setMsgs\(\(m\) => pressLine\(m, pr, pr\.label, pr\.note \|\| ""\)\);/);
  assert.match(body, /canvasState\.putDown\(here\.key \|\| pr\.key, pr\.tid \?\? null\); advance\(null, true\);/);
  assert.match(view, /<Pressed label=\{pressedOf\(m\)\} note=\{pressedNoteOf\(m\)\} \/>/);
  assert.match(view, /\{note && <span className="tq-pressed-note" data-tq-pressed-note="" title=\{note\}>\{note\}<\/span>\}/);
  assert.match(src("assistantView.css"), /\.tq-pressed-note \{[^}]*white-space: nowrap; overflow: hidden; text-overflow: ellipsis;/);
});

test("the setting the Assistant names opens with its knob outlined", async () => {
  const { canvasRequestFromHash } = await import("../src/canvasLinks.js");
  assert.deepEqual(canvasRequestFromHash("#settings=config&group=Sync%20%26%20startup&key=poll_minutes").state,
    { section: "config", open: "Sync & startup", knob: "poll_minutes" });
  assert.match(src("SettingsView.jsx"), /const asked = only\?\.knob === s\.Name;/);
});

// REMIND ME'S SAID DAY (the owner, 2026-10-27): "remind me Monday" lit Remind me and its picker had no Monday, while the phone kept it.
// The day rides the light to the row's pick, the task view keeps it at the press, and the picker leads with it.
test("the day typed with Remind me rides the light into the picker as its first button", () => {
  const day = { until: "2026-11-02 07:00", day: "Mon 2 Nov" };
  const l = lightOf({ verb: "defer", label: "Remind me", key: "task:4", tid: 4, day });
  assert.deepEqual(l.day, day);
  assert.deepEqual(litPick(l, { key: "task:4", tid: 4 }).day, day, "the row's pick carries it");
  assert.equal(lightOf({ verb: "close", key: "task:4", tid: 4, day }).day, undefined, "only Remind me carries a day");
  assert.equal(lightOf({ verb: "defer", key: "task:4", tid: 4 }).day, undefined, "no day said, none carried");
  assert.equal(litPick(lightOf({ verb: "defer", key: "task:4", tid: 4 }), { key: "task:4" }).day, undefined);
  assert.match(src("CanvasItem.jsx"), /saidDay=\{lit\?\.verb === "defer" \? lit\.day \|\| null : null\}/);
  assert.match(src("TaskPage.jsx"), /const remindHere = \(at\) => \{ setRemindSaid\(saidRef\.current\); setRemindAt\(at\); \};/);
  assert.match(src("TaskPage.jsx"), /live=\{liveSession\}\n\s+said=\{remindSaid\} \/>/);
  assert.match(src("RemindMe.jsx"), /\{said\?\.until && said\?\.day && !away && \(/, "the said day leads the picker, before the learned day");
  assert.match(src("AssistantView.jsx"), /live: agentOpen\(item\), said: litDayRef\.current \}\); return; \}/, "the walk's own picker too");
});
