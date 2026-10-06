import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { installNumbersWorkflow, finishNumbersWorkflow, isGuidedDemo, NUMBERS_TASK, NUMBERS_MESSAGE, NUMBERS_REVIEW, NUMBERS_DRAFT, NUMBERS_RESULT } from '../src/demoNumbers.js';
import { createDemoAssistantState } from '../src/demoAssistantData.js';
import { parseStamp } from '../src/demoClock.js';

test('numbers walkthrough keeps the request, general workspace and review on the same task', async () => {
  const state = JSON.parse(await readFile(new URL('../src/demoFixtures.json', import.meta.url), 'utf8'));
  const assistant = createDemoAssistantState();
  installNumbersWorkflow(state, assistant);
  const task = state['/api/tasks/detail'][NUMBERS_TASK];
  assert.equal(task.task.Kind, 'general');
  assert.equal(task.messages[0].MessageId, NUMBERS_MESSAGE);
  assert.equal(task.reviews.length, 0);
  assert.equal(state['/api/reviews'].data.length, 0, 'no review before preparation');
  assert.equal(assistant.pile.items[0].tid, NUMBERS_TASK);
  assert.deepEqual(assistant.messages, [], 'the walkthrough begins at the welcome button');
  const review = finishNumbersWorkflow(state);
  finishNumbersWorkflow(state);
  assert.equal(state['/api/reviews'].data.length, 1, 'reopening the workspace does not duplicate its review');
  assert.equal(review.ReviewId, NUMBERS_REVIEW);
  assert.equal(review.TaskId, NUMBERS_TASK);
  assert.equal(review.MessageId, NUMBERS_MESSAGE);
  assert.equal(review.Status, 'pending');
  assert.equal(task.reviews[0], review);
  const amounts = [...NUMBERS_RESULT.matchAll(/\| (?:Supplies|Services|Software) \| \$([\d,]+)/g)].map(m => Number(m[1].replaceAll(',','')));
  const total = Number(NUMBERS_DRAFT.match(/spend was \$([\d,]+)/)[1].replaceAll(',',''));
  assert.equal(amounts.length, 3);
  assert.equal(amounts.reduce((a,b)=>a+b,0), total, 'the reply total matches the result categories');
  assert.match(NUMBERS_DRAFT, /Open purchase orders are excluded/i);
});

test('a fresh public demo is one current request, without unrelated tasks, meetings or agent sessions', async () => {
  const state = JSON.parse(await readFile(new URL('../src/demoFixtures.json', import.meta.url), 'utf8'));
  const assistant = createDemoAssistantState(state);
  const at = parseStamp('2027-02-10 09:30:00');
  installNumbersWorkflow(state, assistant, at);
  assert.deepEqual(state['/api/tasks'].data.map(t => t.TaskId), [NUMBERS_TASK]);
  assert.deepEqual(state['/api/tasks?active=1'].data.map(t => t.TaskId), [NUMBERS_TASK]);
  assert.deepEqual(state['/api/feed'].data.map(m => m.MessageId), [NUMBERS_MESSAGE]);
  assert.equal(assistant.pile.items.length, 1);
  assert.equal(assistant.chats.length, 1);
  assert.equal(assistant.pile.items[0].when, '2027-02-10 09:29:00');
  assert.equal(state['/api/tasks/detail'][NUMBERS_TASK].task.CreatedAt, '2027-02-10 09:29:00');
  assert.deepEqual(state['/api/calendar/today'].events, []);
  assert.deepEqual(state['/api/terminals'].data, []);
  assert.deepEqual(state['/api/runs/live'].data, []);
  assert.equal(finishNumbersWorkflow(state, at + 3000).CreatedAt, '2027-02-10 09:30:03');
});

// THE DEMO IS THE APP (the owner, 2026-10-06: "who made this ugly thing on top? ... website should be the same. show many
// tasks in demo"): a plain /demo/ opens the full invented office; the one-request walkthrough is only asked for by link
test('the demo opens on the full office; the guided request is an explicit link', () => {
  assert.equal(isGuidedDemo(''), false);
  assert.equal(isGuidedDemo('?demo=explore'), false);
  assert.equal(isGuidedDemo('?demo=guided'), true);
  assert.equal(isGuidedDemo('?workflow=numbers'), true);
});
