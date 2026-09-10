import assert from 'node:assert/strict';

// Stabilize only the owned demo startup before processing interaction assertions.
export const waitForDemoReplays = async (harness, timeout = 30000) => {
  const deadline = Date.now() + timeout;
  let sessions = [];
  while (Date.now() < deadline) {
    const response = await fetch(`${harness.fixtureApi}/api/runs/live?lines=4`, {
      headers: { "X-Taskuary-Token": harness.token },
    });
    if (!response.ok) throw new Error(`demo replay snapshot failed: ${response.status}`);
    const data = await response.json();
    sessions = (data.data || []).filter((row) => row.kind === "session");
    if (sessions.length && sessions.every((row) => row.waiting === true && row.phase === "parked")) {
      return sessions;
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`demo replays did not reach their stable waiting state: ${JSON.stringify(sessions)}`);
};

export const settleDemoWatcher = async (harness, sessions, timeout = 20000) => {
  const headers = { "X-Taskuary-Token": harness.token };
  const deadline = Date.now() + timeout;
  let state = null;
  let lastPile = null;
  let settled = false;
  assert.ok(sessions.length && sessions.every(row => Number.isInteger(row.TaskId)),
    'watcher readiness requires the exact seeded replay tasks');
  const readHistory = async () => {
    const response = await fetch(`${harness.fixtureApi}/api/concierge`, { headers });
    if (!response.ok) throw new Error(`demo watcher history failed: ${response.status}`);
    const snapshot = await response.json();
    assert.ok(Array.isArray(snapshot.messages), 'demo history must return its complete message array');
    return snapshot;
  };
  const initialHistory = (await readHistory()).messages;
  const waitingInPileAndStrip = (snapshot) => {
    assert.ok(Array.isArray(snapshot.items) && Array.isArray(snapshot.alerts) && Array.isArray(snapshot.events),
      'demo pile must expose items, strip alerts, and transition events');
    return sessions.every(session => snapshot.items.some(item => item.tid === session.TaskId
      && item.kind === 'agent' && item.lane === 'blocked'
      && snapshot.alerts.some(alert => alert.item === item.key && alert.kind === 'agent' && alert.lane === 'blocked')));
  };
  while (Date.now() < deadline) {
    const pileResponse = await fetch(`${harness.fixtureApi}/api/funnel/pile?force=1`, { headers });
    if (!pileResponse.ok) throw new Error(`demo watcher snapshot failed: ${pileResponse.status}`);
    lastPile = await pileResponse.json();
    state = await readHistory();
    assert.deepEqual(state.messages, initialHistory, 'watcher observations must not append unsolicited chat turns');
    // Waiting agents already own alerts derived from their exact pile keys. The
    // watcher no longer manufactures chat cards for these passive transitions.
    // Match keys rather than prefixes so legacy and canonical identities both work.
    if (waitingInPileAndStrip(lastPile)) {
      const drainedResponse = await fetch(`${harness.fixtureApi}/api/funnel/pile?force=1`, { headers });
      if (!drainedResponse.ok) throw new Error(`demo watcher drain failed: ${drainedResponse.status}`);
      const drained = await drainedResponse.json();
      lastPile = drained;
      state = await readHistory();
      assert.deepEqual(state.messages, initialHistory, 'draining notices must leave chat history untouched');
      if (waitingInPileAndStrip(drained) && !drained.events.length) {
        settled = true;
        break;
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  if (!settled) {
    throw new Error(`demo watcher did not settle its replay transitions: ${JSON.stringify({
      taskIds: sessions.map((row) => row.TaskId),
      messages: state?.messages || [],
      agents: (lastPile?.items || []).filter(item => item.kind === 'agent'),
      alerts: lastPile?.alerts || [],
      events: lastPile?.events || [],
    })}`);
  }
  const reset = await fetch(`${harness.fixtureApi}/api/assistant/dock/new`, { method: "POST", headers });
  if (!reset.ok) throw new Error(`demo watcher reset failed: ${reset.status}`);
  const freshResponse = await fetch(`${harness.fixtureApi}/api/concierge`, { headers });
  if (!freshResponse.ok) throw new Error(`demo watcher reset snapshot failed: ${freshResponse.status}`);
  const fresh = await freshResponse.json();
  if (!Array.isArray(fresh.messages) || fresh.messages.length) {
    throw new Error("demo watcher reset did not leave a blank fixture conversation");
  }
};
