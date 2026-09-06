import test from 'node:test';
import assert from 'node:assert/strict';
import { observeSync } from '../src/syncObserver.js';
import { syncFace, syncPhaseLabel } from '../src/syncTiming.js';

const flush = () => new Promise(setImmediate);
function harness(read) {
  let clock = 0, id = 0, listener, unsubscribed = false;
  const timers = new Map(), changes = [], errors = [];
  const observer = observeSync({ read, changed: data => changes.push(data), failed: e => errors.push(e),
    now: () => clock, schedule: (fn, ms) => { timers.set(++id, { fn, ms }); return id; },
    cancel: key => timers.delete(key), subscribe: fn => { listener = fn; return () => { unsubscribed = true; }; } });
  return { observer, changes, errors, timers, event: () => listener(), stopped: () => unsubscribed,
    async tick() { const [key, timer] = timers.entries().next().value; timers.delete(key); clock += timer.ms; await timer.fn(); } };
}

test('a five-minute running job stays running until the server reports completion without a live event', async () => {
  let status = { state: 'running', phase: 'triaging' };
  const h = harness(async () => ({ status, now: 1000, nextPollAt: null }));
  await flush();
  for (let n = 0; n < 151; n++) await h.tick();
  assert.equal(h.changes.length, 152);
  assert.ok(h.changes.every(data => data.status.state === 'running'));
  status = { state: 'idle' };
  await h.tick();
  assert.equal(h.changes.at(-1).status.state, 'idle');
  assert.equal([...h.timers.values()][0].ms, 30000);
  h.observer.stop();
  assert.equal(h.timers.size, 0);
  assert.equal(h.stopped(), true);
});

test('failed status reads never invent completion and pending responses cannot update an unmounted view', async () => {
  let fail = false, resolve;
  const h = harness(() => fail ? Promise.reject(new Error('offline')) : Promise.resolve({ status: { state: 'running' } }));
  await flush(); fail = true;
  await h.tick();
  assert.equal(h.errors.length, 1);
  assert.equal(h.changes.length, 1);
  assert.equal([...h.timers.values()][0].ms, 2000);
  h.observer.stop();
  const pending = harness(() => new Promise(done => { resolve = done; }));
  await flush(); pending.observer.stop();
  resolve({ status: { state: 'idle' } }); await flush();
  assert.equal(pending.changes.length, 0);
  assert.equal(pending.timers.size, 0);
});

test('live events coalesce behind a slow status request instead of overlapping it', async () => {
  let resolve, calls = 0;
  const h = harness(() => { calls++; return new Promise(done => { resolve = done; }); });
  await flush(); h.event(); h.event();
  assert.equal(calls, 1);
  resolve({ status: { state: 'running' } }); await flush();
  assert.equal([...h.timers.values()][0].ms, 0);
  const next = h.tick(); await flush();
  assert.equal(calls, 2);
  resolve({ status: { state: 'idle' } }); await next;
  h.observer.stop();
});

test('an unavailable initial status retries promptly without reporting idle', async () => {
  const h = harness(async () => { throw new Error('starting up'); });
  await flush();
  assert.equal(h.changes.length, 0);
  assert.equal(h.errors.length, 1);
  assert.equal([...h.timers.values()][0].ms, 2000);
  h.observer.stop();
});

test('the sync caption names the work and labels completed fetch attempts as checks', () => {
  assert.deepEqual(['fetching', 'triaging', 'checking', 'running_reports'].map(syncPhaseLabel),
    ['Reading sources', 'Organizing', 'Checking updates', 'Running reports']);
  assert.equal(syncFace({ checked: true, lastAt: new Date(2026, 8, 6, 10, 42), terse: true }), 'checked 10:42 AM');
});
