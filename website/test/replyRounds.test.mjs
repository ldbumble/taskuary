import test from "node:test";
import assert from "node:assert/strict";
import { replyRounds as closeoutRounds, roundReviews } from "../src/replyRounds.js";

// CLOSE OUT IN ROUNDS (the owner, 2026-11-01): a reply, a close, new mail that reopened it - the new mail is the current round, with no
// "Sent" of its own, and the old round is under it. Invented people.
const ms = (s) => Date.parse(String(s).replace(" ", "T")) || 0;
const erin = (id, at, body) => ({ MessageId: id, Direction: "in", Status: "routed", FromName: "Erin Blake", SentAt: at, BodyText: body });
const sent = (id, mid, at, text) => ({ ReviewId: id, MessageId: mid, Kind: "reply", Status: "approved", DecidedAt: at, FinalText: text, FromName: "Erin Blake" });
const world = () => ({
  messages: [erin(1, "2026-10-30 09:00:00", "Some accounts are missing."), erin(2, "2026-10-31 09:00:00", "Which of them moved?")],
  reviews: [sent(11, 1, "2026-10-30 12:36:00", "They were folded into 4100.")],
  closeouts: [{ what: "closed", at: "2026-10-30 12:36:01", to: "done", note: "" }, { what: "reopened", at: "2026-10-31 09:00:05" }],
  ms,
});

test("reopened by new mail: the new message is the current round, unanswered, and the reply that closed the last one is its round's", () => {
  const rounds = closeoutRounds(world());
  assert.equal(rounds.length, 2);
  const [old, now] = rounds;
  assert.equal(now.answering.MessageId, 2);
  assert.deepEqual([now.sent, now.close], [[], null], "nothing sent yet in the current round");
  assert.equal(old.answering.MessageId, 1);
  assert.equal(old.sent[0].review.ReviewId, 11);
  assert.equal(old.close.to, "done");
  assert.deepEqual(roundReviews(world().reviews, rounds), [], "the old reply is not the current round's");
});

test("a second reply is the current round's sent reply, never the older one", () => {
  const w = world();
  w.reviews = [sent(12, 2, "2026-10-31 10:00:00", "4101 and 4102 moved."), ...w.reviews, { ReviewId: 13, Kind: "action", Status: "pending" }];
  w.closeouts.push({ what: "closed", at: "2026-10-31 10:00:01", to: "done", note: "" });
  const rounds = closeoutRounds({ ...w, open: false });
  assert.equal(rounds.length, 2);
  assert.equal(rounds[1].sent[0].text, "4101 and 4102 moved.");
  assert.deepEqual(roundReviews(w.reviews, rounds).map((r) => r.ReviewId), [12, 13], "its own reply and the proposal waiting");
});

test("answered outside Taskuary counts as the round's reply; a close with a note and one with nothing are said apart", () => {
  const w = world();
  w.outside = [{ MessageId: 9, Direction: "out", SentAt: "2026-10-31 11:00:00", OwnText: "Two of them, details tomorrow.", SourceName: "Outlook" }];
  w.closeouts.push({ what: "closed", at: "2026-10-31 11:05:00", to: "done", note: "" }, { what: "reopened", at: "2026-10-31 12:00:00" },
    { what: "closed", at: "2026-10-31 12:01:00", to: "done", note: "called her instead" });
  const rounds = closeoutRounds({ ...w, open: false });
  assert.equal(rounds.length, 3);
  assert.equal(rounds[1].sent[0].msg?.SourceName, "Outlook", "answered outside: the round's reply is the owner's own message");
  assert.equal(rounds[2].close?.note, "called her instead");
});

test("a Reopen drawn before the server says so is a new round; a draft closed unsent stays with the round it was closed in", () => {
  const w = world();
  w.messages = w.messages.slice(0, 1); w.closeouts = w.closeouts.slice(0, 1);
  w.reviews = [{ ReviewId: 14, MessageId: 1, Kind: "reply", Status: "superseded", DecidedAt: "2026-10-30 12:36:01", DraftText: "A second thought." }, ...w.reviews];
  const rounds = closeoutRounds({ ...w, open: true });
  assert.equal(rounds.length, 2);
  assert.deepEqual(rounds[0].unsent.map((r) => r.ReviewId), [14]);
  assert.deepEqual([rounds[1].ins, rounds[1].sent], [[], []]);
  assert.deepEqual(roundReviews(w.reviews, rounds), []);
});

test("a task answered twice in one open thread: their reply after yours starts the next round", () => {
  const w = world();
  w.closeouts = [];
  const rounds = closeoutRounds(w);
  assert.equal(rounds.length, 2);
  assert.equal(rounds[1].answering.MessageId, 2);
});

test("a sender's clock set ahead does not put their message after the reply that answered it", () => {
  const w = world();
  w.messages[1] = { ...w.messages[1], SentAt: "2026-10-31 18:00:00", CreatedAt: "2026-10-31 09:00:00" };
  w.reviews = [sent(12, 2, "2026-10-31 10:00:00", "4101 and 4102 moved."), ...w.reviews];
  const rounds = closeoutRounds(w);
  assert.equal(rounds.length, 2);
  assert.deepEqual([rounds[1].answering.MessageId, rounds[1].sent[0].review.ReviewId], [2, 12]);
});

test("one round on a task never closed or answered", () => {
  const rounds = closeoutRounds({ messages: [erin(1, "2026-10-30 09:00:00", "Hi")], ms });
  assert.equal(rounds.length, 1);
  assert.equal(rounds[0].n, 1);
});
