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
