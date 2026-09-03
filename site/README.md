# taskuary.com

The landing page. Static — one `index.html` with its CSS inline, the Studio screenshot as the
hero, the icon, and a social card. No build step, no framework, nothing to install.

The interactive demo is built to `site/demo/` with `npm --prefix website run build:demo`
and is served at `https://taskuary.com/demo/`.

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
- `floor.js` — the hero: the Studio's own isometric renderer (ported from `website/src/StudioView.jsx`)
  on a canvas, driven by `STORY` — mail arrives on the rail, triage rules, agents walk in through
  the door and sit. The door is clickable and scrolls into the site. Respects `prefers-reduced-motion`
  (one composed frame). Edit the story in `STORY`; the loop length is `LOOP` seconds.
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

Both POST to `functions/api/ev.js`, routed by `worker.mjs`, which writes to D1 and **does nothing
at all without a binding** — so a preview deploy or a fork collects no data. To turn it on once:

```
npx wrangler d1 create taskuary-demo
npx wrangler d1 execute taskuary-demo --remote --file functions/schema.sql
```

Then in the Worker: **Bindings → Add binding → D1 database** → variable name `DEMO_EVENTS` →
database `taskuary-demo`. The small admin login is intentionally hardcoded in
`functions/lib/statsAuth.js`; edit `STATS_USERNAME` and `STATS_PASSWORD` there and redeploy when
you want to change it. No Cloudflare credential variables are required.

Read it at **`https://taskuary.com/stats.html`**. It has a normal username/password sign-in and
keeps a signed, secure, HttpOnly session for 12 hours. Credentials never appear in the URL or
browser storage. Once signed in it shows sessions per day, how far people got (bounced after one
event, or stayed for fifteen), which buttons were pressed and which tabs were opened. The page is
not linked from the site and has no data of its own; `/api/ev` returns 401 without a valid admin
session.
