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
- `hero.png` — `docs/screenshot-floor.png` cropped to 2880×1440. Regenerate the screenshot with
  `node website/shot_floor.mjs`, then re-crop (see the git log of this folder for the PIL one-liner).
- `og.png` — the 1200×630 social card, same source.
- The Download button points at `releases/latest`; `publish.yml` attaches `Taskuary.exe` to
  every tagged release, so the direct link
  `https://github.com/ldbumble/taskuary/releases/latest/download/Taskuary.exe` works from the
  first release cut after that change.
