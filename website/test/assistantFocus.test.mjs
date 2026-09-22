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

test("work nobody is on is the task, and it is on you", () => {
  const f = assistantFocus(item({ lane: "queued", agent: "codex" }));
  assert.equal(f.card, "task", "it used to be drawn as a message from a person");
  assert.match(f.lead, /on you/);
  assert.match(f.lead, /no agent is on it right now/);
});

test("the lead states NOW, and never names a worker it cannot vouch for", () => {
  // 'queued' covers a session that ran and died, so "codex has not started" was false on both halves
  for (const over of [{ lane: "queued", agent: "codex" }, { lane: "queued" }]) {
    const lead = assistantFocus(item(over)).lead;
    assert.doesNotMatch(lead, /codex/, lead);
    assert.doesNotMatch(lead, /has not started|was handed/, lead);
  }
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

// THE SAME EXCEPTION, ON THE OTHER SURFACE. funnelPile's own comment promises assistantFocus is
// "kept in the same precedence" as the task page's focusStage; these two assert it rather than
// hoping for it. Its twin lives in taskLifecycle.test.mjs.
test("an agent blocked on approval opens the thing it is waiting for", () => {
  const f = assistantFocus(item({ kind: "agent", lane: "blocked", request_kind: "approval_needed", rid: 9, agent: "codex" }));
  assert.equal(f.card, "reply");
  assert.match(f.lead, /runs only if you say so/);
});

test("an agent blocked on a question is still the agent card", () => {
  for (const parked of [{ asking: true }, { request_kind: "input_needed" }, { state: "stalled" }, {}]) {
    const f = assistantFocus(item({ kind: "agent", lane: "blocked", rid: 9, agent: "codex", ...parked }));
    assert.equal(f.card, "agent", `parked as ${JSON.stringify(parked)} is the agent's card`);
  }
});

test("an approval-blocked agent with nothing proposed is still the agent card", () => {
  const f = assistantFocus(item({ kind: "agent", lane: "blocked", request_kind: "approval_needed", agent: "codex" }));
  assert.equal(f.card, "agent", "no rid means there is no proposal to show");
});
