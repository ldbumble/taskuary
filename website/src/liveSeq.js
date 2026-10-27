// WHICH WRITES A READ HAS SEEN, AND WHOSE THEY WERE (the load-once pass, 2026-10-27; server: live.seq / live.TAB). Every wake-up about a
// durable write carries `seq`, stamped once the write committed, and every answer says the newest stamp there was as its read began
// (X-Taskuary-Seq; a rail's own `live_seq`). A read stamped at least an event's seq began after that write committed and holds it, so
// the page need not read again for it - the rail reloaded 1.5 s after every press, its own answer already in hand. A wake-up with no
// stamp is never covered: the safe error is one read too many, never one too few.
// `by`: the tab whose request made the write. This page names itself on every request (api.js), so it knows the bursts that are only
// its own presses - whose answers it draws itself - from everything else (a new arrival), which it reads at once.
export const TAB = `t${Math.random().toString(36).slice(2, 10)}${Date.now().toString(36)}`;
export const mine = (ev) => !!ev?.by && ev.by === TAB;
export const stampOf = (ev) => (Number.isFinite(ev?.seq) ? ev.seq : null);
// the stamp an answer was read at (axios lower-cases headers), or null
export const seqOf = (res) => { const v = res?.headers?.["x-taskuary-seq"]; return v != null && v !== "" && Number.isFinite(+v) ? +v : null; };
// `seen`: the newest stamp a read the page holds was taken at; `meta.seq`: the newest write of the burst (null: one was unstamped)
export const covers = (seen, meta) => meta?.seq != null && seen != null && seen >= meta.seq;
