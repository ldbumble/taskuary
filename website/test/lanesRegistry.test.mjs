// ONE LANES REGISTRY: every count, section and kind word the page says is built from taskuary/lanes.json - the server builds the
// same tables from the same file (tests/test_lanes_registry.py), so a rule changed there changes on both sides at once.
import { readFileSync } from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";
import vocab from "../../taskuary/lanes.json" with { type: "json" };
import { IDEA, KIND, LEVEL_META, LEVEL_ORDER, SECTION_WORDS, attentionBand, ideaCounted, ideaWord, isAgentKind, isMail, kindSays, levelOf, onYou, toRead, waitsOnYou } from "../src/lanes.js";
import { statusLine, waitedText } from "../src/funnelPile.js";
import { needsYou, zoneOf } from "../src/assistantGame.js";
import { summarize } from "../src/walkSummary.js";

const src = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

test("the sections, their order, headings and hints are lanes.json's", () => {
  assert.deepEqual(LEVEL_ORDER, vocab.sections.map((s) => s.key));
  for (const s of vocab.sections) {
    assert.equal(SECTION_WORDS[s.key], s.word);
    assert.equal(LEVEL_META[s.key].word, s.word.toLowerCase());
    assert.ok(!LEVEL_META[s.key].hint.includes("{"), `${s.key}'s hint kept a placeholder`);
  }
});

test("a row with no band lands where its lane's entry says, every lane", () => {
  for (const l of vocab.lanes) {
    assert.ok(vocab.sections.some((s) => s.key === l.section), `${l.key} names no section`);
    assert.equal(typeof l.on_you, "boolean", `${l.key} does not say whether it is on you`);
    assert.equal(levelOf({ lane: l.key }), l.section, l.key);
  }
  // settled: an unjudged row is FYI while the retry may still judge it (the server's rule), the owner's once it gave up
  assert.equal(levelOf({ lane: "unjudged" }), "fyi");
  assert.equal(levelOf({ lane: "unjudged", held: true }), "task");
  // ...and an ask triage called urgent is Urgent here as on the server
  assert.equal(attentionBand({ lane: "asked", urgent_request: true }), 1);
  assert.equal(attentionBand({ lane: "report", urgent_request: true }), 3);
});

test("on you is one answer: the header, the opener's sections, the game's red count", () => {
  const pile = [
    { key: "a", lane: "asked", order_band: 2 }, { key: "y", lane: "yours", order_band: 2 }, { key: "b", lane: "blocked", order_band: 2 },
    { key: "t", lane: "theirs", order_band: 2 }, { key: "l", lane: "yours", order_band: 2, put_down: true },
    { key: "f", lane: "fyi", order_band: 4 }, { key: "r", lane: "report", order_band: 3 }, { key: "w", lane: "working", order_band: 5 },
    { key: "m", lane: "time", order_band: 1 }, { key: "s", lane: "asked", order_band: 2, settling: true },
  ];
  const you = pile.filter((i) => onYou(i)).map((i) => i.key);
  assert.deepEqual(you, ["a", "y", "b", "m"], "waiting on them, For later, reading, an agent at work and a settling row are not on you");
  assert.equal(statusLine(pile), `${pile.length} in the pipe · 4 on you`, "the header leaves out the lane worded 'on you'");
  assert.deepEqual(pile.filter(needsYou).map((i) => i.key), you);
  const groups = summarize(pile).groups;
  assert.equal(groups.reduce((n, g) => n + g.you, 0), 4, "the opener's headline counts a different set");
  assert.deepEqual(pile.filter((i) => toRead(i)).map((i) => i.key), ["f", "r"]);
  assert.ok(waitsOnYou({ lane: "blocked" }) && waitsOnYou({ lane: "approve" }) && !waitsOnYou({ lane: "yours" }));
  assert.equal(waitedText({ lane: "theirs", order_band: 2, since: "2020-01-01 00:00:00" }), "");
  assert.match(waitedText({ lane: "stopped", order_band: 2, since: "2020-01-01 00:00:00" }), /^waiting /);
});

