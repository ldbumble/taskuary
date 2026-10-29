// The Assistant brings up the app's own screens (the owner, 2026-10-15: "help me set up the intacct api" should open the Sage
// Intacct settings page; "if it needs to know setting for x, bring the settings view up").
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { appLink, firstAppLink } from "../src/appLinks.js";

const read = (name) => fs.readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8");

test("our pages are app links; the web and unknown hashes are not", () => {
  for (const h of ["#connector=intacct", "#cli-agents", "#settings=policies", "#report=new-agent", "#report=12", "#profiles", "#setup"])
    assert.equal(appLink(h), h, h);
  for (const h of ["https://example.com", "#nothing-here", "", "#task=12"]) assert.equal(appLink(h), null, h);
});

// "set up taskuary" typed in the chat was answered with a link to Company Hub - setup had no address (2026-10-16)
test("#setup opens setup mode, the same door as the top bar's Setup", async () => {
  const { openAppLink } = await import("../src/appLinks.js");
  let fired = "";
  globalThis.window = { location: { hash: "" }, dispatchEvent: (e) => { fired = e.type; } };
  globalThis.Event = class { constructor(t) { this.type = t; } };
  openAppLink("#setup");
  assert.equal(fired, "tq-first-run"); assert.equal(window.location.hash, "");
  delete globalThis.window;
});

test("a reply opens the page it names - else the one task it points at, never one of several", () => {
  assert.equal(firstAppLink("Here it is: [Open the Sage Intacct connection](#connector=intacct). Fill in the sender ID."), "#connector=intacct");
  assert.equal(firstAppLink("See [TQ-0012](#task=12) and the [settings](#settings=config)."), "#settings=config");
  assert.equal(firstAppLink("That is [TQ-0012](#task=12)."), "#task=12");
  assert.equal(firstAppLink("Both [TQ-0012](#task=12) and [TQ-0013](#task=13) are open."), null);
  assert.equal(firstAppLink("Read [the docs](https://example.com/x)."), null);
  // two pages is no choice to make for the owner, and the same page twice is one
  assert.equal(firstAppLink("[Outlook](#connector=outlook) or [Gmail](#connector=gmail)?"), null);
  assert.equal(firstAppLink("[Outlook](#connector=outlook) - [open it](#connector=outlook)"), "#connector=outlook");
  // setup replaces the page, the answer with it: its link is pressed, never followed
  assert.equal(firstAppLink("Run [setup](#setup) to connect your mail."), null);
});

test("the chat opens it on a fresh reply, and a link in the text opens it in place", () => {
  assert.match(read("AssistantView.jsx"), /const page = "open" in data \? data\.open : firstAppLink\(data\.say\);\n[^]*?\} else if \(page\) openAppLink\(page\);/);
  // ...a task it opens is a press of its rail row (the owner, 2026-10-28), said in the chat window
  assert.match(read("AssistantView.jsx"), /const opens = \/\^#\?task=\(\\d\+\)\$\/\.exec\(page \|\| ""\);\n\s*if \(opens\) \{\n[^\n]*\n\s*pressRowRef\.current\?\.\(n\);\n\s*setMsgs\(\(m\) => \[\.\.\.m, \{ id: `r\$\{Date\.now\(\)\}`, role: "receipt", status: "done", text: `Opened /);
  assert.match(read("md.jsx"), /else if \(page\) \{ e\.preventDefault\(\); openAppLink\(page\); \}/);
  assert.match(read("ChatThread.jsx"), /\{hasFiles && <Attachments messageId=\{m\.MessageId\} \/>\}/);    // pictures at reading size
});

// THE BOARD AND SEARCH, from the chat (concierge.page_href, 2026-10-28): the Board is its own address, read by the page's one router;
// Search is a dialog, so its link opens it with the words in its box and writes no address
test("#search= opens Search with its words; #board is the Board's own address", async () => {
  const { openAppLink, OPEN_SEARCH } = await import("../src/appLinks.js");
  const fired = [];
  globalThis.window = { location: { hash: "", href: "" }, history: { state: null, replaceState() {} }, dispatchEvent: (e) => fired.push(e) };
  globalThis.CustomEvent = class { constructor(t, o) { this.type = t; this.detail = o?.detail; } };
  openAppLink("#search=May%20close%20numbers");
  openAppLink("#search=");
  assert.deepEqual(fired.map((e) => [e.type, e.detail.q]), [[OPEN_SEARCH, "May close numbers"], [OPEN_SEARCH, ""]]);
  assert.equal(window.location.hash, "", "a dialog is no place");
  openAppLink("#board");
  assert.equal(window.location.hash, "board");
  delete globalThis.window; delete globalThis.CustomEvent;
  assert.match(read("TaskHubPage.jsx"), /if \(h === BOARD\) \{ setTab\("Board"\)/);
  assert.match(read("FeedView.jsx"), /setSearchQ\(String\(e\?\.detail\?\.q \|\| ""\)\); setSearchOpen\(true\);/);
  assert.match(read("SearchEverything.jsx"), /if \(open && query\) \{ typed\.current = query; setQ\(query\); \}/);
});
