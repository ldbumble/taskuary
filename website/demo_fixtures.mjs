// Freeze a running demo into a file the browser can serve on its own.
//
// taskuary.com/demo has no server behind it - it is the real React app with its API client
// swapped for a fixture (demoApi.js). The fixture is DUMPED from a real `taskuary --demo`
// instance rather than written by hand, so every shape is one the app actually produced: a
// hand-written fixture drifts the first time a field is renamed, and a demo that renders a
// blank page is worse than no demo.
//
//   TASKUARY_DEMO=1 TASKUARY_HOME=$(mktemp -d) python -m uvicorn taskuary.server:app --port 7801
//   node demo_fixtures.mjs http://127.0.0.1:7801 > src/demoFixtures.json
import { writeFileSync } from "node:fs";

const BASE = process.argv[2] || "http://127.0.0.1:7801";
const OUT = process.argv[3] || new URL("./src/demoFixtures.json", import.meta.url).pathname.replace(/^\//, "");

// Everything the app reads on a first look at each tab. Parameterised reads are recorded under
// the path the UI asks for, so the adapter can match on the same string.
const PATHS = [
  "/api/version", "/api/build", "/api/demo", "/api/owner", "/api/whoami", "/api/settings",
  "/api/setup", "/api/funnel", "/api/ingest/status", "/api/problems", "/api/runs/live",
  "/api/feed?limit=200", "/api/tasks?active=1", "/api/tasks",
  "/api/reviews", "/api/terminals", "/api/agents", "/api/brains", "/api/cli/detect",
  "/api/connectors", "/api/sources", "/api/report-types", "/api/reports/last-runs",
  "/api/board/notes", "/api/handbook", "/api/people", "/api/send-targets", "/api/memory", "/api/policies",
  "/api/calendar/today", "/api/audit/recent", "/api/semantic/metrics", "/api/soul/interview",
  "/api/voice/status", "/api/learned/graph",
];

const out = {};
for (const path of PATHS) {
  try {
    const r = await fetch(BASE + path);
    out[path.split("?")[0] === "/api/feed" ? "/api/feed" : path] = r.ok ? await r.json() : null;
  } catch (e) {
    out[path] = null;
    console.error(`skip ${path}: ${e.message}`);
  }
}

// the docs, and the per-task detail for everything on the board - the two things a visitor
// clicks into first
out["/api/doc"] = {};
for (const name of ["soul", "triage", "style", "counsel", "coder", "digest", "learned"]) {
  const r = await fetch(`${BASE}/api/doc/${name}`).catch(() => null);
  out["/api/doc"][name] = r && r.ok ? await r.json() : { content: "" };
}
out["/api/tasks/detail"] = {};
for (const t of (out["/api/tasks"]?.data || [])) {
  const r = await fetch(`${BASE}/api/tasks/${t.TaskId}`).catch(() => null);
  if (r && r.ok) out["/api/tasks/detail"][t.TaskId] = await r.json();
  const a = await fetch(`${BASE}/api/tasks/${t.TaskId}/assistant`).catch(() => null);
  if (a && a.ok) out["/api/tasks/detail"][`${t.TaskId}:assistant`] = await a.json();
}
// Attachments, and the FILES themselves. The static demo has no server to serve
// /api/attachments/7 from, so every image rides in the recording as a data: URI - which is how
// a report's chart survives the trip. Non-images keep their url and simply do not resolve; a
// spreadsheet the visitor cannot download is a footnote, a chart that does not draw is a hole.
out["/api/messages/attachments"] = {};
out["/api/messages/one"] = {};
for (const row of (out["/api/feed"]?.data || [])) {
  // the panel reads the whole message for any row with no task behind it - a report, a filed
  // notice - and without this it got an empty object and drew a message with no id, which is
  // why a report's own chart never appeared next to it
  const one = await fetch(`${BASE}/api/messages/${row.MessageId}`).catch(() => null);
  if (one && one.ok) out["/api/messages/one"][row.MessageId] = await one.json();
  const r = await fetch(`${BASE}/api/messages/${row.MessageId}/attachments`).catch(() => null);
  if (!r || !r.ok) continue;
  const box = await r.json();
  if (!(box.data || []).length) continue;
  for (const a of box.data) {
    if (!a.is_image || !a.url) continue;
    const f = await fetch(BASE + a.url).catch(() => null);
    if (!f || !f.ok) continue;
    const type = f.headers.get("content-type") || a.content_type || "image/png";
    const b64 = Buffer.from(await f.arrayBuffer()).toString("base64");
    a.url = `data:${type.split(";")[0]};base64,${b64}`;
  }
  out["/api/messages/attachments"][row.MessageId] = box;
}

// what a replayed coding session had said by the time we looked
out["/api/terminals/scrollback"] = {};
for (const s of (out["/api/terminals"]?.data || out["/api/terminals"] || [])) {
  const r = await fetch(`${BASE}/api/terminals/${s.sid}?tail=400`).catch(() => null);
  if (r && r.ok) out["/api/terminals/scrollback"][s.sid] = await r.json();
}

writeFileSync(OUT, JSON.stringify(out, null, 1));
console.error(`wrote ${OUT}: ${Object.keys(out).length} recordings, ${(JSON.stringify(out).length / 1024).toFixed(0)}KB`);
