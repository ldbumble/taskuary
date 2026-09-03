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

test("the column draws the server's next-first list upside down, mouth at the bottom", () => {
  const items = [{ key: "a" }, { key: "b" }, { key: "c" }];
  assert.deepStrictEqual(drawOrder(items).map((i) => i.key), ["c", "b", "a"]);
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

test("the Assistant page is the landing tab, sits mid-strip wearing the mark, and the bubble stays off it", () => {
  const page = read("TaskHubPage.jsx");
  const tabs = page.match(/const TABS = \[([^\]]+)\]/)[1].split(",").map((t) => t.trim().replace(/"/g, ""));
  assert.strictEqual(tabs.indexOf("Assistant"), 4);
  assert.match(page, /useState\("Assistant"\)/);
  assert.match(page, /tab !== "Assistant" && <FloatingAssistant/);
  assert.match(page, /t === "Assistant" \? \(/);
  assert.match(page, /<TaskuaryMark size=\{18\} \/>\{t\}/);
  const view = read("AssistantView.jsx");
  assert.match(view, /\/api\/funnel\/pile/);
  assert.match(view, /\/api\/concierge\/next/);
  assert.match(view, /All done/);
  assert.match(view, /By the way/);
  assert.match(view, /tq-pipe-walls/);                    // the funnel's shape
  assert.match(view, /current: true/);                    // ...and what is on the table sits at the mouth as CURRENT
  assert.match(view, /tq-pipe-day/);                      // the day, at the bottom, like the Timeline's label
  assert.doesNotMatch(view, /turn\(\{ mode: "open" \}\)/);   // the day never writes itself: the welcome is the door
  assert.match(view, /if \(data\.decision\) await decide\(data\.decision\)/);   // words are carried out, never left as advice
  assert.match(view, /dispatch`, \{ instruction: d\.text \|\| null \}/);          // ...and a hand-off to the coder carries them
  assert.match(view, /triage moved it up/);                // the rail shows promotions
  assert.match(view, /data\.events\?\.length/);           // the watcher's lines land in the chat as they happen
  assert.match(cardsSrc(), /Show the final report/);        // ...and a finished job's report reads right there
  assert.match(cardsSrc(), /Run it again/);                 // a rerun is queued, never run in the chat
  assert.match(cardsSrc(), /Open walkthrough/);             // set-up opens the Assistant operator, not a coding checkout
  assert.match(view, /verb === "done" && cur && cur\.kind !== "agent"/);   // done on a task closes the task
  assert.match(view, /\/api\/ingest\/poll/);                             // sync now, on the pipe
  assert.match(view, /new ResizeObserver\(\(\) => \{ if \(el\.scrollHeight/);   // the chat keeps its bottom in view as it grows
  assert.doesNotMatch(view, /maxWidth: 1380/);             // the chat takes the width it has
  assert.match(cardsSrc(), /Just what came in/);           // ...which is what "mail" actually means: a person sent it
  assert.match(view, /Walk me through my tasks/);
  assert.match(cardsSrc(), /All read, next/);             // a handful of fyi's goes in one click
  assert.match(cardsSrc(), /<TerminalPane sid=\{card\.sid\}/);   // a stopped agent's own screen, in the chat
  assert.match(view, /left: side, right: side/);           // the rows meet the funnel's walls, measured
  assert.doesNotMatch(view, /<Drawer/);                    // no reader drawer: reading happens in the card
  assert.match(read("assistantView.css"), /\.tq-pipe-stack \{ margin-top: auto; \}/);   // gravity
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
