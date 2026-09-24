import test from "node:test";
import assert from "node:assert/strict";
import {
  DEMO_ASSISTANT_CHATS,
  DEMO_ASSISTANT_TIMELINE,
  DEMO_ASSISTANT_TRANSCRIPTS,
  createDemoAssistantState,
  installDemoAssistantTimeline,
} from "../src/demoAssistantData.js";

test("the demo has a current assistant conversation and distinct earlier threads", () => {
  const demo = createDemoAssistantState();
  assert.equal(demo.chats[0].open, true);
  assert.ok(demo.messages.some((message) => message.role === "user"));
  assert.ok(demo.messages.some((message) => message.role === "assistant" && message.card));
  assert.ok(DEMO_ASSISTANT_CHATS.length >= 4);
  for (const chat of DEMO_ASSISTANT_CHATS) {
    assert.ok(DEMO_ASSISTANT_TRANSCRIPTS[chat.taskId]?.length, `missing transcript for ${chat.taskId}`);
  }
});

test("the scripted pipe demonstrates several kinds of work without claiming a live process", () => {
  const demo = createDemoAssistantState();
  assert.ok(demo.pile.items.length >= 6);
  assert.deepEqual(new Set(demo.pile.items.map((item) => item.kind)),
    new Set(["agent", "review", "asked", "idea", "report", "fyi"]));
  assert.ok(demo.pile.items.some((item) => item.lane === "working"));
  assert.ok(demo.pile.items.some((item) => item.lane === "blocked"));
});

test("invented assistant posts are added to the Timeline once and stay date-sorted", () => {
  const state = { "/api/feed": { data: [{ MessageId: 1, SentAt: "2026-09-03 09:00:00" }] }, "/api/messages/one": {} };
  installDemoAssistantTimeline(state);
  installDemoAssistantTimeline(state);
  const rows = state["/api/feed"].data;
  assert.equal(rows.filter((row) => row.Channel === "assistant").length, DEMO_ASSISTANT_TIMELINE.length);
  assert.equal(new Set(rows.map((row) => row.MessageId)).size, rows.length);
  assert.deepEqual(rows.map((row) => row.SentAt), [...rows.map((row) => row.SentAt)].sort().reverse());
  for (const post of DEMO_ASSISTANT_TIMELINE) {
    assert.match(state["/api/messages/one"][post.MessageId].BodyText, /^## /);
  }
});

// The scripted cards were written against one recording's numbers and the next recording moved them: the
// cutover card opened the overnight-import draft (2026-09-23). Bound by what they are, every card's ids
// point at the row it names in the recording the demo ships.
test("every scripted card is bound to the row it names in the shipped recording", async () => {
  const { readFileSync } = await import("node:fs");
  const fx = JSON.parse(readFileSync(new URL("../src/demoFixtures.json", import.meta.url), "utf8"));
  const demo = createDemoAssistantState(fx);
  const tasks = new Map(fx["/api/tasks"].data.map((t) => [t.TaskId, t.Title]));
  const reviews = new Map(fx["/api/reviews"].data.map((r) => [r.ReviewId, r]));
  for (const item of demo.pile.items) {
    assert.equal(item.bind, undefined, item.title);
    assert.ok(item.key && !/undefined/.test(item.key), item.title);
    if (item.rid) assert.equal(reviews.get(item.rid).Subject, item.title);
  }
  const cutover = demo.pile.items.find((i) => i.kind === "review");
  assert.equal(tasks.get(cutover.tid), "Can you confirm the AP cutover date?");
  const census = demo.pile.items.find((i) => i.lane === "blocked");
  assert.match(tasks.get(census.tid), /census sync fails/);
  assert.equal(demo.pile.alerts[0].item, census.key);
});
