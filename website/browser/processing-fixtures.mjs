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
  while (Date.now() < deadline) {
    const pileResponse = await fetch(`${harness.fixtureApi}/api/funnel/pile?force=1`, { headers });
    if (!pileResponse.ok) throw new Error(`demo watcher snapshot failed: ${pileResponse.status}`);
    lastPile = await pileResponse.json();
    const stateResponse = await fetch(`${harness.fixtureApi}/api/concierge`, { headers });
    if (!stateResponse.ok) throw new Error(`demo watcher history failed: ${stateResponse.status}`);
    state = await stateResponse.json();
    const announced = new Set((state.messages || []).flatMap((turn) => turn.card?.key?.startsWith("agent:")
      ? [Number(turn.card.tid)] : []));
    if (sessions.every((row) => announced.has(row.TaskId))) {
      const drainedResponse = await fetch(`${harness.fixtureApi}/api/funnel/pile?force=1`, { headers });
      const drained = await drainedResponse.json();
      lastPile = drained;
      if (drainedResponse.ok && !(drained.events || []).length) {
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
