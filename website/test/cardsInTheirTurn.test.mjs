// THE SPINE AUDIT, 2026-11-09: a card did not stay in the turn that raised it, and one waiting act drew two cards. Everything that waited - a
// held step, a browser act, a drafted playbook - rode one block under whichever turn was newest; a held act and a playbook stood again at the
// chat's foot with a second Approve; and a pressed card was placed by reading an answer's stamp as when its turn BEGAN, which on a general chat
// is when it ended. The server names each card's turn now (tests/test_cards_stand_in_their_turn.py); the page draws each once, there.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { placeCards, turnOf } from "../src/agentSummary.js";
import { askNote } from "../src/reviewProposal.js";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
// a general chat: asked at 09:00 and answered at 09:02, asked again at 11:00 and answered at 11:01 - each answer stamped when its turn ENDED
const chat = [{ id: "comment-1", role: "user", createdAt: "2026-11-05 09:00:00" }, { id: "comment-2", role: "assistant", createdAt: "2026-11-05 09:02:00" },
  { id: "comment-3", role: "user", createdAt: "2026-11-05 11:00:00" }, { id: "comment-4", role: "assistant", createdAt: "2026-11-05 11:01:00" }];
const after = (cards, turns, messages = chat) => placeCards(cards, messages, turns).map((c) => c.after);

test("in a general chat a card stands in the turn the server names, never the one its stamp falls after", () => {
  const cards = [{ key: "held:7", rid: 7, at: "2026-11-05 09:01:00" }, { key: "held:8", rid: 8, at: "2026-11-05 11:00:30", waits: true }];
  assert.deepEqual(cards.map((c) => turnOf(chat, c.at)), ["comment-4", "comment-2"], "read as begin-stamps both stood in the wrong turn");
  assert.deepEqual(after(cards, { 7: "comment-2", 8: "comment-4" }), ["comment-2", "comment-4"]);
  assert.equal(placeCards(cards, chat, { 7: "comment-2", 8: "comment-4" })[1].waits, true, "the card is handed on whole");
});

// ...NEVER AT THE FOOT (the owner, 2026-11-10: "approve should be there then once that's done it shoudl continue after it not above it.. it's
// just a row in the chat"): a card no answer has followed was raised by the turn at work - the newest - and stands in it
test("a card no answer has followed stands in the newest turn, and moves into the turn that answers", () => {
  const card = [{ key: "rv9", rid: 9, at: "2026-11-05 11:05:00", waits: true }], newest = chat.filter((m) => m.role === "assistant").at(-1).id;
  assert.deepEqual(after(card, { 9: null }), [newest]);
  assert.deepEqual(after(card, {}), [newest], "never the foot");
  const answered = [...chat, { id: "comment-6", role: "assistant", createdAt: "2026-11-05 11:06:00" }];
  assert.deepEqual(after(card, { 9: "comment-6" }, answered), ["comment-6"]);
});

test("a coding chat names no turns - its own are stamped as they begin - and an answer the thread does not draw is no place to stand", () => {
  const coding = [{ id: "run-1", role: "assistant", createdAt: "2026-11-05 09:00:00" }, { id: "run-2", role: "assistant", createdAt: "2026-11-05 11:00:00" }];
  assert.deepEqual(after([{ key: "held:7", rid: 7, at: "2026-11-05 09:01:00" }, { key: "held:8", rid: 8, at: "2026-11-05 11:00:30" }], null, coding), ["run-1", "run-2"]);
  assert.deepEqual(after([{ key: "sent:3", rid: 3, at: "2026-11-05 09:01:00" }], { 3: "comment-99" }), ["comment-4"], "as it was placed before");
  assert.deepEqual(after([{ key: "land", at: "2026-11-05 09:01:00" }], { 3: "comment-2" }), ["comment-4"], "a card of no review is placed by its time");
});

