import test from "node:test";
import assert from "node:assert/strict";
import {
  DEFAULT_RATIO,
  clampRatio,
  fitFrame,
  keyMessage, isPaste, pasteMessages,
  isLocalPage,
  layoutFor,
  MIN_CHAT_PX,
  mayShape,
  mouseMessage,
  parseMessage,
  ratioFromPointer,
  shortUrl,
  showsBrowser,
  splitRatio,
  toPage,
  viewportFor,
  viewportMoved,
  viewOnScreen,
  heldOn,
  isTurn,
  askPlaceholder,
  needsOwner,
  TURN_PREFIX,
  wheelMessage,
} from "../src/browserSplit.js";

test("the split stays between a third and four fifths, and defaults when unset", () => {
  assert.equal(clampRatio(0.58), 0.58);
  assert.equal(clampRatio(0.1), 0.3);
  assert.equal(clampRatio(0.95), 0.8);
  assert.equal(clampRatio(NaN), DEFAULT_RATIO);
});

test("dragging the handle sets the browser's share from the pointer's place across the slot", () => {
  assert.equal(ratioFromPointer(400, 0, 1000), 0.6);        // pointer at 40%: terminal 40, browser 60
  assert.equal(ratioFromPointer(950, 0, 1000), 0.3);        // past the minimum: pinned
  assert.equal(ratioFromPointer(100, 0, 0), DEFAULT_RATIO);
});

test("a frame is letterboxed whole into its box, never cropped or stretched", () => {
  assert.deepEqual(fitFrame(1280, 720, 640, 640), { x: 0, y: 140, w: 640, h: 360, scale: 0.5 });
  assert.deepEqual(fitFrame(1280, 720, 1000, 360), { x: 180, y: 0, w: 640, h: 360, scale: 0.5 });
  assert.equal(fitFrame(0, 0, 100, 100).scale, 0);
});

test("a pointer on the canvas maps back to page pixels, and the margin is nowhere", () => {
  const fit = fitFrame(1280, 720, 640, 640);
  assert.deepEqual(toPage(320, 320, fit), { x: 640, y: 360 });
  assert.equal(toPage(10, 10, fit), null);                  // on the letterbox above the page
  assert.equal(toPage(10, 10, null), null);
});

test("mouse and wheel events become CDP input at page coordinates", () => {
  const fit = fitFrame(1280, 720, 640, 640);
  assert.deepEqual(mouseMessage("mousedown", { offsetX: 320, offsetY: 320, button: 0 }, fit),
    { type: "input_mouse", eventType: "mousePressed", x: 640, y: 360, button: "left", clickCount: 1, modifiers: 0 });
  assert.equal(mouseMessage("mousemove", { offsetX: 320, offsetY: 320, button: 0 }, fit).clickCount, 0);
  assert.equal(mouseMessage("mousedown", { offsetX: 1, offsetY: 1, button: 0 }, fit), null);
  assert.equal(mouseMessage("dblclick", { offsetX: 320, offsetY: 320, button: 0 }, fit), null);
  const w = wheelMessage({ offsetX: 320, offsetY: 320, deltaY: 120, shiftKey: true }, fit);
  assert.equal(w.eventType, "mouseWheel"); assert.equal(w.deltaY, 120); assert.equal(w.modifiers, 8);
});

