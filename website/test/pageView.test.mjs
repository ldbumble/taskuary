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

test("the chat sends the view only with a line the owner asked, and draws what it brought up as steps", () => {
  const view = read("AssistantView.jsx");
  assert.match(view, /const view = how\.view !== undefined \? how\.view : pageView\.context\(\);/);
  assert.match(view, /await pageView\.run\(ops, \(steps\) => setMsgs/);
  // ...it never reacts to his own edits on a page, and its x just shuts it
  for (const gone of ["how.react", "react:", "pageView.sessionNow", "pageView.HELP", "End this chat?"]) assert.ok(!view.includes(gone), gone);
});

test("it opens only by his hand: a failure or a refusal lands on the pill, never pops the window up over his task", () => {
  const view = read("AssistantView.jsx");
  assert.doesNotMatch(view, /useEffect\(\(\) => \{ if \(popErr\) setPopOpen\(true\)/);
  assert.doesNotMatch(view, /popLast\.refused \|\| \(popLast\.role === "receipt" && popLast\.status === "error"\)\)\) setPopOpen\(true\)/);
  const opens = [...view.matchAll(/setPopOpen\(true\)/g)].length;
  assert.equal(opens, 3, "a typed line, the bell's Ask press and the visitor's Setup press - nothing else");
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

test("Search, the Hub's Write one and the bell are views, each press named by what it is about", () => {
  const search = read("SearchEverything.jsx"), hub = read("HubView.jsx"), bell = read("TaskHubPage.jsx"), src = read("pageView.js");
  assert.match(search, /<Dialog open=\{open\} onClose=\{onClose\} data-tq-search="true" data-tq-view="search"/);
  // ...its hits are no buttons, so each says it is a press, named by its title and kind
  assert.match(search, /data-tq-view-press="" aria-label=\{`\$\{hit\.title \|\| "untitled"\} \(\$\{kindOf\(hit\)\.label\}\)`\}/);
  assert.match(src, /root\.querySelectorAll\("button, \[role=button\], \[role=tab\], \[data-tq-view-press\]"\)/);
  // ...brought up with its words in its box, and its hits waited for before one is pressed
  assert.match(read("AssistantView.jsx"), /area === "search" \? openAppLink\(`#search=\$\{encodeURIComponent\(state\.query \|\| ""\)\}`\)/);
  assert.match(src, /area === "search" && state\.query && i < 40 && !r\?\.querySelector\('\[data-tq-search-settled="true"\]'\)/);
  // Write one: its boxes keyed, its Post it an outward press - others read the Hub - lit for the owner, never pressed
  assert.match(hub, /<Dialog open=\{!!open\} onClose=\{onClose\} fullWidth maxWidth="sm" data-tq-view="hub_write"/);
  for (const k of ["title", "topic", "kind", "body"]) assert.match(hub, new RegExp(`"data-tq-field": "${k}"`), k);
  assert.match(hub, /disableElevation data-tq-send="" disabled=\{busy \|\| !title\.trim\(\)/);
  // ...each post's vote, comments and remove named by its post, so ten "remove"s are ten
  for (const b of ["`Vote up ${named}`", "`Vote down ${named}`", "`Remove ${named}`", "`Restore ${named}`", '`${plural(commentCount, "comment")} on ${named}`'])
    assert.ok(hub.includes(`aria-label={${b}}`), b);
  // the bell: a view while open, and each problem's buttons named by the problem
  assert.match(bell, /<Popover open=\{!!el\} anchorEl=\{el\} onClose=\{\(\) => setEl\(null\)\} data-tq-view="bell"/);
  for (const b of ["`Dismiss: ${p.title}`", "`Got it: ${p.title}`", "`Ask ${ASSISTANT_NAME}: ${p.title}`"]) assert.ok(bell.includes(`aria-label={${b}}`), b);
});

test("a Hub post removed is under Recently deleted on the Hub, read again after a press on a post", () => {
  const hub = read("HubView.jsx");
  assert.match(hub, /const shelf = <RecentlyDeleted key=\{bin\} kinds=\{\["hub post"\]\} onRestored=\{load\} \/>;/);
  assert.match(hub, /const changed = \(\) => \{ load\(\); setBin\(\(n\) => n \+ 1\); \};/);
  assert.match(read("Removed.jsx"), /d\.kind === "hub post" \? "off this list" : "gone for good"/);
});

test("a page opened for the owner is named in the step without the model's note on what is open", async () => {
  const { shownTitle } = await import("../src/pageView.js");
  assert.equal(shownTitle("the Reports page, Reports section - nothing opened on it yet"), "the Reports page, Reports section");
  assert.equal(shownTitle("Badge swipes by site 9"), "Badge swipes by site 9");
  assert.equal(shownTitle(undefined), "");
});

test("the bell's Ask the assistant opens the chat window and asks in it - not into a closed one (2026-11-12: pressed, nothing happened)", () => {
  const view = read("AssistantView.jsx");
  // askAssistant's road (tq-ask) asked into the chat pop-up without opening it; the doors (openHelp) open it first - so does this one
  assert.match(view, /const on = \(\) => \{ const t = takeAsk\(\); if \(!t\) return; setPopOpen\(true\); askRef\.current\(t\); \};/);
});

test("the bell's ask is one sentence per stop - a detail's own full stop is not doubled (2026-11-12: \"...this computer is online.. Can you\")", async () => {
  const { failureAsk } = await import("../src/askAssistant.js");
  const p = { title: "Vendor mailbox: the last poll failed", detail: "The server's address could not be found. Check that this computer is online." };
  assert.equal(failureAsk(p), "Vendor mailbox: the last poll failed: The server's address could not be found. Check that this computer is online. Can you look into it and fix it?");
  assert.equal(failureAsk({ title: "Reports", detail: "It stopped", error: "timeout" }), "Reports: It stopped (timeout). Can you look into it and fix it?");
});
