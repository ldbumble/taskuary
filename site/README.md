# taskuary.com

The landing page. Static — one `index.html` with its CSS inline, the Studio screenshot as the
hero, the icon, and a social card. No build step, no framework, nothing to install.

## Deploy (Cloudflare Pages)

The domain is on Cloudflare, so Pages is the shortest path and needs no token anywhere:

1. Cloudflare dashboard → **Workers & Pages → Create → Pages → Connect to Git** → pick
   `ldbumble/taskuary`.
2. Build settings: framework **None**, build command *(empty)*, build output directory **`site`**.
3. Deploy. Then **Custom domains → Set up a custom domain → `taskuary.com`** (and `www`);
   Cloudflare writes the DNS records itself because the zone is already here.

Every push to `master` that touches `site/` redeploys. Preview URLs come with pull requests.

Or from a terminal, one-off: `npx wrangler pages deploy site --project-name taskuary`.

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