test("keystrokes carry text for printable keys and Enter, none for chords and specials", () => {
  assert.deepEqual(keyMessage("keydown", { key: "a", code: "KeyA" }),
    { type: "input_keyboard", eventType: "keyDown", key: "a", code: "KeyA", modifiers: 0, text: "a", windowsVirtualKeyCode: 65, nativeVirtualKeyCode: 65 });
  // the editing keys run off the Windows key code in Chrome - without it Backspace did nothing (2026-11-03)
  for (const [key, vk] of [["Backspace", 8], ["Delete", 46], ["Tab", 9], ["ArrowLeft", 37], ["ArrowRight", 39], ["Home", 36], ["End", 35]]) {
    const m = keyMessage("keydown", { key, code: key });
    assert.equal(m.eventType, "rawKeyDown"); assert.equal(m.windowsVirtualKeyCode, vk, key); assert.equal(m.text, undefined);
    assert.equal(keyMessage("keyup", { key, code: key }).windowsVirtualKeyCode, vk);
  }
  const all = keyMessage("keydown", { key: "a", code: "KeyA", ctrlKey: true });
  assert.equal(all.windowsVirtualKeyCode, 65); assert.equal(all.modifiers, 2);
  assert.equal(keyMessage("keydown", { key: "Enter", code: "Enter" }).windowsVirtualKeyCode, 13);
  assert.ok(isPaste({ key: "v", ctrlKey: true }) && isPaste({ key: "V", metaKey: true }) && !isPaste({ key: "v" }));
  assert.deepEqual(pasteMessages("a\r\nb").map((m) => m.text), ["a", "\r", "b"]);
  // a password's shifted symbols and capitals go in as typed: the character is the key's own, Shift rides only in the modifiers (2026-11-04)
  for (const [key, code, keyCode] of [["!", "Digit1", 49], ["@", "Digit2", 50], ["&", "Digit7", 55], ["Z", "KeyZ", 90], ["~", "Backquote", 192], ['"', "Quote", 222]]) {
    const m = keyMessage("keydown", { key, code, keyCode, shiftKey: true });
    assert.equal(m.text, key, key); assert.equal(m.modifiers, 8); assert.equal(m.windowsVirtualKeyCode, keyCode);
  }
  assert.equal(pasteMessages("P@ss!w0rd#$%^&*()").map((m) => m.text).join(""), "P@ss!w0rd#$%^&*()");
  assert.equal(keyMessage("keydown", { key: "a", code: "KeyA", ctrlKey: true }).text, undefined);
  assert.equal(keyMessage("keydown", { key: "Enter", code: "Enter" }).text, "\r");
  // ...and as a key that types: Chrome drops a rawKeyDown's text, so Enter in a password box sent no form
  assert.equal(keyMessage("keydown", { key: "Enter", code: "Enter" }).eventType, "keyDown");
  assert.equal(keyMessage("keydown", { key: "Tab", code: "Tab" }).eventType, "rawKeyDown");
  assert.equal(keyMessage("keyup", { key: "a", code: "KeyA" }).eventType, "keyUp");
  assert.equal(keyMessage("keypress", { key: "a", code: "KeyA" }), null);
});

test("frames parse into something drawable; other messages pass through; junk is dropped", () => {
  const f = parseMessage(JSON.stringify({ type: "frame", seq: 3, data: "AAAA", metadata: { deviceWidth: 800, deviceHeight: 600, timestamp: 5 } }));
  assert.deepEqual(f, { type: "frame", seq: 3, src: "data:image/jpeg;base64,AAAA", w: 800, h: 600, at: 5 });
  assert.deepEqual(parseMessage('{"type":"url","url":"https://a.test/"}'), { type: "url", url: "https://a.test/" });
  assert.equal(parseMessage("not json"), null);
  assert.equal(parseMessage("42"), null);
});

test("urls are shown without scheme, cut in the middle when long", () => {
  assert.equal(shortUrl("https://login.vendor.example/home/userLogin.xhtml"), "login.vendor.example/home/userLogin.xhtml");
  assert.equal(shortUrl("https://a.test/"), "a.test");
  assert.equal(shortUrl(""), "");
  const long = shortUrl(`https://a.test/${"x".repeat(200)}`, 40);
  assert.ok(long.length <= 41 && long.includes("…"));
});

