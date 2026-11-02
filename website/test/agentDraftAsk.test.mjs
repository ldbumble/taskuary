import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { agentAsks, askWhere, draftKey, isAgentDraft } from "../src/agentDraftAsk.js";

// THE AGENT'S DRAFT IS ASKED WHERE THE AGENT IS (the owner, 2026-11-02): a pop-up over a CLI agent's terminal, a card under a general
// agent's chat - the agent's own pending draft only, one per draft, and Later puts one off. Invented people only.
const mine = { ReviewId: 7, Kind: "draft_reply", Status: "pending", DraftText: "Hi Erin - which week should the report cover?", DraftBy: "agent:Claude Code" };

test("only a pending draft the agent wrote is asked about", () => {
  assert.equal(isAgentDraft(mine), true);
  assert.equal(isAgentDraft({ ...mine, Kind: "clarification", DraftBy: "" }), true, "the agent's question to the sender");
  assert.equal(isAgentDraft({ ...mine, DraftBy: "responder" }), false, "triage's own draft stays in Close out");
  assert.equal(isAgentDraft({ ...mine, Status: "approved" }), false, "sent: gone from both places");
  assert.equal(isAgentDraft({ ...mine, DraftText: "  " }), false, "nothing to approve yet");
  assert.equal(isAgentDraft({ ...mine, Kind: "slot" }), false, "one of the task's emails is Close out's");
  assert.equal(isAgentDraft({ ...mine, Kind: "action" }), false);
});

test("one ask per pending agent draft; Later puts that draft off, and a new letter on it comes back", () => {
  const two = { ...mine, ReviewId: 8, DraftText: "Hi Gail - is Friday still on?" };
  const reviews = [{ ReviewId: 6, Kind: "draft", Status: "pending", DraftText: "Thanks", DraftBy: "" }, mine, two];
  assert.deepEqual(agentAsks(reviews).map((r) => r.ReviewId), [7, 8]);
  const off = new Set([draftKey(mine)]);
  assert.deepEqual(agentAsks(reviews, off).map((r) => r.ReviewId), [8], "Later hides that one only");
  assert.deepEqual(agentAsks([{ ...mine, DraftText: "Hi Erin - a second thought." }, two], off).map((r) => r.ReviewId), [7, 8],
    "the agent saved a new letter on the same review: asked again");
  assert.deepEqual(agentAsks(undefined), []);
});

test("a CLI agent's terminal gets the pop-up, a general agent's chat the card, nothing else either", () => {
  assert.equal(askWhere("live"), "popup");
  assert.equal(askWhere("general"), "chat");
  for (const m of ["wrapping", "", null, undefined]) assert.equal(askWhere(m), null);
});

test("the pop-up lies over the terminal, never beside it, and hands ReviewDecision Close out's own Send", () => {
  const pop = readFileSync(new URL("../src/AgentDraftAsk.jsx", import.meta.url), "utf8");
  assert.match(pop, /position: "absolute"/, "laid over the pane: the terminal keeps its size");
  assert.match(pop, /<ReviewDecision review=\{r\} \{\.\.\.decision\} compact/, "the card Close out draws, its props");
  assert.match(pop, /send: true/, "the Assistant is told its Send is an outward send");
  const page = readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");
  assert.match(page, /draftDecision = \{ closeout: closeoutRv, onMarkDone: askFinish, onSent: sent, closeOnSend: true, liveWork,/);
  assert.match(page, /<TerminalPane sid=\{term\.sid\}[^\n]*\n[^\n]*\n\s*\{askAt === "popup" && <AgentDraftPopup/, "inside the terminal's own box");
});
