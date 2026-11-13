// THE ASSISTANT ACTS ON THE PAGE AS THE OWNER WOULD - EXCEPT A SEND, AND NEVER A SECRET (the owner, 2026-10-30). The page's half of the two
// lines the server draws again (taskuary/pageview.py): which button sends something out, and which box holds a secret.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { currentRoot, isSecret, isSend } from "../src/pageView.js";

const read = (name) => fs.readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8");

test("an outward send is known by its verb or its words, and nothing else is one", () => {
  for (const b of [{ id: "row:approve", label: "Approve" }, { id: "x", label: "Send" }, { id: "x", label: "Send test message" }, { id: "x", label: "Anything", send: true },
    { id: "row:accept_invite", label: "Accept" }, { id: "x", label: "Reply all" }]) assert.equal(isSend(b), true, JSON.stringify(b));
  for (const b of [{ id: "test", label: "Test" }, { id: "row:done", label: "Mark done" }, { id: "save", label: "Save" }, { id: "sync", label: "Sync" },
    { id: "row:remind", label: "Remind me" }, { id: "row:redraft", label: "Redraft" }]) assert.equal(isSend(b), false, JSON.stringify(b));
});

test("a secret is known by its key or the words on its box", () => {
  for (const [k, l] of [["Secret", ""], ["client_secret", "Client secret"], ["x", "bot token (xoxb-…)"], ["api_key", ""], ["pw", "Password"]]) assert.equal(isSecret(k, l), true, k);
  for (const [k, l] of [["poll_seconds", "Check every (seconds)"], ["title", "Title"], ["region", "Region"]]) assert.equal(isSecret(k, l), false, k);
});

test("what leaves the page is the view without its elements, and a secret as its state only", () => {
  const src = read("pageView.js");
  assert.match(src, /secret: true, state: state \|\| "empty" \}/);
  assert.match(src, /buttons: v\.buttons\.map\(\(\{ id, label, enabled, send \}\)/, "no element and no handler goes");
  // ...and a press on a send is a light, checked again on the live page whatever the server said
  assert.match(src, /if \(op\.op === "point" \|\| \(b && \(isSend\(b\) \|\| isInstall\(b\)\)\)\)/);
});

test("the chat sends the view only with a line the owner asked, and runs what came back as steps", () => {
  const view = read("AssistantView.jsx");
  assert.match(view, /const view = how\.view !== undefined \? how\.view : pageView\.context\(\);/);
  assert.match(view, /\.\.\.\(view \? \{ view \} : \{\}\), \.\.\.\(react \? \{ react \} : \{\}\)/);
  assert.match(view, /await pageView\.run\(ops, \(steps\) => setMsgs/);
  // ...a reaction is no line of the owner's, never opens the window, and stops at three in a row
  assert.match(view, /if \(!react\) setMsgs\(\(m\) => \{ const i = held/);
  assert.match(view, /s\.auto >= 3\) return;/);
  // ...and its × asks before it ends the help
  assert.match(view, /if \(pageView\.sessionNow\(\)\?\.door\) setEnding\(true\); else \{ pageView\.endSession\(\); shutBox\(\); \}/);
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
  for (const b of ["`Dismiss: ${p.title}`", "`Got it: ${p.title}`", "`Ask the assistant: ${p.title}`"]) assert.ok(bell.includes(`aria-label={${b}}`), b);
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

// THE BUILDER'S DESCRIBE IS ON NO SCREEN (the visual audit, 2026-11-13): the Assistant pointed at it and told the owner to describe the
// dashboard "in the box" - there was no box. It says so to the server, which never lights it
test("a view field drawn nowhere says it is offscreen", () => {
  assert.match(read("pageView.js"), /fields: v\.fields\.map\(\(\{ key, label, kind, value, secret, state, options, disabled, offscreen \}\)/);
  assert.match(read("pageView.js"), /\.\.\.\(offscreen \? \{ offscreen \} : \{\}\)/);
  assert.match(read("ReportsView.jsx"), /fields: \[\{ key: "describe", offscreen: true,/);
});
