import { test } from "node:test";
import assert from "node:assert";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { LANES, LANE_META, ageText, arrivals, cardFor, departures, drawOrder, keysOf, laneMeta, statusLine, topAlert } from "../src/funnelPile.js";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");
const cardsSrc = () => read("assistantCards.jsx");

test("every lane the server knows has a word, a mark and a role the theme can colour", () => {
  assert.deepStrictEqual(LANES, ["blocked", "time", "approve", "asked", "forgotten", "report", "fyi", "working"]);
  for (const l of LANES) { assert.ok(LANE_META[l].word); assert.ok(LANE_META[l].mark); assert.ok("role" in LANE_META[l]); }
  // oxblood is spent on nothing but "this is on you": an agent waiting, a draft waiting for a yes
  assert.deepStrictEqual(LANES.filter((l) => LANE_META[l].role === "you"), ["blocked", "approve"]);
  assert.strictEqual(laneMeta("nonsense"), LANE_META.fyi);
});

test("the rail draws the server's next-first list as it comes: what comes out next is on top", () => {
  const items = [{ key: "a" }, { key: "b" }, { key: "c" }];
  assert.deepStrictEqual(drawOrder(items).map((i) => i.key), ["a", "b", "c"]);
  assert.notStrictEqual(drawOrder(items), items);   // a copy: the caller splices the current one out
  assert.deepStrictEqual(drawOrder(null), []);
});

test("an arrival is a key we have not drawn before - and the first paint is never an arrival", () => {
  const first = [{ key: "a" }, { key: "b" }];
  assert.deepStrictEqual([...arrivals(null, first)], []);
  const prev = keysOf(first);
  assert.deepStrictEqual([...arrivals(prev, [{ key: "b" }, { key: "z" }])], ["z"]);
  assert.deepStrictEqual([...arrivals(prev, first)], []);
  // ...and a departure is a key that was drawn and is gone - it falls out of the mouth
  assert.deepStrictEqual(departures(first, [{ key: "b" }]).map((i) => i.key), ["a"]);
  assert.deepStrictEqual(departures(null, first), []);
});

test("the card under a line is decided by kind, one card per kind", () => {
  assert.strictEqual(cardFor({ kind: "review" }), "reply");
  assert.strictEqual(cardFor({ kind: "action" }), "reply");
  assert.strictEqual(cardFor({ kind: "agent" }), "agent");
  assert.strictEqual(cardFor({ kind: "meeting" }), "meeting");
  assert.strictEqual(cardFor({ kind: "report" }), "report");
  assert.strictEqual(cardFor({ kind: "agentdone" }), "agentdone");
  assert.strictEqual(cardFor({ kind: "idea" }), "idea");
  assert.strictEqual(cardFor({ kind: "asked" }), "message");
  assert.strictEqual(cardFor({ kind: "fyi" }), "message");
  assert.strictEqual(cardFor({ kind: "triaging" }), null);
  assert.strictEqual(cardFor({ kind: "brief" }), "brief");
  assert.strictEqual(cardFor({ kind: "task" }), "task");
  assert.strictEqual(cardFor({ kind: "fyis" }), "fyis");
  assert.strictEqual(cardFor({ kind: "wrapup" }), "wrapup");
  assert.strictEqual(cardFor(null), null);
});

test("ages read as a person says them", () => {
  const now = new Date("2026-09-03T12:00:00").getTime();
  assert.strictEqual(ageText("2026-09-03 12:12:00", now), "in 12 min");
  assert.strictEqual(ageText("2026-09-03 14:30:00", now), "in 2h");
  assert.strictEqual(ageText("2026-09-03 11:59:30", now), "now");
  assert.strictEqual(ageText("2026-09-03 11:20:00", now), "40 min");
  assert.strictEqual(ageText("2026-09-03 08:00:00", now), "4h");
  assert.strictEqual(ageText("2026-08-30 08:00:00", now), "4d");
  assert.strictEqual(ageText("", now), "");
  assert.strictEqual(ageText("garbage", now), "");
});

test("the header line counts the pipe and what is on you", () => {
  assert.strictEqual(statusLine([], false), "All caught up");
  assert.strictEqual(statusLine([{ lane: "fyi" }, { lane: "approve" }, { lane: "blocked" }], false), "3 in the pipe · 2 on you");
  assert.strictEqual(statusLine([{ lane: "fyi" }], false), "1 in the pipe");
  assert.strictEqual(statusLine([{ lane: "fyi" }], true), "thinking…");
});

