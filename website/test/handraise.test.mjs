import test from "node:test";
import assert from "node:assert/strict";
import { advanceHandRaises, claimHandRaise, dismissHandRaise, enqueueHandRaise,
  handRaiseWhat, isWatchingTask, loadHandRaiseState, nonOverlapping,
  saveHandRaiseState } from "../src/handraiseState.js";

const session = (overrides = {}) => ({ TaskId: 247, AgentName: "codex", kind: "session",
  StartedAt: "2026-08-30 00:00:00", phase: "working", waiting: false, idle: 2,
  Title: "Fix notifications", tail: ["working"], ...overrides });

test("a parked session raises once only after it was seen working", () => {
  let t = advanceHandRaises({}, [session()]);
  assert.deepEqual(t.raises, []);
  t = advanceHandRaises(t.state, [session({ phase: "parked", waiting: true, tail: ["Done.", ">"] })]);
  assert.equal(t.raises.length, 1);
  assert.equal(t.raises[0].ref, "TQ-0247");
  t = advanceHandRaises(t.state, [session({ phase: "parked", waiting: true })]);
  assert.deepEqual(t.raises, []);
});

test("a fast question already parked on the first poll raises immediately", () => {
  const t = advanceHandRaises({}, [session({ phase: "parked", waiting: true, asking: true })]);
  assert.equal(t.raises.length, 1);
  assert.equal(t.raises[0].asking, true);
  assert.equal(t.raises[0].eventId.endsWith(":1"), true);
});

test("an unknown idle screen must repeat, so one flaky poll cannot ring", () => {
  let t = advanceHandRaises({}, [session({ phase: "unknown" })]);
  t = advanceHandRaises(t.state, [session({ phase: "unknown", waiting: true, idle: 60 })]);
  assert.deepEqual(t.raises, []);
  t = advanceHandRaises(t.state, [session({ phase: "unknown", waiting: false, idle: 3 })]);
  assert.deepEqual(t.raises, []); // the glitch cleared and never became stable
  t = advanceHandRaises(t.state, [session({ phase: "unknown", waiting: true, idle: 60 })]);
  assert.deepEqual(t.raises, []);
  t = advanceHandRaises(t.state, [session({ phase: "unknown", waiting: true, idle: 68 })]);
  assert.equal(t.raises.length, 1);
});

test("a missed live-runs row preserves the working history", () => {
  let t = advanceHandRaises({}, [session()]);
  t = advanceHandRaises(t.state, []);
  assert.deepEqual(t.raises, []);
  t = advanceHandRaises(t.state, [session({ phase: "parked", waiting: true })]);
  assert.equal(t.raises.length, 1);
});

test("a process disappearing twice raises a finished event, but a parked session does not also finish", () => {
  let working = advanceHandRaises({}, [session()]);
  working = advanceHandRaises(working.state, []);
  assert.deepEqual(working.raises, []);
  working = advanceHandRaises(working.state, []);
  assert.equal(working.raises.length, 1);
  assert.equal(handRaiseWhat(working.raises[0]), "codex finished");

  let parked = advanceHandRaises({}, [session({ phase: "parked", waiting: true })]);
  assert.equal(parked.raises.length, 1);
  parked = advanceHandRaises(parked.state, []);
  parked = advanceHandRaises(parked.state, []);
  assert.deepEqual(parked.raises, []);
});

test("a replacement session already asking raises independently", () => {
  let t = advanceHandRaises({}, [session()]);
  t = advanceHandRaises(t.state, [session({ StartedAt: "2026-08-30 00:01:00", phase: "parked", waiting: true })]);
  assert.equal(t.raises.length, 1);
});

test("an interactive session wins over a duplicate headless run row", () => {
  const run = { TaskId: 247, AgentName: "coder", kind: "run", RunId: 8, StartedAt: "2026-08-30 00:00:00" };
  let t = advanceHandRaises({}, [session(), run]);
  t = advanceHandRaises(t.state, [run, session({ phase: "parked", waiting: true })]);
  assert.equal(t.raises.length, 1);
});

test("browser windows claim an event once but allow the next waiting cycle", () => {
  const values = new Map(), storage = { getItem: (k) => values.get(k), setItem: (k, v) => values.set(k, v) };
  const raise = { tid: 247, identity: "session:now:codex", eventId: "session:now:codex:1" };
  assert.equal(claimHandRaise(storage, raise), true);
  assert.equal(claimHandRaise(storage, raise), false);
  assert.equal(claimHandRaise(storage, { ...raise, eventId: "session:now:codex:2" }), true);
});

test("tracker state survives a reload so an existing wait is not replayed", () => {
  const values = new Map(), storage = { getItem: (k) => values.get(k), setItem: (k, v) => values.set(k, v) };
  const first = advanceHandRaises({}, [session({ phase: "parked", waiting: true })]);
  assert.equal(first.raises.length, 1);
  saveHandRaiseState(storage, first.state);
  const afterReload = advanceHandRaises(loadHandRaiseState(storage), [session({ phase: "parked", waiting: true })]);
  assert.deepEqual(afterReload.raises, []);
});

test("watching suppression follows the selected task exactly", () => {
  assert.equal(isWatchingTask("Tasks", 247, 247), true);
  assert.equal(isWatchingTask("Tasks", 246, 247), false);
  assert.equal(isWatchingTask("Board", 247, 247), false);
});

test("simultaneous agents queue in arrival order instead of overwriting each other", () => {
  let queue = enqueueHandRaise([], { tid: 246 });
  queue = enqueueHandRaise(queue, { tid: 247 });
  assert.deepEqual(queue.map((r) => r.tid), [246, 247]);
  assert.deepEqual(dismissHandRaise(queue).map((r) => r.tid), [247]);
});

test("a slow poll cannot overlap and land out of order", async () => {
  let finish, calls = 0;
  const poll = nonOverlapping(() => { calls += 1; return new Promise((resolve) => { finish = resolve; }); });
  const first = poll();
  assert.equal(await poll(), false);
  assert.equal(calls, 1);
  finish();
  assert.equal(await first, true);
  const third = poll();
  assert.equal(calls, 2);
  finish();
  assert.equal(await third, true);
});