test("every kind of row is counted, filed as mail and placed by lanes.json's item_kinds", () => {
  for (const [k, v] of Object.entries(KIND)) {
    assert.equal(kindSays(k, 1), `1 ${v.one}`); assert.equal(kindSays(k, 2), `2 ${v.many}`);
    assert.equal(isMail({ kind: k }), !!v.mail); assert.equal(isAgentKind(k), !!v.agent);
  }
  assert.equal(kindSays("goal_slipped", 1), "1 goal that slipped");
  assert.equal(kindSays("nonsense", 3), "3 other things", "an internal name never reaches a sentence");
  // the game: an agent's own news at its desk, a finished task in the gym, mail an agent drafted at the meeting table
  assert.equal(zoneOf({ kind: "wrapup", lane: "report" }), "floor");
  assert.equal(zoneOf({ kind: "agentdone", lane: "report" }), "gym");
  assert.equal(zoneOf({ kind: "action", lane: "approve" }), "meeting");
});

test("an Advisor line's kind has one word on its card, its Timeline row and its report", () => {
  for (const [k, v] of Object.entries(IDEA)) { assert.equal(ideaWord(k), v.word); assert.equal(ideaCounted(k), v.counted); }
  assert.equal(ideaWord("followup"), "waiting on them");
  assert.equal(ideaWord(undefined), "advisor idea", "an unnamed kind is an Advisor idea, not a slip nobody saw");
});

test("no copy of a lanes.json table is left in the page", () => {
  assert.doesNotMatch(src("funnelPile.js"), /const BAND = \{|LEVEL_OF_BAND = \{|const OWED = /);
  assert.doesNotMatch(src("assistantGame.js"), /const ON_YOU = |const AGENT_KINDS = /);
  assert.doesNotMatch(src("assistantCards.jsx"), /g\.key === "urgent" \|\| g\.key === "task"|followup: "waiting on them"/);
  assert.doesNotMatch(src("FeedView.jsx"), /const IDEA_KIND = /);
  assert.doesNotMatch(src("ReportsView.jsx"), /const IDEA_KINDS = /);
  assert.doesNotMatch(src("walkSummary.js"), /\["agent", "agentdone", "action"\]/);
  assert.doesNotMatch(src("demoAssistantData.js"), /\["blocked", "approve", "asked"\]/);
});

// A STATE'S WORD IS WRITTEN ONCE (the cleanup round, 2026-10-18): "agent working", "ready to send", "waiting to start" lived in
// lanes.json, in taskLifecycle's AGENT, in ui.jsx's TASK_STATES, in theme.jsx and in the demo's pile - and the demo still said
// "reply pending" for the lane the live app calls "ready to send". The page reads them from lanes.js WORD; no page file types one.
test("every state word the page says is read from lanes.json, never typed in a page file", async () => {
  const { WORD } = await import("../src/lanes.js");
  const { AGENT, READY } = await import("../src/taskLifecycle.js");
  for (const g of ["lanes", "kinds", "states"]) for (const r of vocab[g]) assert.equal(WORD[r.key], r.word, r.key);
  assert.deepEqual(AGENT, { waiting: WORD.blocked, working: WORD.working, saved: WORD.saved, stopped: WORD.stopped, finished: WORD.agentdone, idle: WORD.queued });
  assert.equal(READY, WORD.approve);
  // the words a sentence could not say by accident: two words or more ("done", "report" and "fyi" are ordinary English too)
  const words = new Set(Object.values(WORD).filter((w) => /\s/.test(w)));
  const fs = await import("node:fs");
  const files = fs.readdirSync(new URL("../src/", import.meta.url)).filter((f) => /\.(jsx?|mjs)$/.test(f));
  const literals = (code) => [...code.replace(/(^|\s)\/\/[^\n]*/g, "$1").matchAll(/"((?:[^"\\n]|\.)*)"|'((?:[^'\\n]|\.)*)'/g)].map((m) => m[1] ?? m[2]);
  const hits = files.flatMap((f) => literals(src(f)).filter((s) => words.has(s)).map((s) => `${f}: "${s}"`));
  assert.deepEqual(hits, []);
});
