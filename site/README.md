# taskuary.com

The landing page. Static — `index.html`, the interactive Three.js Studio hero under `workspace/`,
the icon, and a social card. No build step, no framework, nothing to install.

The interactive demo is built to `site/demo/` with `npm --prefix website run build:demo`
and is served at `https://taskuary.com/demo/`. Each visit starts with a guided request:
watch it become a task, review the proposed answer, and see the simulated result.
The full sample app is optional through the Explore control or `/demo/?demo=explore`.
The landing page's optional Studio starts collapsed.

## Deploy (Cloudflare Workers)

The existing `taskuary` Workers project deploys both the static site and its two tiny analytics
endpoints from one command. `wrangler.jsonc` serves `site/` as static assets and sends `/api/*`
through `worker.mjs` first:

1. Cloudflare dashboard → the `taskuary` Worker → **Settings → Builds** → connect
   `ldbumble/taskuary`, production branch `master`.
2. Leave the build command empty and use deploy command **`npx wrangler deploy`**.
3. Keep `taskuary.com` and `www.taskuary.com` under the Worker's custom domains.

Every push to `master` redeploys. A one-off deployment is simply `npx wrangler deploy`.

## Editing

- `index.html` — the whole page. The palette is the app's own ("Beacon": `website/src/theme.jsx`),
  type is IBM Plex from Google Fonts.
- `workspace/` — the interactive Three.js hero. Work arrives beside the room, agents collect it,
  desks assemble as needed, and Nora raises her hand with a draft. It supports mouse, touch,
  keyboard navigation, and `prefers-reduced-motion`.
- `floor.js` — the previous canvas hero, retained for reference but no longer loaded by the page.
- `og.png` — the 1200×630 social card, cropped from `docs/screenshot-floor.png`.
- The Download button points at `releases/latest`; `publish.yml` attaches `Taskuary.exe` to
  every tagged release, so the direct link
  `https://github.com/ldbumble/taskuary/releases/latest/download/Taskuary.exe` works from the
  first release cut after that change.

## Counting the demo

Nothing counted anything until now, so "did anyone try it?" had no answer. Two first-party
pieces, no third-party script and no cookie:

- `site/index.html` sends `open` when the page loads and `cta` when someone clicks Try it now,
  Download or View source.
- The demo bundle (`website/src/demoTrack.js`) sends `open`, `tab`, `row`, `verdict`, `ask`,
  `dwell` (15s/1m/3m/10m) and `leave` with the seconds spent — never a word the visitor typed,
  and only when the page is served from `taskuary.com`.

Both POST to `functions/api/ev.js`, routed by `worker.mjs`. The Worker keeps the events in its own
SQLite-backed `StatsStore`; `wrangler.jsonc` creates and binds it automatically on deployment.
There is no database id or manual database binding to configure. A fork that already has the old
`DEMO_EVENTS` D1 binding can keep using it.

Reading the stats is public, like collecting them: `/stats` and `GET /api/ev` need no login. The counts
are of anonymous tab sessions; nothing in them names a person.

Read it at **`https://taskuary.com/stats.html`** - a dashboard in plain words: downloads first (with
downloads per day), visitors (and the week-on-week change), who tried the demo and who stayed a minute, how visitors came in
(the site, the site then the demo, or straight to the demo), visitors per day, what site visitors did next, where visitors came
from, countries, what demo visitors did and how long people stayed. The page is not linked from the site and has no data of
its own; it reads `/api/ev`. The landing page and the demo share one tab id (`tq_demo_sid`), so a visit that goes on into the
demo is one visitor - before 2026-10-15 the landing page ran two counters and every visit counted twice.
