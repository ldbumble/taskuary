import test from "node:test";
import assert from "node:assert/strict";

import { atBottom, CHIP_MOVE, channelKind, questsFor, zoneAt, zoneOf, zoneItems, bossHp, matchFor, award, levelOf, fresh, shareCard, loadGame, saveGame, COMBO_WINDOW, XP } from "../src/assistantGame.js";

const at = Date.parse("2026-09-23T10:00:00Z");

test("every lane has a room, and an agent always sits on the floor", () => {
  assert.equal(zoneOf({ lane: "approve" }), "meeting");
  assert.equal(zoneOf({ kind: "task", lane: "asked" }), "gym");
  assert.equal(zoneOf({ lane: "fyi" }), "coffee");
  assert.equal(zoneOf({ lane: "forgotten" }), "archive");
  assert.equal(zoneOf({ kind: "agent", lane: "report" }), "floor");
  assert.equal(zoneOf({ lane: "something-new" }), "coffee", "an unknown lane is still drawn somewhere, never dropped");
  const z = zoneItems([{ lane: "asked" }, { lane: "fyi" }, { kind: "agent", lane: "blocked" }]);
  assert.deepEqual([z.meeting.length, z.coffee.length, z.floor.length], [1, 1, 1]);
});

test("the boss's health is what you have not seen - read in the chat counts, a working agent never does", () => {
  const items = [{ key: "a", lane: "approve" }, { key: "b", lane: "fyi" }, { key: "c", lane: "working" }, { key: "d", lane: "blocked", surfaced: true }];
  assert.equal(bossHp(items), 2);
  assert.equal(bossHp(items, new Set(["a", "b"])), 0);
});

test("the matchmaker routes on the judged kind and the agents you have, never on words", () => {
  const agents = [{ Name: "coder", Kind: "coding" }, { Name: "helper", Kind: "general" }];
  assert.equal(matchFor({ lane: "asked", kind: "todo", coding: true }, agents).who, "coder");
  assert.equal(matchFor({ lane: "yours", kind: "todo" }, agents).who, "helper");
  assert.equal(matchFor({ lane: "approve" }, agents).verb, "approve");
  assert.equal(matchFor({ lane: "fyi" }, agents).who, "nobody");
  // the same words on a different lane give a different answer: the title is not read
  const title = "please fix the export code";
  assert.equal(matchFor({ lane: "asked", kind: "reply", title }, agents).verb, "draft");
});

test("a streak multiplies, a pause resets it", () => {
  let s = fresh(at);
  s = award(s, "approve", at).state;
  const second = award(s, "approve", at + 1000);
  assert.equal(second.gained, Math.round(XP.approve * 1.25));
  const late = award(second.state, "approve", at + 1000 + COMBO_WINDOW + 1);
  assert.equal(late.state.combo, 1);
  assert.equal(late.gained, XP.approve);
});

test("levels climb and trophies unlock once", () => {
  assert.equal(levelOf(0).level, 1);
  assert.equal(levelOf(100).level, 2);
  const r = award(fresh(at), "answer", at);
  assert.deepEqual(r.unlocked.map((a) => a.key).sort(), ["first", "unblock"]);
  assert.equal(award(r.state, "answer", at + 1).unlocked.some((a) => a.key === "first"), false);
  const room = award(fresh(at), "read", at, { coffee: 0, meeting: 3 });
  assert.ok(room.unlocked.some((a) => a.key === "coffee"), "emptying the coffee room is judged on the room");
});

test("a daily quest pays once and resets with the day", () => {
  let s = fresh(at), paid = 0;
  for (let n = 0; n < 4; n += 1) { const r = award(s, "approve", at + n * 100000); s = r.state; paid += r.quests.length; }
  assert.equal(paid, 1);
  const tomorrow = award(s, "approve", at + 86400000);
  assert.deepEqual(tomorrow.state.dayBy, { approve: 1 });
});

test("the share card carries counts, never a name", () => {
  const s = award(fresh(at), "approve", at).state;
  const card = shareCard(s, at + 65000);
  assert.match(card, /Lv 1/);
  assert.match(card, /1:05/);
  assert.doesNotMatch(card, /@|\.example/);
});

test("a broken store never breaks the game", () => {
  const bad = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } };
  assert.equal(loadGame(bad, at).xp, 0);
  assert.doesNotThrow(() => saveGame(fresh(at), bad));
  const mem = new Map(), store = { getItem: (k) => mem.get(k) ?? null, setItem: (k, v) => mem.set(k, v) };
  saveGame({ ...fresh(at), xp: 42 }, store);
  assert.equal(loadGame(store, at).xp, 42);
});

test("walking across a room's line takes you into it", () => {
  assert.equal(zoneAt(0, 0), "floor");
  assert.equal(zoneAt(0, 6), "meeting");
  assert.equal(zoneAt(-8, 6), "gym");
  assert.equal(zoneAt(8, -1), "coffee");
  assert.equal(zoneAt(8, 6), "hq");
  assert.equal(zoneAt(-8, 0), "archive");
});

test("an agent's own news stands at its desk, and every chat word scores as a real move", () => {
  assert.equal(zoneOf({ kind: "agentdone", lane: "report" }), "floor");
  assert.equal(zoneOf({ kind: "wrapup", lane: "report" }), "floor");
  assert.equal(zoneOf({ kind: "report", lane: "report" }), "coffee");
  for (const move of Object.values(CHIP_MOVE)) assert.ok(move in XP, `${move} has no points`);
});

test("mail sits at the table, chat huddles, a tool is neither", () => {
  assert.equal(channelKind({ channel: "email" }), "email");
  assert.equal(channelKind({ channel: "teams" }), "chat");
  assert.equal(channelKind({ channel: "whatsapp" }), "chat");
  assert.equal(channelKind({ channel: "github" }), "tool");
});

test("the bottom is nothing left you have not seen - a working agent never blocks it", () => {
  const items = [{ key: "a", lane: "fyi" }, { key: "b", lane: "asked" }, { key: "c", lane: "working" }];
  assert.equal(atBottom(items, new Set(["a"])), false);
  assert.equal(atBottom(items, new Set(["a", "b"])), true);
  assert.equal(atBottom([], new Set()), true);
  assert.equal(award(fresh(at), "bottom", at).gained, 50);
});

test("quests are sized to what you have, and a target never shrinks as you work", () => {
  let s = fresh(at);
  const one = questsFor(s, { approve: 1, read: 0, dispatch: 5, rep: 2 });
  assert.deepEqual(one.map((q) => [q.key, q.n, q.label]), [["q-reply", 1, "Send 1 reply"], ["q-hand", 2, "Hand 2 things to agents"], ["q-gym", 2, "Do 2 reps"]]);
  const r = award(s, "approve", at, { quests: one });
  assert.equal(r.quests.length, 1, "the one reply there was completes the quest");
  s = r.state;
  assert.equal(questsFor(s, { approve: 0 }).find((q) => q.key === "q-reply").n, 1, "sending it did not shrink the target");
});
