import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { agentAsks, alreadyAnswered, answeredLine, askWhere, autoPair, draftKey, isAgentDraft, noticeLine } from "../src/agentDraftAsk.js";

// THE AGENT'S DRAFT IS SAID WHERE THE AGENT IS AND SENT FROM CLOSE OUT (the owner, 2026-11-02: "in agent we should just say 'agent drafted a
// message' and take you to the Close out screen"), and a draft the owner already answered says so. Invented people only.
const mine = { ReviewId: 7, Kind: "draft_reply", Status: "pending", DraftText: "Hi Erin - which week should the report cover?", DraftBy: "agent:Claude Code",
  MessageId: 40, FromName: "Erin Blake", FromEmail: "erin@northwind.example" };

test("only a pending draft the agent wrote is said in the agent's pane", () => {
  assert.equal(isAgentDraft(mine), true);
  assert.equal(isAgentDraft({ ...mine, Kind: "clarification", DraftBy: "" }), true, "the agent's question to the sender");
  assert.equal(isAgentDraft({ ...mine, DraftBy: "responder" }), false, "Taskuary's own draft is Close out's alone");
  assert.equal(isAgentDraft({ ...mine, Status: "approved" }), false, "sent: the notice goes");
  assert.equal(isAgentDraft({ ...mine, Status: "no_reply" }), false, "dropped: the notice goes");
  assert.equal(isAgentDraft({ ...mine, DraftText: "  " }), false);
  assert.equal(isAgentDraft({ ...mine, Kind: "slot" }), false, "an email the task owes is Close out's");
  const two = { ...mine, ReviewId: 8 };
  assert.deepEqual(agentAsks([{ ReviewId: 6, Kind: "draft", Status: "pending", DraftText: "Thanks" }, mine, two]).map((r) => r.ReviewId), [7, 8], "one notice per draft");
  assert.deepEqual(agentAsks(undefined), []);
});

test("the notice names the agent and the person, never the address", () => {
  assert.equal(noticeLine(mine, "Taskuary"), "Claude Code drafted a message to Erin Blake");
  assert.equal(noticeLine({ ...mine, Kind: "clarification", DraftBy: "" }, "Taskuary"), "Taskuary drafted a question to Erin Blake");
  assert.equal(askWhere("live"), "popup");
  assert.equal(askWhere("general"), "chat");
  for (const m of ["wrapping", "", null, undefined]) assert.equal(askWhere(m), null);
});

test("already answered: a reply to that person newer than the message the draft answers - outside Taskuary or from here", () => {
  const against = { MessageId: 40, FromEmail: "erin@northwind.example", SentAt: "2026-11-02 09:00:00" };
  const outside = { at: "2026-11-02 09:30:00", text: "Hi Erin, the report covers the week of the 26th - all of it, night shift too.",
    msg: { RecipientsJson: JSON.stringify({ to: ["erin@northwind.example"] }) } };
  const a = alreadyAnswered({ draft: mine, sent: [outside], against });
  assert.equal(a.who, "Erin Blake");
  assert.equal(a.at, "2026-11-02 09:30:00");
  assert.ok(a.words.startsWith("Hi Erin, the report covers") && a.words.endsWith("...") && a.words.length < 70, a.words);
  assert.equal(answeredLine(a, () => "9:30 AM"), `You already answered Erin Blake at 9:30 AM: "${a.words}"`);
  const fromHere = { at: "2026-11-02 10:00:00", text: "Sent from Taskuary", review: { ReviewId: 3, FromEmail: "erin@northwind.example" } };
  assert.equal(alreadyAnswered({ draft: mine, sent: [outside, fromHere], against }).words, "Sent from Taskuary", "the newest one");
  // ...not: one older than the message the draft answers, one to someone else, the draft itself, or nothing at all
  assert.equal(alreadyAnswered({ draft: mine, sent: [{ ...outside, at: "2026-11-02 08:00:00" }], against }), null);
  assert.equal(alreadyAnswered({ draft: mine, sent: [{ ...outside, msg: { RecipientsJson: '["gail@northwind.example"]' } }], against }), null);
  assert.equal(alreadyAnswered({ draft: mine, sent: [{ ...fromHere, review: mine }], against }), null);
  assert.equal(alreadyAnswered({ draft: null, sent: [outside], against }), null);
  assert.equal(answeredLine(null), "");
});

