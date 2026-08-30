// Pure hand-raise state. Keeping this out of React makes the polling edge cases testable:
// delayed responses, uncertain idle screens, vanished processes, and multiple live rows.

const payload = (row, identity, cycle, finished = false) => ({
  tid: row.TaskId,
  ref: `TQ-${String(row.TaskId).padStart(4, "0")}`,
  agent: row.AgentName || "agent",
  title: row.Title || "",
  asking: !finished && !!row.asking,
  finished,
  tail: (row.tail || []).slice(-2).join(" "),
  identity,
  eventId: `${identity}:${finished ? "ended" : cycle}`,
});

const observations = (rows, idleWaiting) => {
  const out = new Map();
  for (const row of rows || []) {
    const tid = Number(row.TaskId);
    if (!Number.isFinite(tid)) continue;
    const session = row.kind === "session";
    const waiting = session && !!(row.asking || (row.waiting ?? (Number(row.idle) >= idleWaiting)));
    // A CLI prompt/spinner is authoritative. An unknown silent screen is only a fallback and
    // must repeat before it can change the stable state.
    const certain = !session || !!row.asking || row.phase === (waiting ? "parked" : "working");
    const identity = `${row.kind || "run"}:${row.StartedAt || row.RunId || "unknown"}:${row.AgentName || "agent"}`;
    const observation = { tid, state: waiting ? "waiting" : "working", certain, identity, row: { ...row, TaskId: tid } };
    const old = out.get(tid);
    // A terminal session is the owner's interactive truth when a headless run row for the
    // same task is also present. Array order must not decide the notification.
    if (!old || session || old.row.kind !== "session") out.set(tid, observation);
  }
  return out;
};

// Returns {state, raises}. Missing rows remain remembered: one incomplete live-runs response
// must not erase history. Two consecutive successful polls without a formerly-working process
// confirm that it ended and needs the owner's attention.
export function advanceHandRaises(previous = {}, rows = [], idleWaiting = 45) {
  const state = { ...previous }, raises = [], seen = observations(rows, idleWaiting);

  for (const [tid, obs] of seen) {
    const key = String(tid), old = previous[key];
    if (!old || old.identity !== obs.identity || old.ended) {
      state[key] = { identity: obs.identity, stable: obs.state, candidate: null, count: 0,
        cycle: old?.identity === obs.identity ? old.cycle : 0, missing: 0, ended: false, row: obs.row };
      continue; // a session already parked when first observed is old news
    }
    if (old.stable === obs.state) {
      state[key] = { ...old, candidate: null, count: 0, missing: 0, row: obs.row };
      continue;
    }
    const count = old.candidate === obs.state ? old.count + 1 : 1;
    if (obs.certain || count >= 2) {
      const cycle = old.cycle + (obs.state === "waiting" ? 1 : 0);
      state[key] = { ...old, stable: obs.state, candidate: null, count: 0, cycle,
        missing: 0, ended: false, row: obs.row };
      if (obs.state === "waiting") raises.push(payload(obs.row, obs.identity, cycle));
    } else {
      state[key] = { ...old, candidate: obs.state, count, missing: 0, row: obs.row };
    }
  }

  for (const [key, old] of Object.entries(previous)) {
    if (seen.has(Number(key))) continue;
    const missing = (old.missing || 0) + 1;
    state[key] = { ...old, missing };
    if (missing >= 2 && old.stable === "working" && !old.ended) {
      state[key] = { ...state[key], ended: true };
      raises.push(payload(old.row, old.identity, old.cycle, true));
    } else if (missing >= 2) {
      state[key] = { ...state[key], ended: true };
    }
  }
  return { state, raises };
}

// One browser window should claim a transition for all windows on the same Taskuary origin.
// The cooldown also catches a flapping terminal without suppressing a later, genuine stop.
export function claimHandRaise(storage, raise, now = Date.now(), cooldown = 12000) {
  if (!storage) return true;
  try {
    const key = `tq.handraise.${encodeURIComponent(`${raise.tid}:${raise.identity}`)}`;
    const last = Number(storage.getItem(key) || 0);
    if (last && now - last < cooldown) return false;
    storage.setItem(key, String(now));
    return true;
  } catch { return true; }
}

export const isWatchingTask = (tab, selected, tid) => tab === "Tasks" && Number(selected) === Number(tid);

export const handRaiseWhat = (raise) => raise.finished ? `${raise.agent} finished`
  : raise.asking ? `${raise.agent} asked you something`
    : `${raise.agent} stopped and is waiting on you`;

export const enqueueHandRaise = (queue, raise) => [...(queue || []), raise];
export const dismissHandRaise = (queue) => (queue || []).slice(1);

// setInterval does not wait for promises. Without this gate, an older slow response can land
// after a newer one and rewind the tracker, making the next poll ring again at random.
export const nonOverlapping = (work) => {
  let inFlight = false;
  return async () => {
    if (inFlight) return false;
    inFlight = true;
    try { await work(); return true; }
    finally { inFlight = false; }
  };
};
