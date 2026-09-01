// One socket for the Timeline, Board and Studio. The terminal already speaks WebSocket;
// this one pushes feed-changed / task-changed / run-tail so those views refetch only
// when something actually moved. Hand-raise notifications keep their own timer: they
// fire BECAUSE you are on another tab.
//
// Hidden windows stay subscribed (cheap) but do not refetch; showing the tab plays
// the deferred event. A dropped socket reconnects, then sends hello so nothing is missed.
// While it is down a slow fallback keeps the screen from freezing.

const DEMO = (typeof import.meta !== "undefined" && import.meta.env && import.meta.env.VITE_DEMO === "1");

const subs = new Set();
let ws = null;
let retry = 0;
let timer = 0;
let fallback = 0;

function visible() {
  return typeof document === "undefined" || document.visibilityState !== "hidden";
}

function url() {
  const t = typeof localStorage === "undefined" ? "" : localStorage.getItem("taskuary_token");
  const proto = typeof location === "undefined" ? "ws:" : (location.protocol === "https:" ? "wss:" : "ws:");
  const host = typeof location === "undefined" ? "127.0.0.1" : location.host;
  return `${proto}//${host}/api/events/ws${t ? `?token=${encodeURIComponent(t)}` : ""}`;
}

function fanout(ev) {
  for (const s of [...subs]) {
    if (s.want.size && ev.type !== "hello" && !s.want.has(ev.type)) continue;
    s.got(ev);
  }
}

function armFallback() {
  if (DEMO || fallback) return;
  fallback = setInterval(() => {
    if (ws && ws.readyState === 1) return;
    fanout({ type: "hello" });
  }, 60000);
}

function schedule() {
  clearTimeout(timer);
  const ms = Math.min(15000, 500 * (2 ** retry));
  retry += 1;
  timer = setTimeout(connect, ms);
}

export function connect() {
  if (DEMO || typeof WebSocket === "undefined") return;
  if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) return;
  try { ws = new WebSocket(url()); } catch { schedule(); armFallback(); return; }
  ws.onopen = () => { retry = 0; if (fallback) { clearInterval(fallback); fallback = 0; } };
  ws.onmessage = (e) => {
    try { fanout(JSON.parse(e.data)); } catch { /* a non-JSON frame is not one of ours */ }
  };
  ws.onclose = () => { ws = null; schedule(); armFallback(); };
  ws.onerror = () => { try { ws.close(); } catch { /* already gone */ } };
}

// Keep the socket up for the whole page, not only while Timeline is mounted (that tab
// unmounts when you open Board, and tearing the socket down with it was the old bug).
export function holdLive() {
  connect();
  return () => {};
}

export function onLive(kinds, fn) {
  const want = new Set(!kinds ? [] : (typeof kinds === "string" ? [kinds] : kinds));
  let dirty = false;
  const got = (ev) => {
    if (!visible()) { dirty = true; return; }
    dirty = false;
    fn(ev);
  };
  const rec = { want, got };
  subs.add(rec);
  connect();
  const onVis = () => {
    if (visible() && dirty) { dirty = false; fn({ type: "hello" }); }
  };
  if (typeof document !== "undefined") document.addEventListener("visibilitychange", onVis);
  return () => {
    subs.delete(rec);
    if (typeof document !== "undefined") document.removeEventListener("visibilitychange", onVis);
  };
}

// Tests poke the dirty/visible gate without standing up a socket.
export function __testFanout(ev) {
  fanout(ev);
}
