# The documentation site — design

**Date:** 2026-09-18
**Status:** approved in chat, ready for an implementation plan

Taskuary's user documentation is six markdown files in `docs/`, reachable only by browsing the
GitHub repository, mixed in a folder with 39 engineering notes. taskuary.com has a landing page and
a demo and nothing between "here is what it does" and "clone the repo". This builds a real
documentation site at `taskuary.com/docs`, laid out like the app's Settings page, from one source,
with the machinery that keeps it true.

## Decisions taken

| Question | Decision |
|---|---|
| Audience | End users of the product. Not a contributor/architecture guide. |
| Source of truth | Markdown under `docs/site/`, built into committed static HTML. |
| Page shape | One page per rail entry, each its own URL. |
| The old `docs/*.md` | The six user-facing ones move and become stubs; the engineering notes are untouched. |
| Visual direction | "Editorial" — see *Look* below. |

## Architecture

```
docs/site/*.md + docs/site/manifest.json
        |  npm run build:docs   (website/tools/build-docs.mjs, marked)
        v
site/docs/*.html + docs.css + docs.js + search.json     <- committed to git
        |  push to master
        v
Cloudflare Workers serves site/ as static assets
```

**Source.** One markdown file per rail page under `docs/site/`, plus `docs/site/manifest.json`
giving page order, slug, title and a one-line description — the same shape as `PAGES` in
`SettingsView.jsx`. A `##` heading inside a file becomes a rail sub-entry, its anchor and its
search crumb at once; nothing is listed twice.

**Build.** `website/tools/build-docs.mjs`, run as `npm run build:docs`. This follows the existing
house pattern: `build:demo` already lives in `website/` and writes into `../site/`. It reuses
`website/node_modules`, so CI needs no second `npm ci`. One new devDependency: `marked`.

**Output, committed.** `site/docs/<slug>.html` — one per page, each carrying the whole rail — plus
shared `docs.css`, `docs.js` and `search.json`. Cloudflare's `html_handling: auto-trailing-slash`
serves `/docs/connections` from `connections.html` and `/docs/` from `index.html` with no redirect
rules. The site stays pure static: no worker involvement, no framework, nothing to install.

**The gate.** A step in the existing `build-web` job runs `npm run build:docs`, then
`git diff --exit-code -- site/docs` plus the untracked-file check, and uploads `site/docs` as an
artifact on failure. This is byte-for-byte the rule the packaged UI got in `c4c5eb3e`, for the same
reason: a committed artifact that no longer matches its source must fail CI, not ship.

## The page

Vanilla JS. The behaviour is the Settings rail's, which the owner asked for by name.

- **The rail** lists every doc page; the current one is expanded to show its `##` sections, the
  others collapse behind a chevron. Every entry is a real `<a href>` — a section on the current page
  scrolls, a section elsewhere navigates to `connections#sources`. The docs therefore work with
  JavaScript off; only search and the active-section highlight need it.
- **Scroll-spy** marks the section you are actually looking at: the last heading that has passed
  under the sticky bar, with the rule Settings needed for its last section — at the foot of the
  page the final section wins, whatever the arithmetic says about the one above it
  (`settingsMap.sectionOffset`).
- **Search** sits at the top of the rail over `search.json` (every section, its heading, its text).
  Results read `Connections → Sources`, the same path the rail shows, and land on that anchor.
  Entirely client-side: no third-party service, no key.
- **Mobile**: the rail becomes a collapsed "On this page" disclosure above the text.

### Look — "Editorial"

The site's own skin, not the app's: the Beacon palette and IBM Plex from `site/index.html`, so
`/docs` reads as part of taskuary.com.

- Body text at a **760px measure**, 16.5px / 1.72. Settings is 980 because it holds forms and
  tables; running prose at 980 is ~115 characters a line.
- 42px display headings, `-0.022em`; hairline rules between sections rather than boxes.
- Callouts are a **2px left rule** with a mono eyebrow — never a tinted panel. Colour identifies;
  it does not decorate.
- Screenshots float with a soft shadow and a mono caption. Code blocks sit on `--panel` with a
  1px border and a copy button.
- Diagrams are inline SVG, in the spirit of the existing `learning-loop.svg`.
- Dark mode; anchor links appearing on heading hover; previous/next at the foot of each page.