test("the by-the-way bar shows the first alert nobody has put down - and only what outranks the table", () => {
  const alerts = [{ key: "alert:a", item: "a", kind: "meeting", lane: "time", text: "Standup starts in 10 min" },
    { key: "alert:b", item: "b", kind: "agent", lane: "blocked", text: "codex asked you something" },
    { key: "alert:c", item: "c", kind: "review", lane: "approve", text: "Craig's reply is waiting for your yes" }];
  assert.strictEqual(topAlert(alerts, new Set()).key, "alert:a");
  assert.strictEqual(topAlert(alerts, new Set(["alert:a"])).key, "alert:b");
  assert.strictEqual(topAlert(alerts, new Set(["alert:a", "alert:b"])).key, "alert:c");   // nothing on the table: a draft is worth a word
  assert.strictEqual(topAlert(alerts.slice(2), new Set(), { key: "x", lane: "fyi" }).key, "alert:c");   // on an fyi: the draft outranks it
  assert.strictEqual(topAlert(alerts.slice(2), new Set(), { key: "x", lane: "approve" }), null);      // on another draft: it does not
  assert.strictEqual(topAlert(alerts.slice(2), new Set(), { key: "c", lane: "approve" }), null);      // it IS the one on the table
  assert.strictEqual(topAlert(alerts.slice(1, 2), new Set(), { key: "x", lane: "blocked" }).key, "alert:b");   // an agent always interrupts
  assert.strictEqual(topAlert(alerts, new Set(["alert:a", "alert:b", "alert:c"])), null);
  assert.strictEqual(topAlert(null, new Set()), null);
});

