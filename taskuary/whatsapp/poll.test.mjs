import test from "node:test";
import assert from "node:assert/strict";
import crypto from "node:crypto";
import { aesEncryptGCM, hmacSign, proto } from "@whiskeysockets/baileys";
import { createPolls, pollValues, MAX_OPTIONS } from "./poll.mjs";

// a vote as WhatsApp encrypts it (the inverse of Baileys' decryptPollVote)
function encVote({ creator, voter, pollId, secret, option }) {
  const sign = Buffer.concat([Buffer.from(pollId), Buffer.from(creator), Buffer.from(voter), Buffer.from("Poll Vote"), new Uint8Array([1])]);
  const key = hmacSign(sign, hmacSign(secret, new Uint8Array(32), "sha256"), "sha256");
  const iv = crypto.randomBytes(12);
  const plain = proto.Message.PollVoteMessage.encode({ selectedOptions: option ? [crypto.createHash("sha256").update(option).digest()] : [] }).finish();
  return { encPayload: aesEncryptGCM(plain, key, iv, Buffer.from(`${pollId}\u0000${voter}`)), encIv: iv };
}

const ME = "15550001:7@s.whatsapp.net", CHAT = "15550001@s.whatsapp.net";

test("a vote on the newest poll comes back as the option's own words", () => {
  const polls = createPolls(), secret = crypto.randomBytes(32), values = ["Send the reply", "Next", "Not ours"];
  polls.remember(CHAT, "P1", secret, values);
  // the owner votes from their phone: the device suffix is on the socket's jid, not on the signature
  const vote = encVote({ creator: "15550001@s.whatsapp.net", voter: "15550001@s.whatsapp.net", pollId: "P1", secret, option: "Next" });
  assert.equal(polls.vote({ pollCreationMessageKey: { id: "P1" }, vote }, { creators: [ME], voters: [CHAT] }), "Next");
});

test("a vote on an older poll, a taken-back vote, or another key answers nothing", () => {
  const polls = createPolls(), secret = crypto.randomBytes(32);
  polls.remember(CHAT, "P1", secret, ["A", "B"]);
  const old = encVote({ creator: CHAT, voter: CHAT, pollId: "P1", secret, option: "A" });
  polls.remember(CHAT, "P2", crypto.randomBytes(32), ["C", "D"]);
  assert.equal(polls.vote({ pollCreationMessageKey: { id: "P1" }, vote: old }, { creators: [CHAT], voters: [CHAT] }), "", "stale poll");
  const s2 = polls.latest(CHAT).secret;
  const none = encVote({ creator: CHAT, voter: CHAT, pollId: "P2", secret: s2, option: "" });
  assert.equal(polls.vote({ pollCreationMessageKey: { id: "P2" }, vote: none }, { creators: [CHAT], voters: [CHAT] }), "", "deselected");
  const wrong = encVote({ creator: CHAT, voter: CHAT, pollId: "P2", secret: crypto.randomBytes(32), option: "C" });
  assert.equal(polls.vote({ pollCreationMessageKey: { id: "P2" }, vote: wrong }, { creators: [CHAT], voters: [CHAT] }), "", "undecryptable");
});

test("a LID-signed vote is found among the candidate jids", () => {
  const polls = createPolls(), secret = crypto.randomBytes(32);
  polls.remember(CHAT, "P3", secret, ["Yes", "No"]);
  const vote = encVote({ creator: "999@lid", voter: "999@lid", pollId: "P3", secret, option: "No" });
  assert.equal(polls.vote({ pollCreationMessageKey: { id: "P3" }, vote }, { creators: [ME, "999:3@lid"], voters: [CHAT, "999@lid"] }), "No");
});

test("options are distinct, cut to WhatsApp's length and capped at twelve", () => {
  assert.deepEqual(pollValues(["a", "a", " ", "b"]), ["a", "b"]);
  assert.equal(pollValues(["x".repeat(300)])[0].length, 100);
  assert.equal(pollValues(Array.from({ length: 20 }, (_, i) => `o${i}`)).length, MAX_OPTIONS);
});
