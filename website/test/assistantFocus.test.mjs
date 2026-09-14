// The assistant's answer to the task page's focusStage: what the item is asking of you decides the
// card AND the words above it. Kind alone used to decide, so a task handed to an agent that never
// started fell through to "a person wrote something" (the owner, 2026-09-14).
import test from "node:test";
import assert from "node:assert/strict";
import { assistantFocus, cardFor } from "../src/funnelPile.js";

const item = (over) => ({ kind: "todo", lane: "asked", tid: 7, ...over });

test("a draft waiting for a yes outranks everything and says so", () => {
  const f = assistantFocus(item({ kind: "review", lane: "approve", rid: 3 }));
  assert.equal(f.card, "reply");
  assert.match(f.lead, /waiting for your yes/);
  assert.match(f.lead, /read what they asked/);          // you must see what you are answering
});

test("a proposed action is a reply card with its own words", () => {
  const f = assistantFocus(item({ kind: "action", lane: "approve", rid: 4 }));
  assert.equal(f.card, "reply");
  assert.match(f.lead, /runs only if you say so/);
});

test("an agent that stopped is the agent card and names who is waiting", () => {
  const f = assistantFocus(item({ kind: "agent", lane: "blocked", agent: "codex" }));
  assert.equal(f.card, "agent");
  assert.equal(f.lead, "codex stopped and is waiting on you.");
});

test("work handed over and never started is the task, and it is on you", () => {
  const f = assistantFocus(item({ lane: "queued", agent: "codex" }));
  assert.equal(f.card, "task", "it used to be drawn as a message from a person");
  assert.match(f.lead, /on you/);
  assert.match(f.lead, /codex was handed it and has not started/);
});

test("...and with nobody named it still says the work is unstarted", () => {
  assert.match(assistantFocus(item({ lane: "queued" })).lead, /handed over and has not started/);
});

test("a live agent is the agent card - reachable only on what is already in front of you", () => {
  // the walk never OFFERS a working item (funnel_selection._eligible drops lane 'working'); an item
  // on the table can become working while it is read, and then it is the agent's card
  const f = assistantFocus(item({ lane: "working", working: "codex" }));
  assert.equal(f.card, "agent");
  assert.match(f.lead, /nothing for you here yet/);
});

test("everything else keeps the card its kind has always chosen", () => {
  for (const [kind, card] of [["report", "report"], ["fyis", "fyis"], ["meeting", "meeting"],
                              ["idea", "idea"], ["agentdone", "agentdone"], ["wrapup", "wrapup"],
                              ["brief", "brief"], ["task", "task"]]) {
    assert.equal(assistantFocus(item({ kind, lane: "report" })).card, card, kind);
  }
  assert.equal(assistantFocus(item({ kind: "fyi", lane: "fyi" })).card, "message");
  assert.equal(assistantFocus(item({ kind: "asked", lane: "asked" })).card, "message");
});

test("the reports and the fyi batch are untouched by the focus rule", () => {
  assert.equal(cardFor({ kind: "report", lane: "report", mid: 1 }), "report");
  assert.equal(cardFor({ kind: "fyis", lane: "fyi", items: [1, 2, 3, 4] }), "fyis");
});

test("cardFor is the same table, so the two can never disagree", () => {
  for (const over of [{ kind: "review", lane: "approve" }, { lane: "queued" }, { lane: "blocked" },
                      { kind: "report", lane: "report" }, { kind: "fyi", lane: "fyi" }]) {
    assert.equal(cardFor(item(over)), assistantFocus(item(over)).card);
  }
  assert.equal(cardFor(null), null);
});
