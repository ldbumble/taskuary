// The Assistant brings up the app's own screens (the owner, 2026-10-15: "help me set up the intacct api" should open the Sage
// Intacct settings page; "if it needs to know setting for x, bring the settings view up").
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { appLink, firstAppLink, inApp, linkName, linkRoad, ownPath } from "../src/appLinks.js";

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

// B24 (the email walk, 2026-10-29): "Choose where it works" opened Settings → Coding agent, which has no folder field - the fix now
// opens the task on its own "Which code is this about?" picker (failures.pick_repo_href)
test("a task's pick-repo link opens the task and its picker, once, on that task only", async () => {
  const { openAppLink, takeRepoPick, PICK_REPO } = await import("../src/appLinks.js");
  const fired = [];
  globalThis.window = { location: { hash: "", href: "" }, history: { state: null, replaceState: () => {} }, dispatchEvent: (e) => fired.push(e) };
  globalThis.CustomEvent = class { constructor(t, o) { this.type = t; this.detail = o?.detail; } };
  openAppLink("#task=12&pick=repo");
  assert.equal(window.location.hash, "task=12", "the task opens as #task=12 does");
  await new Promise((r) => setTimeout(r, 5));
  assert.deepEqual(fired.map((e) => [e.type, e.detail?.tid]), [[PICK_REPO, 12]]);
  assert.equal(takeRepoPick(7), false, "another task's page never takes it");
  assert.equal(takeRepoPick(12), true); assert.equal(takeRepoPick(12), false, "taken once");
  delete globalThis.window; delete globalThis.CustomEvent;
  const page = read("TaskPage.jsx");
  assert.match(page, /const take = \(\) => \{ if \(takeRepoPick\(selected\)\) pickRepoRef\.current\?\.\(\); \};/);
  assert.match(page, /pickRepoRef\.current = pickRepo;/);
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
  assert.match(read("AssistantView.jsx"), /const page = "open" in data \? data\.open : firstAppLink\(data\.say\);\n[^]*?\} else if \(page\) \{[^]*?openAppLink\(page\);/);
  // ...a task it opens is a press of its rail row (the owner, 2026-10-28), said in the chat window
  assert.match(read("AssistantView.jsx"), /const opens = \/\^#\?task=\(\\d\+\)\$\/\.exec\(page \|\| ""\);\n\s*if \(opens\) \{\n[^\n]*\n\s*pressRowRef\.current\?\.\(n\);\n\s*receipt\(`Opened /);
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

test("every #hash a reply links is followed in the app window, never a new browser tab (TQ-1251: #new-task opened the browser)", () => {
  for (const h of ["#new-task", "#new-task&kind=agent", "#msg=12", "#settings=docs"]) assert.equal(inApp(h), true, h);
  for (const h of ["https://example.com", "/api/task-outputs/3/x.png", "#", "", null]) assert.equal(inApp(h), false, String(h));
});

// OUTSIDE LINKS GO TO THE SYSTEM BROWSER, THE APP'S OWN STAY IN THE WINDOW (the owner, 2026-11-02). A new tab (target=_blank) is what the
// desktop window hands to the system browser - so only the web gets one. The app's own address written out whole
// (http://127.0.0.1:<port>/#settings), an /api/ file and a path of the app's got a new tab too, and left the window
test("a link's road: the web leaves for the system browser; the app's pages, tasks and files stay in the window", () => {
  const here = { origin: "http://127.0.0.1:8765" };
  const road = (h) => linkRoad(h, here);
  for (const h of ["https://vendor.example/pricing", "http://docs.example/x#top", "mailto:erin@northwind.example", "http://127.0.0.1:9999/"])
    assert.equal(road(h), "outside", h);
  assert.equal(road("#task=12"), "task"); assert.equal(road("http://127.0.0.1:8765/#task=12"), "task");
  assert.equal(road("#connector=intacct"), "page"); assert.equal(road("http://127.0.0.1:8765/#settings=policies"), "page"); assert.equal(road("/#new-task"), "page");
  for (const h of ["/api/task-outputs/3/x.png", "/api/attachments/7", "http://127.0.0.1:8765/api/task-artifacts/3/7", "/assets/chart.png"]) assert.equal(road(h), "file", h);
  for (const h of ["/", "http://127.0.0.1:8765/?view=board", "http://127.0.0.1:8765"]) assert.equal(road(h), "app", h);
  assert.equal(road("//vendor.example/x"), "outside", "a scheme-relative address is another site");
  assert.equal(ownPath("http://127.0.0.1:8765/api/task-artifacts/3/7?x=1", here), "/api/task-artifacts/3/7?x=1");
  // ...and the reply's link draws by that road: a new tab for the web alone
  assert.match(read("md.jsx"), /target=\{road === "outside" \? "_blank" : undefined\}/);
});

test("a report's run linked by an answer opens on the table as a Search pick does, and is named by the words it was linked with", () => {
  // the owner, 2026-11-03: "open the report should open the report like search" - search.places links a report's newest run as #msg=N
  assert.equal(firstAppLink("Here: [AP ageing over 30 days, weekly](#msg=10)."), "#msg=10");
  assert.equal(firstAppLink("[AP ageing](#msg=10) or [Headcount](#msg=9)?"), null, "two runs: the owner picks");
  assert.equal(firstAppLink("That is [TQ-0012](#task=12), from [the run](#msg=10)."), "#task=12", "a task named still opens");
  assert.equal(linkName("Here: [AP ageing over 30 days, weekly](#msg=10).", "#msg=10"), "AP ageing over 30 days, weekly");
  assert.equal(linkName("Here: [Settings](#settings=config).", "#msg=10"), "");
});
