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
  // ...and the one-row chat bar's pop-up never shuts by itself (the owner, 2026-10-27: "it disappeared when done?") - no timer closes it
  assert.doesNotMatch(view, /POP_LIT_MS|setTimeout\(\(\) => setPopOpen\(false\)/);
  // ...and a reply that only lit or pressed is no chat line in the column: only words get one - in the chat window it ends on its receipt
  // ...or acts on the page it was asked about (pageView): those acts are its steps, drawn on its line (the owner, 2026-10-30)
  assert.match(view, /if \(data\.say \|\| data\.options\?\.length \|\| data\.chips\?\.length \|\| ops\.length\)\s+setMsgs\(\(m\) => \[\.\.\.m, \{ id: aid, role: "assistant"/);
  assert.match(view, /else if \(winOnRef\.current && !data\.context_update && !data\.decision\) \{ const r = actReceipt\(data, tableKey \|\| current\); receipt\(r\.text, r\.status\); \}/);
  assert.doesNotMatch(view, /Thinking about this one/, "no Thinking under it - or anywhere (the owner, 2026-10-23)");
  assert.match(view, /lit: litNow,/);
  assert.match(src("CanvasItem.jsx"), /<ActionRow inline advised=\{pick\}( says=\{.*?\})? \/>/);
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
  assert.match(src("TaskPage.jsx"), /onStay=\{onStay\}\n\s+said=\{remindSaid\} \/>/);
  assert.match(src("RemindMe.jsx"), /\{said\?\.until && said\?\.day && !away && \(/, "the said day leads the picker, before the learned day");
  assert.match(src("AssistantView.jsx"), /said: litDayRef\.current \}\); return; \}/, "the walk's own picker too");
});

// HAND IT TO A PERSON, ASKED FOR IN WORDS (the owner, 2026-11-03: "This should be sent to <an address>" did nothing): the light carries who
// and a note, the task view opens the form with them in it, and the form drafts the forward at once - Send is still the owner's press.
test("the person and note typed with Hand it to a person ride the light into its form", () => {
  const hand = { to: "gail@vendor.example", note: "Yours from here." };
  const l = lightOf({ verb: "forward", label: "Hand it to a person", key: "msg:5", tid: 31, hand });
  assert.deepEqual(l.hand, hand);
  assert.deepEqual(litPick(l, { key: "msg:5", tid: 31 }).hand, hand, "the row's pick carries it");
  assert.equal(lightOf({ verb: "close", key: "msg:5", tid: 31, hand }).hand, undefined, "only Hand it to a person carries one");
  assert.equal(lightOf({ verb: "forward", key: "msg:5", tid: 31, hand: { note: "x" } }).hand, undefined, "no person, nothing to fill");
  assert.match(src("CanvasItem.jsx"), /saidHand=\{lit\?\.verb === "forward" \? lit\.hand \|\| null : null\}/);
  assert.match(src("TaskPage.jsx"), /if \(saidHand\?\.to\) \{ setHandSaid\(\{ to: saidHand\.to, note: saidHand\.note \|\| "" \}\); setHandoff\(true\); \}/);
  assert.equal((src("TaskPage.jsx").match(/<Handoff key=\{handSaid \? [^\n]+? taskId=\{selected\} said=\{handSaid\} /g) || []).length, 1, "its one place, the drawer");
  const form = src("Handoff.jsx");
  assert.match(form, /useState\(said\?\.to \|\| ""\)/);
  assert.match(form, /useEffect\(\(\) => \{ if \(said\?\.to\) draft\(said\.to\); \}, \[\]\);/, "drafted when it opens");
  const opens = form.slice(form.indexOf("const draft = async"), form.indexOf("const send = async"));
  assert.match(opens, /draft_only: true/); assert.doesNotMatch(opens, /send\(/, "never sent by itself");
});