test("the notice lies over the terminal and opens Close out; the draft is drawn in Close out alone, its answered line on it", () => {
  const notice = readFileSync(new URL("../src/AgentDraftNotice.jsx", import.meta.url), "utf8");
  assert.match(notice, /position: "absolute"/, "laid over the pane: the terminal keeps its size");
  assert.doesNotMatch(notice, /ReviewDecision|DraftField|textarea/, "no draft, no Send in the agent's pane");
  const page = readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");
  assert.match(page, /<TerminalPane sid=\{term\.sid\}[^\n]*\n[^\n]*\n\s*\{askAt === "popup" && noticeOn && <AgentDraftNotice asks=\{agentDrafts\} at="popup"/, "inside the terminal's own box");
  assert.match(page, /<ReviewDecision review=\{pendingReview\}[^\n]*\n[^\n]*answered=\{answeredYet\}/);
  assert.equal(page.match(/<ReviewDecision review=\{pendingReview\}/g).length, 1, "one card for the draft: Close out's");
});

test("the reply opens beside an agent once it stopped running, once per draft, never again once the owner closed it", () => {
  const at = { draft: mine, canPair: true };
  assert.equal(autoPair(at), true, "stopped or finished: Agent | Close out");
  // the owner, 2026-11-03: "every 10 seconds it opens the response tab ??? stop opening that until the agent stopped running"
  assert.equal(autoPair({ ...at, running: true }), false, "a live agent, working or waiting on you, is never squeezed - its notice's press pairs them");
  assert.equal(autoPair({ ...at, canPair: false }), false, "a work area too narrow for two halves: Close out on its own, as today");
  assert.equal(autoPair({ ...at, paired: true }), false);
  assert.equal(autoPair({ ...at, draft: null }), false);
  assert.equal(autoPair({ ...at, shut: new Set([draftKey(mine)]) }), false, "closed for this draft stays closed");
  assert.equal(autoPair({ ...at, shut: new Set([draftKey({ ...mine, DraftText: "older words" })]) }), true, "a new letter from the agent is a new draft");
  assert.equal(autoPair({ ...at, done: new Set([draftKey(mine)]) }), false, "once per draft - a view the page reads again is not a new one");
  // a running agent's re-reads, one every few seconds, its word flipping between working and waiting: it opens at most once, after it stops
  const done = new Set(), shut = new Set();
  const opened = [true, true, true, true, false, false, false].filter((running) => autoPair({ ...at, running, done, shut }) && done.add(draftKey(mine))).length;
  assert.equal(opened, 1);
  const page = readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");
  assert.match(page, /autoPair\(\{ draft: agentDraft, running: \(liveSession && !answered\) \|\| !!liveRun,/, "running: a live session (not a general chat that answered) or a run - not the working word");
  assert.match(page, /^const PAIR_DONE = new Set\(\), PAIR_SHUT = new Set\(\);/m, "held for the app's life, not a page drawn again");
  assert.match(page, /const canPair = pairRoom && \(!liveSession \|\| !!agentDraft \|\| \(pairPick\.key === pickKey && !!pairPick\.draft\)\)/,
    "side by side over a live agent only for its draft, and kept once it is sent");
});

// AN EARLIER SESSION'S DRAFT IS NOT THE REPLY (the owner, 2026-11-03: "when you continue on general agent it shows the prior reply on bottom
// that the agent generated. Don't show that reply if it was based off another general session not the latest one")
test("a draft an earlier agent session wrote is not drawn while a newer session is live", async () => {
  const { latestDrafts, earlierSession } = await import("../src/agentDraftAsk.js");
  const old = { ...mine, DraftSid: "s-old" }, owned = { ...mine, ReviewId: 9, DraftSid: "owner" }, legacy = { ...mine, ReviewId: 10, DraftSid: null };
  assert.equal(earlierSession(old, "s-new"), true, "Continue opened a new session: the old one's words wait");
  assert.equal(earlierSession(old, "s-old"), false, "the same session, a new turn: still its latest");
  assert.equal(earlierSession(old, ""), false, "no session live: the draft is the task's, in Close out as ever");
  assert.equal(earlierSession(owned, "s-new"), false, "the owner edited it: theirs");
  assert.equal(earlierSession(legacy, "s-new"), false, "one written before drafts knew their session is the server's call (held there)");
  assert.equal(earlierSession({ ...old, DraftBy: "" }, "s-new"), false, "Taskuary's own draft belongs to no agent session");
  assert.equal(earlierSession({ ...old, Status: "approved" }, "s-new"), false, "what went is history, never hidden");
  const fresh = { ...mine, ReviewId: 11, DraftSid: "s-new" };
  assert.deepEqual(latestDrafts([old, fresh, owned], "s-new").map((r) => r.ReviewId), [11, 9]);
  assert.equal(agentAsks(latestDrafts([old], "s-new")).length, 0, "no 'drafted a message' notice for it");
  const page = readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");
  assert.match(page, /reviews = latestDrafts\(roundReviews\(allReviews, rounds\), liveSession \? term\.sid : ""\)/,
    "the page's reply, its notice, Send and Mark done all read the reviews with it left out");
});