test("the task page hands every waiting ask to its turn, and draws it in its own block only where there are no turns", () => {
  const page = read("TaskPage.jsx");
  assert.match(page, /const inTurns = !solo && !\["done", "dropped"\]\.includes\(t\?\.Status\)/);
  assert.match(page, /\.\.\.\(inTurns \? askCards : \[\]\)\.map\(\(g\) => \(\{ key: g\.key, at: g\.reviews\[0\]\.CreatedAt \|\| "", rid: g\.reviews\[0\]\.ReviewId, waits: true, also: asksBelow, note: g\.held \? "" : askNote\(g\.reviews\[0\]\),/);
  assert.match(page, /\{!inTurns && askCards\.length > 0 && \(/);
  // ...and the block is not drawn for them: a chat whose only ask stands in its turn has no "Next steps" over nothing
  assert.match(page, /const waits = !!\(pendingReview \|\| moreDrafts\.length \|\| proposals\.length - \(inTurns \? asks\.length : 0\) \|\| owesEmails \|\| handoff\);/);
  assert.match(page, /\(waits \|\| \(!inTurns && kept\.length\) \|\| upFailed/);
  for (const k of ["pressedCards.map((g) => ({ key: g.key, at: g.at, rid: g.reviews[0].ReviewId,", 'at: r.CreatedAt || "", rid: r.ReviewId, node: <SentCard'])
    assert.ok(page.includes(k), "a pressed card names its review too");
});

test("the chat draws a waiting card once, in its turn - the foot's \"Waiting on you\" box is gone", () => {
  const gw = read("GeneralWorkspace.jsx");
  assert.match(gw, /mine = React\.useContext\(TurnCardsCtx\)\.filter\(\(c\) => c\.after === id\), pressed = mine\.filter\(\(c\) => !c\.waits\)/);
  assert.match(gw, /<TurnAsks cards=\{mine\.filter\(\(c\) => c\.waits\)\} also=\{holds && !!next && mine\.some\(\(c\) => c\.also\)\} \/>/);
  assert.equal((gw.match(/<TurnAsks /g) || []).length, 1, "drawn in a turn only - no box of its own at the chat's foot");
  assert.match(gw, /\{!dock && placed\.filter\(\(c\) => !c\.after\)\.map\(/, "only a chat with no agent turn at all draws a card under it, as its one row");
  assert.match(gw, /\{!dock && !turnCards && !!drafts\?\.length && \(/); assert.match(gw, /\{!dock && !turnCards && !!acts\?\.length && \(/);
  assert.match(gw, /turns=\{coding \? null : data\?\.turns\}/);
  // ...under the words the block said, counted per turn, and marked for the agent room's rest (TaskPage's :has([data-tq-waits]))
  const asks = gw.slice(gw.indexOf("const TurnAsks = "), gw.indexOf("const TurnAsks = ") + 900);
  assert.match(asks, /<Box data-tq-turn-asks="" data-tq-waits=""/);
  assert.match(asks, /\$\{also \? "Also waiting on you" : "Waiting on you"\}\$\{cards\.length > 1 \? ` · \$\{cards\.length\}` : ""\}/);
});

test("what the foot's boxes said over a held act and a playbook is said over its one card", () => {
  const act = (p) => ({ Kind: "action", Status: "pending", DraftText: JSON.stringify(p) });
  assert.match(askNote(act({ action: "browser_act", what: "Press Renew", url: "https://portal.vendor.example/renew" })), /^The agent's browser waits for your yes\./);
  assert.match(askNote(act({ action: "amend_playbook", name: "Renewals", text: "# Renewals" })), /^Approve saves this playbook to Reports → Playbooks/);
  assert.equal(askNote(act({ action: "close_task", why: "the folder is clear" })), "", "a card that says itself gets no line over it");
});

// A TURN THAT GOES ON PAST ITS CARD IS TWO ROWS, THE CARD BETWEEN (the owner, 2026-11-10: "it should continue after it not above it"): an ACP
// turn an Approve lets carry on draws what it did next under the card, never over it
test("a coding turn that goes on past a card is split at the card, so its next steps stand under it", async () => {
  const { chatRows, rowMessages } = await import("../src/chatStream.js");
  const ups = [{ sessionUpdate: "agent_message_chunk", content: { type: "text", text: "Committing." }, _at: "2026-11-10 12:00:01" },
    { sessionUpdate: "tool_call", toolCallId: "m", kind: "execute", title: "Merge newest master; list conflicts", status: "in_progress", _at: "2026-11-10 12:00:09" }];
  const ses = [{ sid: "s", source: "acp", live: true, at: "2026-11-10 12:00:00", updates: ups }];
  assert.equal(chatRows({ sessions: ses }).filter((r) => r.kind === "turn").length, 1, "no card: one turn");
  const rows = chatRows({ sessions: ses, cuts: ["2026-11-10 12:00:05"] }).filter((r) => r.kind === "turn");
  assert.equal(rows.length, 2);
  const msgs = rowMessages(rows);
  assert.deepEqual(after([{ key: "held:7", rid: 7, at: "2026-11-10 12:00:05", waits: true }], null, msgs), [msgs[0].id], "the card stands after the part before it");
});
