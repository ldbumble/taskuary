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
  assert.deepEqual(litPick(landed, up), { verb: "defer", label: label("defer"), line: `Press ${label("defer")} when you're sure.` });
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
  assert.match(view, /setLit\(\{ verb: "approve", label: btn\("approve"\), line: `Read the draft, then press \$\{btn\("approve"\)\} when you're sure\.`, key: `review:\$\{data\.reviewId\}`/);
  // the lit act outranks the Advisor's line, which would name another button; any press puts it out
  assert.match(view, /<ActionRow advised=\{stripPick \|\| setupLit\} \/>/);
  assert.match(view, /const shownAdvice = table\.speaks && !litNow \?/);
  assert.match(src("advice.js"), /pick: lit \|\| \(noAi \? \{ none: "no_ai", for: key \} : shown \|\| quiet\)/, "the light first, then no AI's way out, then the Advisor's decision, then Next (advice.stripWord)");
  assert.match(view, /useEffect\(\(\) => onPressed\(\(\) => setLit\(null\)\), \[\]\);/);
});

// THE STRIP SAYS IT (verify, 2026-10-19): a lit Mark done stood dark under an empty strip, "Press Mark done" only up in the chat - the
// DARK and STRIP rules' own state. The line rides with the light and goes out with it; the chat keeps the past
test("the lit button's line is the strip's, over the composer and on a phone's own row", () => {
  const lit = lightOf({ verb: "close", label: label("close"), line: `Press ${label("close")} when you're sure.`, key: "msg:4", tid: 7 });
  assert.equal(litPick(lit, { key: "msg:4", tid: 7 }).line, `Press ${label("close")} when you're sure.`);
  assert.equal(lightOf({ verb: "defer", label: label("defer"), key: "task:2" }).line, `Press ${label("defer")} when you're sure.`, "a light with no line still says one");
  const view = src("AssistantView.jsx");
  assert.match(view, /\{table\.speaks && !!litNow && <div className="tq-next" role="status" data-tq-advice="lit"><div className="tq-next-txt">\{litNow\.line\}<\/div><\/div>\}/);
  assert.doesNotMatch(view, /Thinking about this one/, "no Thinking under it - or anywhere (the owner, 2026-10-23)");
  assert.match(view, /lit: litNow,/);
  assert.match(src("CanvasItem.jsx"), /<ActionRow inline advised=\{pick\} \/>/);
});

test("the setting the Assistant names opens with its knob outlined", async () => {
  const { canvasRequestFromHash } = await import("../src/canvasLinks.js");
  assert.deepEqual(canvasRequestFromHash("#settings=config&group=Sync%20%26%20startup&key=poll_minutes").state,
    { section: "config", open: "Sync & startup", knob: "poll_minutes" });
  assert.match(src("SettingsView.jsx"), /const asked = only\?\.knob === s\.Name;/);
});
