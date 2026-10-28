// EVERY PRESS, KEPT (the Advisor and memory design, phase B, 2026-10-23): each surface says what was pressed, what it had lit and what
// else could be pressed - the desk read through the row's own rowOf, the Tasks tab off the buttons it drew, the draft's own buttons
// heard before they run. Nothing on screen changes for it.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { announce, onPressing } from "../src/actionRow.js";
import { label } from "../src/buttons.js";
import { deskPress, notePress, pagePress, verbOf, verbOfLabel } from "../src/pressLog.js";
import { isWrite } from "../src/wrote.js";

const v = (id, group, extra = {}) => ({ id, group, tone: "s", label: id, title: "", disabled: false, why: "", promote: true, lead: false, ...extra });
const src = (f) => fs.readFileSync(path.join(process.cwd(), "src", f), "utf8");

test("a row id is its verb: Mark done is close, a draft's Send is approve, an Advisor-only move is its own verb", () => {
  assert.equal(verbOf("done"), "close"); assert.equal(verbOf("12:approve"), "approve"); assert.equal(verbOf("advice:chase"), "chase");
  assert.equal(verbOf("next"), "next");
});

test("the desk: nothing lit is recorded as nothing lit, with every live button - the card's own under the draft among them", () => {
  const snap = { ref: "TQ-1", list: [v("12:approve", "decide", { tone: "p", card: true, label: "Send" }), v("12:redraft", "decide", { card: true }),
    v("done", "more"), v("nat", "more", { disabled: true }), v("next", "next")] };
  const got = deskPress(snap, null, "done");
  assert.deepEqual(got, { pressed: "close", lit: "", live: ["close", "next", "approve", "redraft"], greyed: ["remove"] });   // a greyed button is no choice - but kept as greyed (A4)
});

test("the desk: what the row filled is what was lit - the Advisor's pick, Next under a 'nothing to do' line, a running agent's Stop", () => {
  const snap = { ref: "", list: [v("continue", "agent"), v("done", "more"), v("next", "next")] };
  assert.equal(deskPress(snap, { verb: "continue", label: "Continue" }, "done").lit, "continue");
  assert.equal(deskPress(snap, { verb: "next" }, "next").lit, "next");
  assert.equal(deskPress({ ref: "", list: [v("save-end", "agent", { fill: true }), v("next", "next")] }, null, "next").lit, "stop_agent");
});

test("the Tasks tab: a button is known by its one name, and the filled one is what was lit", () => {
  assert.equal(verbOfLabel(label("close")), "close"); assert.equal(verbOfLabel(` ${label("redraft", "none")} `), "redraft");
  assert.equal(verbOfLabel("Change"), "");                                // not a button with a verb: nothing recorded
  const b = (text, extra = {}) => ({ textContent: text, disabled: false, className: "MuiButton-root MuiButton-outlined", ...extra });
  const done = b(label("close"), { className: "MuiButton-root MuiButton-contained" });
  const page = { querySelectorAll: () => [b(label("approve")), done, b(label("defer")), b("Change"), b(label("forward"), { disabled: true })] };
  assert.deepEqual(pagePress(page, b(label("defer"))), { pressed: "defer", lit: "close", live: ["approve", "close", "defer"], greyed: ["forward"] });
  assert.equal(pagePress(page, b("Change")), null);
});

test("one press is posted with its surface, and a lost post never stops the press", async () => {
  const sent = [];
  const api = { post: (url, body, cfg) => { sent.push([url, body, cfg]); return Promise.reject(new Error("offline")); } };
  await notePress(api, { key: "task:3", pressed: "close", surface: "task", lit: "close", live: ["defer"] });
  assert.deepEqual(sent, [["/api/advice/press", { key: "task:3", pressed: "close", surface: "task", lit: "close", live: ["defer"], greyed: null, advised: null, revision: null }, { quiet: true }]]);
  // ...and that record is no write the sync caption must re-read for: every press of Next asked /api/ingest/status again (overnight walk)
  assert.equal(isWrite({ method: "post", ...sent[0][2] }), false);
  assert.equal(isWrite({ method: "post" }), true);
  assert.equal(isWrite({ method: "get" }), false);
  assert.equal(notePress(api, { key: "", pressed: "close" }), null);
});

test("the draft's own buttons are heard before they run, as the row's are", () => {
  const heard = [];
  const off = onPressing((id) => heard.push(id));
  announce("12:approve"); off();
  assert.deepEqual(heard, ["12:approve"]);
  const rd = src("ReviewDecision.jsx");
  for (const at of ['announce(no(verb));', 'announce(no("redraft"));', 'announce(no("copy"));']) assert.ok(rd.includes(at), at);
});

test("the Tasks tab hears every press on its own page, and only while it is the tab in view", () => {
  const tp = src("TaskPage.jsx");
  assert.match(tp, /if \(canvas \|\| !active \|\| !el\) return undefined;/);
  assert.match(tp, /el\.addEventListener\("click", heard, true\);/);
  assert.match(tp, /notePress\(api, \{ key: `task:\$\{selRef\.current\}`, surface: "task", \.\.\.got, advised: taskAdviceRef\.current\?\.verb \|\| null \}\)/);
  assert.match(tp, /<Box ref=\{pageRef\} data-tq-task-page=/);
});
