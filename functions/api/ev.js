// What the demo is actually worth, measured first-party.
//
// taskuary.com is static on Cloudflare, so until now nothing knew whether anyone opened
// /demo/, let alone whether they clicked anything once they were there - which is the only
// question the demo exists to answer. This takes batched events from the page and writes them
// to a D1 table. No third party, no cookies, no ad network: an id that lives in sessionStorage
// and dies with the tab, and a country Cloudflare already knows from routing the request.
//
// Setup (once, from the repo root):
//   npx wrangler d1 create taskuary-demo
//   npx wrangler d1 execute taskuary-demo --remote --file functions/schema.sql
//   Worker -> Bindings -> Add binding -> D1 database: DEMO_EVENTS -> taskuary-demo
// Unbound it is a no-op, so a preview deploy or a fork never errors and never collects.

import { hasStatsSession } from "../lib/statsAuth.js";

const KINDS = new Set(["open", "tab", "row", "verdict", "ask", "watch", "dwell", "leave", "cta"]);
const cut = (v, n) => (typeof v === "string" ? v.slice(0, n) : "");
const statsJson = (body, status = 200) => Response.json(body,
  { status, headers: { "Cache-Control": "no-store" } });

export async function onRequestPost({ request, env }) {
  if (!env.DEMO_EVENTS) return new Response(null, { status: 204 });
  let body;
  try { body = await request.json(); } catch { return new Response(null, { status: 204 }); }
  const evs = Array.isArray(body?.events) ? body.events.slice(0, 40) : [];
  if (!evs.length) return new Response(null, { status: 204 });

  const cf = request.cf || {};
  const sid = cut(body.sid, 40);
  const ref = cut(body.ref, 200);
  const now = new Date().toISOString();
  const rows = evs.filter((e) => KINDS.has(e?.kind)).map((e) => env.DEMO_EVENTS
    .prepare(`INSERT INTO ev (At, Sid, Kind, What, N, Page, Ref, Country, Mobile)
              VALUES (?,?,?,?,?,?,?,?,?)`)
    .bind(now, sid, cut(e.kind, 16), cut(e.what, 80), Number(e.n) || 0,
          cut(body.page, 120), ref, cut(cf.country, 4), body.mobile ? 1 : 0));
  if (rows.length) { try { await env.DEMO_EVENTS.batch(rows); } catch { /* a lost beacon is not an error */ } }
  return new Response(null, { status: 204 });
}

// Reading analytics requires the signed session issued by /api/stats-auth. Event collection above
// remains anonymous and public; a login must never get in the way of a sendBeacon from the demo.
export async function onRequestGet({ request, env }) {
  const url = new URL(request.url);
  if (!(await hasStatsSession(request)))
    return statsJson({ error: "Sign in to view analytics." }, 401);
  if (!env.DEMO_EVENTS) return statsJson({ visits: 0, note: "no D1 binding" });
  const days = Math.min(90, Math.max(1, Number(url.searchParams.get("days")) || 14));
  const since = new Date(Date.now() - days * 86400000).toISOString();
  const q = (sql) => env.DEMO_EVENTS.prepare(sql).bind(since).all().then((r) => r.results || []);
  const [visits, kinds, what, depth] = await Promise.all([
    q(`SELECT substr(At,1,10) d, COUNT(DISTINCT Sid) sessions, COUNT(*) events
       FROM ev WHERE At>=? GROUP BY d ORDER BY d`),
    q(`SELECT Kind, COUNT(*) n FROM ev WHERE At>=? GROUP BY Kind ORDER BY n DESC`),
    q(`SELECT Kind, What, COUNT(*) n FROM ev WHERE At>=? AND What<>'' GROUP BY Kind, What
       ORDER BY n DESC LIMIT 40`),
    q(`SELECT CASE WHEN c=1 THEN '1 (bounced)' WHEN c<5 THEN '2-4' WHEN c<15 THEN '5-14' ELSE '15+' END bucket,
              COUNT(*) sessions FROM (SELECT Sid, COUNT(*) c FROM ev WHERE At>=? GROUP BY Sid)
       GROUP BY bucket ORDER BY sessions DESC`),
  ]);
  return statsJson({ days, visits, kinds, what, depth });
}
