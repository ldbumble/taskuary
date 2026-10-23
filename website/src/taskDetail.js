// SWAP, NEVER CLEAR (the 2026-10-19 UI walk, G8): a task view put on the table mounted empty and asked for its task only then, so
// between the press and the answer the canvas held a bordered shell with a spinner and the row held a lone Next - 2-9 frames on
// every Next, rail click and search pick - before the task and its buttons arrived together. The read is asked for EARLIER, where
// the next view is already known (the row Next will bring, a rail row under the pointer, a search hit highlighted), and the view
// draws from it on its first frame; it still reads the task again on mount, so what is held is only ever the first paint.
// ...for as long as a person reads the item before it: six seconds held nothing by the time Next was pressed (G8, verified 2026-10-20).
// What changes a task while it is held says so - an act pressed here (AssistantView's onPressed) or a write anywhere (task-changed) -
// and lets the read go; past this a read is not drawn even so
const TTL = 120000;
const held = new Map();                 // tid -> { at, p, data }
const now = () => Date.now();
const fresh = (e) => !!e && now() - e.at < TTL;

// ask for a task's view ahead of drawing it - once per tid while the last read is fresh; a failure is held as nothing
export const prefetchTask = (api, tid) => {
  const id = Number(tid);
  if (!id) return null;
  const e = held.get(id);
  readTerms(api);
  if (fresh(e)) return e.p;
  const rec = { at: now(), data: null, p: null }, asked = rec.at;
  // ...a GOAL's steps with it: they were read only after the view mounted, and "no steps yet" stood over a goal with five (G8)
  rec.p = api.get(`/api/tasks/${id}`).then(({ data }) => {
    rec.data = data; noteRead(id, data, asked);
    if (data?.task?.DoneWhen) api.get(`/api/tasks/${id}/steps`).then(({ data: d }) => { rec.steps = d?.steps || []; }).catch(() => {});
    // ...and its waiting room, which the view reads straight after the task: drawn without it, the view filled in a beat later
    api.get(`/api/tasks/${id}/waitroom`).then(({ data: w }) => { rec.wait = w; }).catch(() => {});
    return data;
  }).catch(() => { if (held.get(id) === rec) held.delete(id); return null; });
  held.set(id, rec);
  return rec.p;
};
// ...and the agents' sessions: whether the task has one decides half its row (Answer it, Review changes, Stop and save), and a view that
// waited to look put a session-less row up first - Reply and Send out results for ~100ms over a task whose agent was waiting on the
// owner (G8, verified 2026-10-20). One list for every task, read with any task ahead
let terms = null;                       // { at, rows }
const readTerms = (api) => {
  if (fresh(terms)) return;
  const rec = terms = { at: now(), rows: null };
  api.get("/api/terminals", { params: { details: false } }).then(({ data }) => { rec.rows = data?.data || []; }).catch(() => { if (terms === rec) terms = null; });
};
// undefined while not known - the view looks for itself then - and null for a task with no session
export const heldTerm = (tid) => {
  const id = Number(tid);
  if (!id || !fresh(terms) || !terms.rows || terms.gone?.has(id)) return undefined;
  return terms.rows.find((x) => x.taskId === id && x.alive) || terms.rows.find((x) => x.taskId === id) || null;
};
export const keepTerms = (rows) => { if (Array.isArray(rows)) terms = { at: now(), rows }; };
// the task as last read, while it is fresh - what a view draws on its first frame
export const heldTask = (tid) => { const e = held.get(Number(tid)); return fresh(e) && e.data?.task?.TaskId === Number(tid) ? e.data : null; };
export const heldSteps = (tid) => { const e = held.get(Number(tid)); return fresh(e) && Array.isArray(e.steps) ? e.steps : null; };
export const heldWait = (tid) => { const e = held.get(Number(tid)); return fresh(e) && e.data && e.wait ? e.wait : null; };
// ...a view's own read is the newest word on its task; an act on any task makes every held read old. `asked`: when that read was asked
// (noteRead), never when it landed - a read that waited behind the rail's build reflects the moment it was sent
export const keepTask = (tid, data, wait = undefined, asked = now()) => { const id = Number(tid), e = held.get(id);
  if (id && data?.task?.TaskId === id) held.set(id, { at: now(), data, p: Promise.resolve(data), steps: e?.steps, wait: wait === undefined ? e?.wait : wait });
  noteRead(id, data, asked); };
// ...one task's write leaves every other task's session as it was: only that task's is unknown again
export const forgetTasks = (tid = null) => {
  if (tid == null) { terms = null; held.clear(); reads.clear(); pileAt = 0; return; }
  held.delete(Number(tid));
  if (terms) terms.gone = new Set([...(terms.gone || []), Number(tid)]);
};

// WHICH READ IS NEWER, THE RAIL'S OR THE TASK'S (the owner, 2026-10-23: "this shows agent working but it's not working"). The rail is
// one big read the server builds under a lock - 152 s on that morning - while the task's own read is small, so the page knew its agent
// had finished (its Result) while the rail row and the header pill, which reads that row, still held the build from when it worked.
// Each read is stamped with the moment it was ASKED: what it reflects is no older than that. A task read asked after the rail's last
// one is the newer word on that task (railStatus.agentGone), for its header pill and its rail row alike. Never aged out - only compared.
let pileAt = 0;
const reads = new Map();                // tid -> { at, state, live }
const watchers = new Set();
export const notePile = (at) => { pileAt = Math.max(pileAt, Number(at) || 0); };
export function noteRead(tid, data, at = now()) {
  const id = Number(tid), was = reads.get(id);
  if (!id || data?.task?.TaskId !== id || (was && was.at > at)) return;
  const r = { at, state: data.state || null, live: !!data.session?.alive };
  reads.set(id, r);
  if (!was || was.state !== r.state || was.live !== r.live) watchers.forEach((f) => f(id));
}
// the task's own read when it was asked after the rail's last one - else null, and the rail's row stands
export const pageRead = (tid) => { const r = reads.get(Number(tid)); return r && r.at > pileAt ? r : null; };
// a view drawing rail rows draws again when a task's read says something new
export const watchReads = (f) => { watchers.add(f); return () => { watchers.delete(f); }; };
