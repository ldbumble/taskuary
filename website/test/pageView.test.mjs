// THE ASSISTANT READS THE PAGE AND BRINGS THINGS UP - IT NEVER WORKS IN THEM (the owner, 2026-11-18: "it should just open the task, not do
// anything on the tasks. That's on the agent to do"). The page's half of taskuary/pageview.py.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { currentRoot, isSecret, run, typingOnPage } from "../src/pageView.js";

const read = (name) => fs.readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8");

test("a secret is known by its key or the words on its box", () => {
  for (const [k, l] of [["Secret", ""], ["client_secret", "Client secret"], ["x", "bot token (xoxb-…)"], ["api_key", ""], ["pw", "Password"]]) assert.equal(isSecret(k, l), true, k);
  for (const [k, l] of [["poll_seconds", "Check every (seconds)"], ["title", "Title"], ["region", "Region"]]) assert.equal(isSecret(k, l), false, k);
});

test("what leaves the page is the view without its elements, and a secret as its state only", () => {
  const src = read("pageView.js");
  assert.match(src, /secret: true, state: state \|\| "empty" \}/);
  assert.match(src, /buttons: v\.buttons\.map\(\(\{ id, label, enabled \}\) => \(\{ id, label, enabled \}\)\)/, "no element and no handler goes");
});

// 2026-11-18 walk: "let AI fill this in" posted "Fill in the mssql card with me" as the owner, the Assistant filled the report form, moved the
// page to a connection card while he typed, and his "No SQL Server..." became that card's name
test("the Assistant only opens a page or points at a thing - a fill or a press it asks for is never run", async () => {
  const src = read("pageView.js");
  assert.deepEqual((await import("../src/pageView.js")).OPS, ["open", "point"]);
  for (const gone of ['op.op === "set"', 'op.op === "press"', "setDom", "pickCombo", ".click()", "onReact", "startSession"]) assert.ok(!src.includes(gone), gone);
  const steps = [];
  const out = await run([{ op: "set", field: "title", value: "Vendor spend" }, { op: "press", button: "Save" }], (s) => steps.push(s));
  assert.deepEqual(out.steps, []); assert.deepEqual(steps, []);
});

test("an open never moves the page under his hands, and never takes the box he types in", () => {
  const box = (sel, skip = false) => ({ matches: (q) => q.startsWith("input:not") && sel === "input", closest: () => (skip ? {} : null) });
  assert.equal(typingOnPage(box("input")), true, "a box of the page holds the focus");
  assert.equal(typingOnPage(box("input", true)), false, "the chat's own box is not the page");
  assert.equal(typingOnPage(box("button")), false);
  assert.equal(typingOnPage(null), false);
  const src = read("pageView.js");
  assert.match(src, /if \(typingOnPage\(\)\) return step\(n, "Left the page as it is while you type", "done", "read"\);/);
  assert.match(src, /const letGo = keepFocus\(document\.activeElement\);/);
});


// A DIALOG OVER THE PAGE IS THE PAGE (the owner, 2026-11-02): Search everything, the Hub's Write one and the bell's list sit in a portal
// over a wider page - the widest root in sight was "the page", so the Assistant read the Hub beneath while the owner looked at the dialog
test("a dialog open over the page is the view, the one opened last on top; with none, the root most in sight", () => {
  const el = (name, size, modal = false) => ({ name, parentElement: { closest: () => null }, getClientRects: () => [1],
    closest: (sel) => (modal && sel === ".MuiModal-root" ? {} : null), getBoundingClientRect: () => ({ top: 0, left: 0, bottom: size, right: size }) });
  const was = { document: globalThis.document, window: globalThis.window, getComputedStyle: globalThis.getComputedStyle };
  let roots = [];
  Object.assign(globalThis, { document: { querySelectorAll: () => roots }, window: { innerHeight: 1000, innerWidth: 1000 },
    getComputedStyle: () => ({ visibility: "visible" }) });
  try {
    const hub = el("hub", 900), write = el("hub_write", 400, true), search = el("search", 500, true);
    roots = [hub]; assert.equal(currentRoot().name, "hub");
    roots = [hub, write]; assert.equal(currentRoot().name, "hub_write", "the smaller dialog wins over the wider page beneath");
    roots = [hub, write, search]; assert.equal(currentRoot().name, "search", "the dialog opened last is on top");
  } finally { Object.assign(globalThis, was); }
});


test("a page opened for the owner is named in the step without the model's note on what is open", async () => {
  const { shownTitle } = await import("../src/pageView.js");
  assert.equal(shownTitle("the Reports page, Reports section - nothing opened on it yet"), "the Reports page, Reports section");
  assert.equal(shownTitle("Badge swipes by site 9"), "Badge swipes by site 9");
  assert.equal(shownTitle(undefined), "");
});


test("the bell's ask is one sentence per stop - a detail's own full stop is not doubled (2026-11-12: \"...this computer is online.. Can you\")", async () => {
  const { failureAsk } = await import("../src/askAssistant.js");
  const p = { title: "Vendor mailbox: the last poll failed", detail: "The server's address could not be found. Check that this computer is online." };
  assert.equal(failureAsk(p), "Vendor mailbox: the last poll failed: The server's address could not be found. Check that this computer is online. Can you look into it and fix it?");
  assert.equal(failureAsk({ title: "Reports", detail: "It stopped", error: "timeout" }), "Reports: It stopped (timeout). Can you look into it and fix it?");
});
