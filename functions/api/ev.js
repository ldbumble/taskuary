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

// This intentionally returns aggregate, anonymous telemetry without a login. The stats page is
// public too: there are no names, addresses, IPs, user-agent strings, cookies, or persistent ids
// in this store to protect. Keeping the reader here (instead of a third-party dashboard) also
// makes the definitions below the single source of truth for every number on the page.
export async function onRequestGet({ request, env }) {
  const url = new URL(request.url);
  if (!env.DEMO_EVENTS) return statsJson({ visits: 0, note: "no D1 binding" });
  const days = Math.min(90, Math.max(1, Number(url.searchParams.get("days")) || 14));
  const since = new Date(Date.now() - days * 86400000).toISOString();
  const q = (sql, ...args) => env.DEMO_EVENTS.prepare(sql).bind(...args).all()
    .then((r) => r.results || []);
  const demoAction = "Kind IN ('tab','row','verdict','ask','watch')";
  const coreAction = "Kind IN ('row','verdict','ask','watch')";
  const [summaryRows, durationRows, daily, engagement, actions, ctas, referrers,
    countries, devices, recent] = await Promise.all([
    q(`SELECT COUNT(*) sessions, SUM(landing) landing, SUM(demo_click) demo_clicks,
              SUM(demo) demo, SUM(engaged) engaged, SUM(acted) acted,
              SUM(downloaded) downloads, SUM(events) events,
              SUM(CASE WHEN landing=1 AND demo=1 THEN 1 ELSE 0 END) converted,
              SUM(CASE WHEN demo_click=1 AND demo=1 THEN 1 ELSE 0 END) clickthrough
       FROM (
         SELECT Sid,
           MAX(CASE WHEN Kind='open' AND (Page='/' OR What='landing') THEN 1 ELSE 0 END) landing,
           MAX(CASE WHEN Kind='cta' AND What='demo' THEN 1 ELSE 0 END) demo_click,
           MAX(CASE WHEN Kind='open' AND Page LIKE '/demo%' THEN 1 ELSE 0 END) demo,
           MAX(CASE WHEN Page LIKE '/demo%' AND (${demoAction} OR (Kind='dwell' AND N>=15)) THEN 1 ELSE 0 END) engaged,
           MAX(CASE WHEN Page LIKE '/demo%' AND ${coreAction} THEN 1 ELSE 0 END) acted,
           MAX(CASE WHEN Kind='cta' AND What='download' THEN 1 ELSE 0 END) downloaded,
           COUNT(*) events
         FROM ev WHERE At>=? GROUP BY Sid
       )`, since),
    q(`SELECT ROUND(AVG(seconds),0) avg_seconds, MAX(seconds) max_seconds
       FROM (
         SELECT Sid, MAX(CASE WHEN Kind IN ('dwell','leave') THEN N ELSE 0 END) seconds
         FROM ev WHERE At>=? AND Page LIKE '/demo%' GROUP BY Sid
       )`, since),
    q(`SELECT substr(At,1,10) d,
         COUNT(DISTINCT CASE WHEN Kind='open' AND (Page='/' OR What='landing') THEN Sid END) landing,
         COUNT(DISTINCT CASE WHEN Kind='open' AND Page LIKE '/demo%' THEN Sid END) demo,
         COUNT(DISTINCT CASE WHEN Page LIKE '/demo%' AND (${demoAction} OR (Kind='dwell' AND N>=15)) THEN Sid END) engaged
       FROM ev WHERE At>=? GROUP BY d ORDER BY d`, since),
    q(`SELECT bucket, COUNT(*) sessions FROM (
         SELECT Sid, CASE
           WHEN MAX(CASE WHEN Kind IN ('dwell','leave') THEN N ELSE 0 END)<15 THEN 'Under 15 sec'
           WHEN MAX(CASE WHEN Kind IN ('dwell','leave') THEN N ELSE 0 END)<60 THEN '15-59 sec'
           WHEN MAX(CASE WHEN Kind IN ('dwell','leave') THEN N ELSE 0 END)<180 THEN '1-2 min'
           WHEN MAX(CASE WHEN Kind IN ('dwell','leave') THEN N ELSE 0 END)<600 THEN '3-9 min'
           ELSE '10+ min' END bucket,
           CASE
             WHEN MAX(CASE WHEN Kind IN ('dwell','leave') THEN N ELSE 0 END)<15 THEN 1
             WHEN MAX(CASE WHEN Kind IN ('dwell','leave') THEN N ELSE 0 END)<60 THEN 2
             WHEN MAX(CASE WHEN Kind IN ('dwell','leave') THEN N ELSE 0 END)<180 THEN 3
             WHEN MAX(CASE WHEN Kind IN ('dwell','leave') THEN N ELSE 0 END)<600 THEN 4 ELSE 5 END ord
         FROM ev WHERE At>=? AND Page LIKE '/demo%' GROUP BY Sid
       ) GROUP BY bucket, ord ORDER BY ord`, since),
    q(`SELECT Kind, What, COUNT(DISTINCT Sid) sessions, COUNT(*) events
       FROM ev WHERE At>=? AND Page LIKE '/demo%' AND ${demoAction}
       GROUP BY Kind, What ORDER BY sessions DESC, events DESC LIMIT 40`, since),
    q(`SELECT What, COUNT(DISTINCT Sid) sessions, COUNT(*) clicks
       FROM ev WHERE At>=? AND Kind='cta' GROUP BY What ORDER BY sessions DESC`, since),
    q(`SELECT CASE WHEN Ref='' THEN 'Direct / unknown' ELSE Ref END label,
              COUNT(DISTINCT Sid) sessions
       FROM ev WHERE At>=? AND Kind='open' AND (Page='/' OR What='landing')
       GROUP BY label ORDER BY sessions DESC LIMIT 12`, since),
    q(`SELECT CASE WHEN Country='' THEN 'Unknown' ELSE Country END label,
              COUNT(DISTINCT Sid) sessions
       FROM ev WHERE At>=? AND Kind='open' AND (Page='/' OR What='landing')
       GROUP BY label ORDER BY sessions DESC LIMIT 12`, since),
    q(`SELECT CASE WHEN Mobile=1 THEN 'Mobile' ELSE 'Desktop' END label,
              COUNT(DISTINCT Sid) sessions
       FROM ev WHERE At>=? AND Kind='open' AND (Page='/' OR What='landing')
       GROUP BY label ORDER BY sessions DESC`, since),
    q(`SELECT MIN(At) started, MAX(At) last_seen,
              COALESCE(NULLIF(MAX(CASE WHEN Kind='open' AND (Page='/' OR What='landing') THEN Ref ELSE '' END),''),
                       NULLIF(MAX(Ref),''), 'Direct / unknown') referrer,
              CASE WHEN MAX(Country)='' THEN 'Unknown' ELSE MAX(Country) END country,
              CASE WHEN MAX(Mobile)=1 THEN 'Mobile' ELSE 'Desktop' END device,
              MAX(CASE WHEN Kind='open' AND (Page='/' OR What='landing') THEN 1 ELSE 0 END) landing,
              MAX(CASE WHEN Kind='cta' AND What='demo' THEN 1 ELSE 0 END) demo_click,
              MAX(CASE WHEN Kind='open' AND Page LIKE '/demo%' THEN 1 ELSE 0 END) demo,
              MAX(CASE WHEN Page LIKE '/demo%' AND (${demoAction} OR (Kind='dwell' AND N>=15)) THEN 1 ELSE 0 END) engaged,
              MAX(CASE WHEN Page LIKE '/demo%' AND ${coreAction} THEN 1 ELSE 0 END) acted,
              MAX(CASE WHEN Kind='cta' AND What='download' THEN 1 ELSE 0 END) downloaded,
              MAX(CASE WHEN Kind IN ('dwell','leave') THEN N ELSE 0 END) seconds,
              COUNT(*) events
       FROM ev WHERE At>=? GROUP BY Sid ORDER BY started DESC LIMIT 30`, since),
  ]);
  return statsJson({
    days,
    summary: { ...(summaryRows[0] || {}), ...(durationRows[0] || {}) },
    daily, engagement, actions, ctas, referrers, countries, devices, recent,
  });
}