## Content

Eight pages. Sections shown are the `##` headings, which the rail generates.

| Page (slug) | Sections |
|---|---|
| Start here (`index`) | What Taskuary is · Install on Windows · Install with Python · Docker · Your first run · Where your data lives · Updating |
| How it works (`how-it-works`) | The Timeline · The five roads a message can take · What triage decides · The work rail and its lanes · Nothing sends itself · The learning loop |
| Connections (`connections`) | What a connection is · The four roles · Mail · Chat · Repositories and trackers · Databases and report sources · Adding another of the same kind |
| Tasks and agents (`tasks-and-agents`) | A task's three lifecycles · Sending work to a coding agent · The general agent · Sessions and transcripts · Checklists and closing · Profiles and playbooks |
| Reports and the Assistant (`reports`) | A report is a pipeline · Sources · Letting the AI write the cards · The AI pass · Where a run goes · Schedules · The Assistant |
| On your phone (`phone`) | The doorways · What it can do · The morning line · Handing over |
| Settings reference (`settings`) | One section per schema group — **generated**, see below |
| When something is wrong (`troubleshooting`) | It will not start · A connection stopped · Triage got it wrong · An agent is stuck · Reading the audit log · Where the logs are |

Existing material is rewritten and expanded into these, not pasted: `getting-started.md` →
Start here; `product-guide.md` → How it works and parts of Tasks and agents;
`task-lifecycle.md` → Tasks and agents; `integrations.md` → Connections;
`reports-and-assistant.md` → Reports and the Assistant; `roadmap.md` stays a repo document.

## Links in

- `site/index.html`: **Docs** in the top nav, a footer column, and a "Read the docs" link beside
  the download button.
- `README.md` and `README.zh-CN.md` point at `taskuary.com/docs` rather than `docs/*.md`.
- The six moved files become one-line stubs naming their new URL, so no existing link 404s.
- In the app: one line, "Full documentation", under the Settings rail — where someone already is
  when they are looking something up.

## Keeping it current

Four mechanisms, most valuable first.

1. **The settings reference is generated from `taskuary/settings_schema.json`** — the file the app
   and the assistant already read. Label, group, default and help text come from there, so that
   page cannot drift: a knob added to the schema appears in the docs on the next build. This is
   only possible because that file is already the one vocabulary
   (`settings_schema.py`, `appfacts.py`, `SettingsView.jsx`).
2. **The CI gate** above: the committed page must match a fresh build, so nobody hand-edits the
   HTML or forgets to rebuild.
3. **Tests that hold the docs honest** — `website/test/docs.test.mjs`:
   - every manifest page has a source file, and every source file is in the manifest;
   - every internal link and `#anchor` resolves to a real page and heading;
   - every referenced image exists in `site/docs/`;
   - the generated settings page names exactly the groups and knobs the schema has;
   - the search index carries one entry per section.
   A rename that breaks a cross-reference fails CI instead of rotting quietly.
4. **A visible age stamp.** Each page's footer carries the version it was written for and its
   source file's last-changed date, so a page that has fallen behind says so rather than lying
   confidently. One line is added to the `deploy` skill: a release that changes user-visible
   behaviour updates `docs/site/`.

## Testing

- `website/test/docs.test.mjs` as above, run by the existing `npm test` in the `build-web` job.
- The build is deterministic: same input, same bytes, which is what makes the CI diff meaningful.
- No new Python tests; nothing in `taskuary/` changes except that `settings_schema.json` gains a
  reader in the docs build.

## Out of scope

- Contributor and architecture documentation (a later, separate site section if it is ever wanted).
- Versioned docs for older releases. One set, for the current release, with an age stamp.
- Translating the docs. The Chinese README keeps its own life.
- Search across the repo's engineering notes.

## Risks

- **The docs go stale anyway.** Mitigated by 1–4 above, but only the settings page is structurally
  incapable of drifting; the prose still depends on someone writing it. The age stamp makes the
  failure visible rather than silent.
- **Another committed artifact to rebuild.** The same cost the packaged UI already carries, and the
  same gate catches it.
- **`marked` as a dependency.** A build-time-only devDependency in `website/`, never shipped to a
  browser.