test("the Assistant page IS the Timeline: the landing tab, mid-strip wearing the mark, four tabs each side, the bubble off it", () => {
  const page = read("TaskHubPage.jsx");
  const tabs = page.match(/const TABS = \[([^\]]+)\]/)[1].split(",").map((t) => t.trim().replace(/"/g, ""));
  assert.strictEqual(tabs.indexOf("Assistant"), 4);
  assert.strictEqual(tabs.length, 9);                       // four to each side of it
  assert.ok(!tabs.includes("Timeline"));                    // the Timeline is the Assistant's rail now...
  assert.match(page, /if \(t === "Timeline"\) t = "Assistant"/);   // ...and old links to it still land
  assert.doesNotMatch(page, /<FeedView/);                   // the rail is mounted by the Assistant, nowhere else
  assert.match(page, /useState\("Assistant"\)/);
  assert.match(page, /tab !== "Assistant" && <FloatingAssistant/);
  assert.match(page, /t === "Assistant" \? \(/);
  assert.match(page, /<TaskuaryMark size=\{18\} \/>\{t\}/);
  const view = read("AssistantView.jsx");
  assert.match(view, /\/api\/funnel\/pile/);
  assert.match(view, /\/api\/concierge\/next/);
  assert.match(view, /All done/);
  assert.match(view, /By the way/);
  assert.doesNotMatch(view, /tq-pipe-walls/);             // no funnel: what comes out next is the FIRST row
  assert.match(view, /current: true \}\] : \[\]\), \.\.\.drawOrder/);   // what is on the table sits at the TOP as CURRENT
  // The pipe is still the top of the Timeline's own rail - but `top` is a FUNCTION now, because a
  // click on a pile row in task mode has to reach FeedView's stage, and an element could not be
  // handed the way to do it. A row with no message behind it (a meeting, a wrapup, an agent) has
  // nothing to open, so those still answer in the chat.
  assert.match(view, /<FeedView[^]*top=\{\(\{ openByMid \}\) => <Pile/);
  assert.match(view, /stageMode === "task" && it\?\.mid && openByMid/);
  assert.match(read("FeedView.jsx"), /typeof top === "function" \? top\(\{ openByMid \}\) : top/);
  // The rail's kind/source filters narrow the rail's OWN rows and nothing else: the pile and the
  // walk are asked for over everything, so the assistant processes the whole pipe whatever the
  // rail is showing (the owner, 2026-09-04: "how the assistant works on filtered tasks - does it
  // only process those?"). The one narrowing the walk takes is `only`, which is the "Just what
  // came in" button. If that ever changes, these two are where it has to be said out loud.
  assert.match(view, /\/api\/funnel\/pile", \{ params: currentRef\.current\?\.key \? \{ current: currentRef\.current\.key \} : \{\} \}/);
  assert.match(view, /\{ key: body\.key, only: body\.only \}/);
  assert.match(view, /stage=\{stageMode === "chat" \? chat : placeholder\} rowMode=\{stageMode\}/);   // the two ways to use the stage
  assert.match(view, /onPull=\{\(r\) => pull\(keyForRow\(r\)/);   // a Timeline row is pulled in by the pipe's own key
  assert.match(view, /window\.location\.hash = `msg=\$\{mid\}`/);   // "on the Timeline" pins the row over the chat
  assert.doesNotMatch(view, /turn\(\{ mode: "open" \}\)/);   // the day never writes itself: the welcome is the door
  assert.match(view, /if \(data\.decision\) await decide\(data\.decision\)/);   // words are carried out, never left as advice
  assert.match(view, /dispatch`, \{ instruction: d\.text \|\| null \}/);          // ...and a hand-off to the coder carries them
  assert.match(view, /triage moved it up/);                // the rail shows promotions
  assert.match(view, /data\.events\?\.length/);           // the watcher's lines land in the chat as they happen
  assert.match(cardsSrc(), /Show the final report/);        // ...and a finished job's report reads right there
  assert.match(cardsSrc(), /Run it again/);                 // a rerun is queued, never run in the chat
  assert.match(cardsSrc(), /Open walkthrough/);             // set-up opens the Assistant operator, not a coding checkout
  assert.match(view, /verb === "done" && cur && cur\.kind !== "agent"/);   // done on a task closes the task
  assert.match(read("FeedView.jsx"), /\/api\/ingest\/poll/);            // sync now, on the rail's header
  assert.match(view, /new ResizeObserver\(\(\) => \{ if \(el\.scrollHeight/);   // the chat keeps its bottom in view as it grows
  assert.doesNotMatch(view, /maxWidth: 1380/);             // the chat takes the width it has
  assert.match(cardsSrc(), /Just what came in/);           // ...which is what "mail" actually means: a person sent it
  assert.match(view, /Walk me through my tasks/);
  assert.match(cardsSrc(), /All read, next/);             // a handful of fyi's goes in one click
  assert.match(cardsSrc(), /<TerminalPane sid=\{card\.sid\}/);   // a stopped agent's own screen, in the chat
  assert.doesNotMatch(view, /left: side, right: side/);    // no taper: every row is a Timeline row's width
  assert.doesNotMatch(view, /<Drawer/);                    // no reader drawer: reading happens in the card
  const css = read("assistantView.css");
  assert.match(css, /\.tq-pile-row \{[^}]*grid-template-columns: 70px 14px minmax\(0, 1fr\)/);   // the Timeline row's gutter, rail and card
  assert.match(read("FeedView.jsx"), /const GUTTER = 70;/);
  assert.doesNotMatch(css, /tq-pipe-/);                    // the funnel's CSS is gone with it
  assert.doesNotMatch(view, /tq-pile-head/);               // no "The pipe · N" header over the rows (the owner, 2026-09-03)
  assert.match(view, /One more and the pipe is clear/);    // ...the count is the encouragement, at the bottom, from fifteen
  assert.match(read("FeedView.jsx"), /useState\(top \? "unread" : ""\)/);   // the rail opens on the pipe alone; "all" is the Timeline
  const feed = read("FeedView.jsx");
  assert.match(feed, /if \(narrow \|\| chatMode\) return;/);   // a chat is not a preview pane: no hover-open in chat mode
  assert.match(feed, /addEventListener\("hashchange", openHash\)/);   // a card's #msg= opens the row while the rail is already up
  const cards = read("assistantCards.jsx");
  // the two "not ours" doors the owner asked for: one that teaches memory, one that does not
  assert.match(cards, /not-mine/); assert.match(cards, /Not ours — remember it/); assert.match(cards, /Not ours, just this once/);
  assert.match(cards, /Approve & send/); assert.match(cards, /Prep me/);
  assert.match(cards, /SourceMark/); assert.match(cards, /ChannelIcon/);   // the logo of where it came from
  assert.match(cards, /On the Timeline/);                                   // every card links to the whole of it
  assert.match(read("SettingsView.jsx"), /funnel_hours/); assert.match(read("SettingsView.jsx"), /funnel_max/);
});

test("a few kinds say more than their lane does", async () => {
  const { rowMeta, laneMeta } = await import("../src/funnelPile.js");
  // an agent's finished job and a report you set up share the 'report' lane; they do not read alike
  assert.equal(rowMeta({ kind: "agentdone", lane: "report" }).word, "agent finished");
  assert.equal(rowMeta({ kind: "agentdone", lane: "report" }).role, "working");
  assert.equal(rowMeta({ kind: "wrapup", lane: "report" }).word, "close it?");
  assert.equal(rowMeta({ kind: "report", lane: "report" }).word, laneMeta("report").word);
  assert.equal(rowMeta({ kind: "fyi", lane: "fyi" }).word, "fyi");
  assert.equal(rowMeta(null).word, "fyi");
});