// THE AGENT'S OWN FILE IN ITS BROWSER IS NAMED, never shown as a disk path (the stress test, 2026-11-02: the chip read
// "browser · file:///C:/Users/<you>/.taskuary/scratch/...")
test("a page the agent opened from disk is its file's name, never the path to it", () => {
  assert.equal(shortUrl("file:///C:/Users/alex/.taskuary/scratch/outputs/TQ-0001/desk%20plan.svg"), "file · desk plan.svg");
  assert.equal(shortUrl("file:///home/alex/out/notes.html#top"), "file · notes.html");
  assert.equal(shortUrl("FILE:///C:/a/b/"), "file · b");
  assert.doesNotMatch(shortUrl(`file:///C:/Users/alex/${"deep/".repeat(30)}report.html`, 28), /Users|C:|\//);
});

test("the slot decides: no browser is nothing, a narrow slot is a chip, otherwise the split unless folded", () => {
  assert.equal(layoutFor(1200, false, false), "none");
  assert.equal(layoutFor(500, true, false), "chip");
  assert.equal(layoutFor(1200, true, false), "split");
  assert.equal(layoutFor(1200, true, true), "folded");
});

// THE BROWSER IN THE AGENT'S CANVAS (the owner, 2026-10-28): an agent's conversation too narrow to split stacks the view above it -
// only a phone's width folds it to the chip, its link
test("an agent's conversation stacks the view above it when narrow, and a phone gets the chip", () => {
  assert.equal(layoutFor(600, true, false, true), "stack");
  assert.equal(layoutFor(600, true, true, true), "folded");
  assert.equal(layoutFor(390, true, false, true), "chip");
  assert.equal(layoutFor(1200, true, false, true), "split");
  assert.equal(layoutFor(600, true, false), "chip", "a Wall tile keeps its chip");
  assert.ok(viewOnScreen("split") && viewOnScreen("stack") && !viewOnScreen("chip") && !viewOnScreen("folded"));
});

test("what waits on the view: a held act of THIS browser, and the agent's hand-over", () => {
  const row = (p, id = 7) => ({ ReviewId: id, DraftText: JSON.stringify(p) });
  const act = { action: "browser_act", sid: "s1", command: "agent-browser click @e7", what: 'press "Register" on events.trainly.example',
    site: "trainly.example", url: "https://events.trainly.example/r", why: "it can't be undone" };
  assert.deepEqual(heldOn(row(act), "s1"), { id: 7, what: act.what, site: act.site, url: act.url, why: act.why });
  assert.equal(heldOn(row(act), "s2"), null, "another session's act stays on its card");
  assert.equal(heldOn(row({ ...act, action: "shell_act" }), "s1"), null, "a shell step is not the browser's");
  assert.equal(heldOn({ ReviewId: 1, DraftText: "not json" }, "s1"), null);
  assert.equal(heldOn(row({ ...act, what: "" }), "s1").what, act.command);
  assert.ok(isTurn({ request_id: `${TURN_PREFIX}abc` }));
  assert.ok(!isTurn({ request_id: "signin:bank.example" }) && !isTurn(null));
});


test("the page is given the pane's shape, at a desktop width", () => {
  // 55% of the pane was black because a 16:9 render was fitted into a tall box (measured
  // 2026-09-14). Matching the SHAPE removes the bars; holding the WIDTH keeps the desktop layout.
  assert.deepEqual(viewportFor(860, 1060), { w: 1200, h: 1479 });   // narrow pane: width floors at 1200
  assert.deepEqual(viewportFor(1600, 800), { w: 1600, h: 800 });    // a wide pane keeps its own width
  // ...but a laptop's pane (under NARROW_PANE) gets 980: at 1200 a 540px pane drew the page at 45% (2026-10-25)
  assert.deepEqual(viewportFor(488, 605), { w: 980, h: 1215 });
  assert.equal(viewportFor(538, 347).w, 980);
  assert.equal(viewportFor(0, 600), null);
  assert.equal(viewportFor(600, 0), null);
  assert.ok(viewportFor(1200, 10).h >= 400, "never a slit: a floor keeps the page usable");
});

test("dragging the splitter does not re-lay-out Chrome for six pixels", () => {
  const was = { w: 1200, h: 1400 };
  assert.equal(viewportMoved(was, { w: 1200, h: 1410 }), false);
  assert.equal(viewportMoved(was, { w: 1200, h: 1460 }), true);
  assert.equal(viewportMoved(null, was), true, "the first measurement always lands");
  assert.equal(viewportMoved(was, null), false);
});

// The 2026-10-02 pane pass: a live run of Board -> New task -> "It needs a browser", watched from a desktop and a phone.
test("the chat keeps a readable width whatever share the browser was dragged to", () => {
  assert.equal(splitRatio(0.8, 1000), (1000 - MIN_CHAT_PX - 8) / 1000);   // 4/5 of 1000 left the chat ~200px
  assert.ok((1 - splitRatio(0.8, 1000)) * 1000 - 8 >= MIN_CHAT_PX);
  assert.equal(splitRatio(0.5, 2000), 0.5);                               // room enough: the owner's ratio stands
  assert.equal(splitRatio(0.8, 0), 0.8);                                  // not measured yet
  assert.equal(splitRatio(0.6, 400), 0.3);                                // never below the browser's own floor
});

test("only a browser open on a page is shown: not one still starting, nor an empty tab (2026-11-04)", () => {
  assert.equal(showsBrowser(true, "https://fares.example/results"), true);
  assert.equal(showsBrowser(true, "file:///receipt.html"), true);         // a local file: shown folded to its chip (isLocalPage)
  assert.equal(showsBrowser(true, "about:blank"), false);                 // "no browser should open if we don't have a URL"
  assert.equal(showsBrowser(true, ""), false);
  assert.equal(showsBrowser(false, "https://fares.example/results"), false);   // closed, or still coming up
});

test("only the tab the owner is at shapes the page, so a phone tab cannot reshape the desktop's", () => {
  assert.equal(mayShape(false, true), true);
  assert.equal(mayShape(false, false), false);             // a background window's resize
  assert.equal(mayShape(false, false, true), true);        // a press in the pane, Take over, the window coming back
  assert.equal(mayShape(true, true, true), false);         // a hidden tab never does
});

test("a file the agent opened in its browser is not browsing, so it takes no room until asked", () => {
  assert.equal(isLocalPage("file:///C:/Users/a/AppData/Local/Temp/receipt-15-handwritten.html"), true);
  assert.equal(isLocalPage(" FILE:///tmp/x.html"), true);
  assert.equal(isLocalPage("https://example.com/login"), false);
  assert.equal(isLocalPage("about:blank"), false);
  assert.equal(isLocalPage(""), false);
});

test("an empty tab is not a page: the view folds to its chip until the agent opens one, or something waits on it", async () => {
  const { isBlankPage, waitsOnPage } = await import("../src/browserSplit.js");
  assert.equal(isBlankPage("about:blank"), true);
  assert.equal(isBlankPage(""), true);
  assert.equal(isBlankPage(" about:newtab"), true);
  assert.equal(isBlankPage("https://portal.example/login"), false);
  // "your turn - click the page and type" is for a wait ON the page - its hand-over or a sign-in - never a question asked in words
  assert.equal(waitsOnPage({ request_id: `${TURN_PREFIX}abc` }), true);
  assert.equal(waitsOnPage({ request_id: "signin:portal.example" }), true);
  assert.equal(waitsOnPage({ request_id: "571e07b97197", text: "First month free, or a price now?" }), false);
  assert.equal(waitsOnPage(null), false);
});

// A CHAT TASK'S BROWSER (the owner, 2026-11-05): drawn only when the owner has a part on the page, and then beside the chat
test("a chat task's browser shows only when the owner is needed, side by side", async () => {
  const { needsOwner, quietLayout, quietRatio, CHAT_SHARE } = await import("../src/browserSplit.js");
  assert.equal(needsOwner(null), false);                                                   // the agent just browsing
  assert.equal(needsOwner({ request_id: "q:where" }), false);                              // a question asked in words: the chat's box
  assert.equal(needsOwner({ request_id: "signin:bank.example" }), true);                   // a sign-in (or its code) the vault does not keep
  assert.equal(needsOwner({ request_id: "yourturn:captcha" }), true);                      // a captcha handed over
  assert.equal(needsOwner(null, [{ id: 7 }]), true);                                       // a held step: Approve / Dismiss
  assert.equal(quietLayout(1200, false), "none");
  for (const w of [555, 600, 700, 900, 1400]) assert.equal(quietLayout(w, true), "split");     // never stacked at a desktop's width
  assert.equal(quietLayout(380, true), "chip");                                            // a phone's width: the view as a link
  assert.equal(quietLayout(900, true, true), "folded");                                    // the owner's own Fold
  for (const r of [0.3, 0.58, 0.8, NaN]) assert.ok(1 - quietRatio(r) >= CHAT_SHARE - 1e-9 && quietRatio(r) >= 0.3);
});

// THE CHAT'S WIDTH, SAMPLED EVERY PAINTED FRAME while a browser opened, folded, came back and closed beside it (2026-11-11, a 1600px window):
// at rest 1049px, at work 1073 (the section's room changed with the session); the pane opening drew 479px in the chat's own column, then 479
// at the window's left, then 655 - three layouts in 300 ms; folded to its chip, the chat ran 1465px with the task list still gone.
test("the chat keeps one width at rest and at work, and the browser pane arrives and leaves in one step", async () => {
  const { readFileSync } = await import("node:fs");
  const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
  const term = read("TerminalView.jsx"), page = read("TaskPage.jsx");
  // ...AND THE TASK LIST STAYS WHERE IT IS (design round 6, D8: the list folded for the page and his rail went with it): nothing asks for its room
  const feed = read("FeedView.jsx");
  assert.doesNotMatch(term + page + feed + read("browserSplit.js"), /wantRoom|onRoom|roomWanted/);
  assert.match(feed, /const folded = setupMode;/);
  assert.match(term, /new ResizeObserver\(\(\[e\]\) => flushSync\(\(\) => setWidth\(e\.contentRect\.width\)\)\);/, "the pane's own width is the frame's");
  assert.match(page, /bodyRO\.current = new ResizeObserver\(\(\[e\]\) => flushSync\(\(\) => setBodyW\(Math\.round\(e\.contentRect\.width\)\)\)\);/, "and the task's sections are sized for the width the frame has");
  assert.match(page, /SECTION\(isOpen\("agent"\), openW\("agent"\), sessionView, liveSession, fades\), \.\.\.\(chatPane \? \{ pb: 0\.25, px: 1, pt: 0\.65 \} : \{\}\)/, "a chat's section keeps the live room at rest too");
  // ...and a CODING agent's page is shown him too, while he is needed on it (the recorded coding walk, 2026-11-12: it asked to be signed in, and
  // with no chat session to name, no page was ever shown) - its session's own browser
  const chat = readFileSync(new URL("../src/GeneralWorkspace.jsx", import.meta.url), "utf8");
  assert.match(chat, /<SessionPane sid=\{\(!noTools && session\?\.sid\) \|\| \(coding && needNow && cli\?\.sid\) \|\| null\}/);
});

// THE VIEW OPENING FOR A STEP OF HIS, WATCHED FRAME BY FRAME (the browser round, 2026-11-14): the page was drawn small between bars, then again
// at its size 0.6 s later; and its address bar read the sign-in page's address over the code page the saved sign-in had moved it on to.
test("the first picture of a view waits a moment for the pane's shape, and the greeting's tabs name the page", async () => {
  const { holdFirst, FIRST_WAIT, activeTab, viewportFor } = await import("../src/browserSplit.js");
  const box = { width: 623, height: 507 }, want = viewportFor(box.width, box.height);
  assert.equal(holdFirst(false, { w: 1280, h: 720 }, box, 0), true, "a frame at another shape is held while nothing is drawn");
  assert.equal(holdFirst(false, { w: want.w, h: want.h }, box, 0), false, "the pane's own shape is drawn at once");
  assert.equal(holdFirst(true, { w: 1280, h: 720 }, box, 0), false, "a page already on the canvas is never held back by a resize");
  assert.equal(holdFirst(false, { w: 1280, h: 720 }, box, FIRST_WAIT), false, "and never for long: a browser that will not resize still draws");
  assert.equal(holdFirst(false, { w: 0, h: 0 }, box, 0), false, "a frame that does not say its size is drawn");
  assert.equal(activeTab({ type: "tabs", tabs: [{ active: false, url: "https://a.example/" }, { active: true, url: "https://b.example/code?x=1" }] }), "https://b.example/code?x=1");
  assert.equal(activeTab({ type: "tabs" }), "");
  const { readFileSync } = await import("node:fs");
  const pane = readFileSync(new URL("../src/BrowserPane.jsx", import.meta.url), "utf8");
  assert.match(pane, /late\.current = setTimeout\(\(\) => \{ if \(!img\.current\) show\(\); \}, FIRST_WAIT\)/, "a still page sends no second frame: the held one is drawn when the wait is over");
  assert.match(pane, /else if \(m\.type === "tabs"\) \{ const u = activeTab\(m\); if \(u\) setUrl\(u\);/);
});

// THE OWNER, 2026-11-15: "you can open multiple sites on same window with tabs" - the view lists the browser's tabs, each by its page's title
// (its host where the title is only an address), the one the agent works marked; a tab without agent-browser's id is not one to switch to
test("the browser's tabs read as a strip: title or host, the active one marked, only real tab ids", async () => {
  const { tabList } = await import("../src/browserSplit.js");
  const m = { type: "tabs", tabs: [
    { tabId: "t1", title: "Payworth - Sign in", url: "http://localhost:8931/login", active: false },
    { tabId: "t2", title: "127.0.0.1:8932", url: "http://127.0.0.1:8932/", active: true },
    { tabId: "t3", title: "", url: "https://news.example/today", active: false },
    { tabId: "x;rm", title: "bad", url: "https://bad.example/", active: false }] };
  assert.deepEqual(tabList(m), [
    { id: "t1", name: "Payworth - Sign in", url: "http://localhost:8931/login", active: false },
    { id: "t2", name: "127.0.0.1:8932", url: "http://127.0.0.1:8932/", active: true },
    { id: "t3", name: "news.example", url: "https://news.example/today", active: false }]);
  assert.deepEqual(tabList({ type: "tabs" }), []);
  // ...and a page keeps the title it once showed, where the browser names it in the background by its address (design round 5, 2026-11-19)
  tabList({ type: "tabs", tabs: [{ tabId: "t4", title: "PermitWatch - Sign up", url: "http://127.0.0.6:18791/s/permitwatch/", active: true }] });
  assert.equal(tabList({ type: "tabs", tabs: [{ tabId: "t4", title: "127.0.0.6:18791/s/permitwatch/", url: "http://127.0.0.6:18791/s/permitwatch/", active: false }] })[0].name,
    "PermitWatch - Sign up");
  const { readFileSync } = await import("node:fs");
  const pane = readFileSync(new URL("../src/BrowserPane.jsx", import.meta.url), "utf8");
  assert.match(pane, /tabs\.length > 1 &&/, "one tab draws no strip");
  assert.match(pane, /useState\(\(\) => TABS\.get\(sid\) \|\| \[\]\)/, "a view drawn again for a resize keeps its strip");
  assert.match(pane, /send\?\.\(\{ type: "tab", tab: t\.id \}\)/, "a press on a tab switches the browser to it, through the view's own socket");
});

// THE BROWSER AUDIT, 2026-11-15: a step handed over on the page drew "Answer the agent's question..." in the box - it was no question
test("the box says what waits on him: a sign-in, a step on the page, or a question", () => {
  assert.equal(askPlaceholder(null), "");
  assert.equal(askPlaceholder({ request_id: "signin:bank.example" }), "Message the agent - never your password");
  assert.equal(askPlaceholder({ request_id: `${TURN_PREFIX}ab12` }), "Your step is on the page - or tell the agent here…");
  assert.equal(askPlaceholder({ request_id: "q:1" }), "Answer the agent's question…");
});
