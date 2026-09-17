# Onboarding: a checklist that points, and a walk that goes

2026-09-17

## The problem

Two things call themselves setting Taskuary up, and neither does what its name says.

The **top-right counter** opens `SetupWizard`, whose eight rows each carry an inline form. The
file's header argues for that: "Pointing is not setting up: it hands the work back with directions
attached." The argument held while the forms were one field. They are not any more — the AI row now
carries a CLI picker, an installer, a sign-in pane and an API-key form, and it is a worse version of
the page that owns those things. A form kept in step with the real page by hand is a second source
of truth, and the second one loses.

The **Set up Taskuary** chip on the assistant header (`AssistantView.jsx:1172`) opens something
else entirely: an AI-led concierge walk (`/api/concierge/setup`) that asks you to type what you want
set up. It cannot run at all before an AI is connected, which is precisely when somebody presses it.

So: the checklist stops holding forms and starts pointing at the pages that own the work, and the
chip stops needing an AI and starts walking the whole app.

## The shape this takes

Nothing here is a new interaction model. The walk is the assistant's existing one — **deterministic
steps, with the AI only for anything off script** — applied to onboarding. The stops are static and
the buttons are code; a typed question is an ordinary assistant turn, and `concierge.fallback()`
already speaks in facts when there is no model to answer it. `walk.py` supplies stops. Everything
else in the conversation is machinery that already exists.

Two surfaces, one source of truth:

**The panel** — the top-right counter and its dialog, same place, five rows, gone for good once they
are done. The shortest path to a working funnel.

**The walk** — the assistant header's chip. A scripted stop-per-turn tour of the whole app,
re-runnable any time, needing no AI.

Anything set up anywhere ticks in both, because both read the same derived state. That is already
how `setup.py` works and it does not change.

## The panel

`taskuary/setup.py` keeps `state(store)` and keeps deriving. Its `steps` drop from eight to five,
each gaining a `goto` deep-link, and every inline form is removed except the owner's.

| # | key | Row | Goes to | Ticks when |
|---|-----|-----|---------|------------|
| 1 | `owner` | Say who you are | *inline, name + email* | owner name is set and is not the literal `the owner` — unchanged |
| 2 | `ai` | Set up an AI | Connections → AI CLI agents (`#cli-agents`) | `_ai(store)` finds a CLI profile or an active AI connector — unchanged |
| 3 | `models` | Choose what runs on which model | Settings → Configuration → Triage & agents | the page has been opened once |
| 4 | `inbound` | Connect where work arrives | Connections (`#connector=outlook`) | a **mail or messaging** connector is live |
| 5 | `sync` | Read your first messages | Assistant | real (non-report) messages are in the feed — unchanged |

### Row 1 keeps its form

The only exception. Its whole content is two text boxes, and sending somebody to Docs to type their
own name is exactly the pointing the old header comment complains about. `OwnerForm` stays as it is.
Every other form in `SetupWizard.jsx` is deleted: `BrainForm`, `MailboxForm`, `SyncForm`,
`HistoryForm`, `SoulForm`, `AgentForm`, `CliPicker`; the `FORMS` map shrinks to `{owner}`.

### Row 3 is the one stored flag

Every other row reads real state. Row 3 cannot: a fresh install already ships working brain and
model defaults, so there is nothing to detect, and "the defaults are fine" and "I never looked" are
the same state. Opening the page is enough to make it green.

- New setting `setup_seen_models`.
- New endpoint `POST /api/setup/seen` taking `{step: "models"}`, writing the setting and auditing it.
- `AiDefaults.jsx` posts it once on mount.
- `setup.py`'s module docstring gains a paragraph naming this as the single deliberate exception to
  "nothing here is a stored checklist", so the next reader finds the reason instead of the
  contradiction.

### Row 4 narrows to mail and messaging

`INBOUND` (`setup.py:18`) currently counts trackers, so a GitHub connection alone ticks the row while
the Timeline still has no mail in it. The row now requires one of:

    outlook, teams, slack, gmail, imap, telegram, whatsapp, imessage, discord

Trackers stay connectable and stay in the funnel; they no longer satisfy this row. Implemented as a
`MESSAGING` subset of `INBOUND`, so nothing else reading `INBOUND` changes behaviour.

### Row 5 ticks on arrival, not on completion

Derived from the feed holding real messages, exactly as the current `sync` step is. It does not wait
for the owner to have walked their mail: walking is the walk's job, and a row that waits for "enough"
items read is a row that can sit unticked forever. Its link goes to the Assistant tab, where the pile
is waiting.

### Disappearing

`complete` is now simply all five. `SetupChip` already returns `null` when `state.complete`, so the
counter removing itself falls out of the change. The two-tier counters (`guide_done`/`guide_total`
beside `done`/`total`) collapse into one pair — there is no optional tier left to count separately.
`ready` and `complete` become the same thing, and `ready` is removed.

`SetupPanel`'s three-way headline (`complete` / `ready` / neither) collapses to two: the count left,
or the finished state. `NextSteps` — the "what happens now" block — moves into the walk, which is a
better home for it than a panel about to vanish.

### What leaves the panel

`soul`, `style`, `triage` and `agent` stop being rows. They are not gone; they become stops on the
walk, where there is room to say what they are for. The panel is the shortest path to a working
funnel, and none of the four is on it.

## The walk

New module `taskuary/walk.py`.

```
STOPS = [ {key, title, blurb, can, goto} ... ]      # ordered, static, hard-coded
state(store, at) -> {stops, at, total}              # facts and done-ness filled live
```

Each stop carries:

- `key` — stable id
- `title` — the part of the app
- `blurb` — one or two lines on what this part is for
- `can` — **what you can do here**: a hard-coded list of capability lines, each with an optional
  `goto` of its own, so a stop is a menu of real things rather than a paragraph
- `image` — `/walk/<key>.png`, a shot of the tab; absent on the five setup stops
- `goto` — the deep link the stop's main button opens
- `done` — filled from `setup.state(store)` where that module already knows, else absent
- `facts` — a live line read off the store, e.g. "1 connected: Outlook"

`facts` is what keeps the two surfaces honest: a stop never states a fact of its own, it states one
the panel would state. `can` is the opposite — deliberately static prose, because what the app can do
is not a thing to derive, and a capability list assembled at runtime is a list that goes blank on an
empty install.

### The stops

1–5. The five panel rows, same order, same links, same derivations. Stop 1 carries `OwnerForm`
itself rather than a link, for the same reason the panel does — two text boxes have nowhere better to
be. Stop 2 carries the terminal (below). Stops 3–5 link out like every other stop.

6. **Connections** — every mailbox, chat, tracker and report source. *Can:* connect a mailbox, add a
   chat channel, connect a tracker, add an AI CLI, test any connection.
7. **Docs** — SOUL.md is the funnel's constitution; STYLE.md is how you write. *Can:* edit SOUL.md,
   generate your reply style from sent mail, generate triage habits from what you answered. Absorbs
   the old `soul` and `style` steps, including their generate buttons.
8. **Settings** — *Can:* choose the triage brain and its backups, set what each part runs on, decide
   what drafts automatically, choose how finished work lands, set notifications. Absorbs the old
   `triage` step.
9. **Board** — work in flight and the agents doing it. *Can:* watch a live session, take over a pane,
   hand an agent a note, put a coding agent to work. Absorbs the old `agent` step.
10. **Tasks** — *Can:* open a task, see its thread and its runs, continue a session, close it.
11. **Review** — drafted replies. *Can:* approve a draft, redraft it, edit before sending, say it is
    not yours. Nothing sends until you approve it.
12. **Reports & workflows** — *Can:* schedule a check that reads and summarises, build a workflow
    that writes, choose when a run reaches you.
13. **The Assistant** — *Can:* press Next through the pile, reply, hand work to an agent, say it is
    not ours, ask anything in your own words.
14. **Hub** — where it all comes together.

### Endpoints

- `GET /api/setup/walk` → `{stops, at, total}`
- `POST /api/setup/walk {at}` → move to a stop, store the position, return the new state
- `POST /api/setup/walk/reset` → back to the beginning

Position lives in a setting (`setup_walk_at`), so a reload, a tab switch, an off-script conversation
or a week away all resume where the owner stopped. Reaching the last stop clears it, so the next
press starts over.

### In the assistant

`AssistantView`'s `setup()` handler stops calling `/api/concierge/setup`. It fetches
`/api/setup/walk` and pushes one `WalkCard` message per stop.

`/api/concierge/setup` is untouched and keeps every other caller: `SetupCard`'s "Open walkthrough",
the floating assistant's "Set up report", and the phone doorway. Only the header chip changes what it
opens.

New card kind `walk` in `assistantCards.jsx`:

```
+-- Setting Taskuary up — 6 of 14 -----------+
| Connections                                |
| Every mailbox, chat and tracker Taskuary   |
| reads lives here.  1 connected: Outlook.   |
|                                            |
| You can:                                   |
|   · connect a mailbox            ->        |
|   · add a chat channel           ->        |
|   · connect a tracker            ->        |
|   · add an AI CLI                ->        |
|   · test any connection                    |
|                                            |
| [Open Connections]  [Next >]      [Finish] |
+--------------------------------------------+
```

Three buttons, and no more. **Open ‹tab›** follows the stop's `goto`. **Next ›** pushes the
following stop as a **new message** rather than replacing the card, so the conversation keeps the
trail of where the walk has been — consistent with every other card in this chat. **Finish** leaves
the walk and clears the stored position, so the next press starts from the beginning.

There is no Skip: with nothing recorded per stop but the position, skipping and advancing are the
same act, and two buttons for one act is a button that makes people think.

The last stop's card has no **Next**. It closes with the `NextSteps` content inherited from the
panel — what happens now, and where to look — and a single **Finish**.

### Each tab stop shows the tab

Stops 6–14 carry a picture of the tab they are about. The five setup stops do not — those are
actions, and a photo of a form you are filling in below it is noise.

The images ship with the package and are served locally. They are **not** the README's shots:
`docs/readme/*.png` are narrative crops at mixed viewports, annotated for a story, and they live on
GitHub raw URLs. An install must not fetch its own onboarding over the network, and nine images shot
at nine different sizes read as nine different apps.

So one new capture script, `website/capture-walk.mjs`, built on `website/capture-readme.mjs`'s exact
pattern — a vite server over the sealed demo fixtures, one browser, one viewport, one crop — writes
nine PNGs into `website/public/walk/`. Vite copies `public/` into the build, so they land in
`taskuary/web/walk/` and serve at `/walk/<key>.png` with no endpoint to write.

`walk.py`'s stops gain an `image` field holding that path, absent on the five setup stops. The
picture is decoration with a caption's job: the stop's words still carry the meaning, and a card
whose image fails to load is still a complete stop.

**Staleness is the real cost and it is handled by regeneration, not discipline.** The script shoots
all nine in one run from one command, so bringing them back into line is one command rather than
nine judgement calls. It belongs in the release routine beside the bundle rebuild. (This is not the
`docs/hero.gif` rule — that one says never re-shoot the hero for a UI change, because it is a
composed animation. These are plain tab shots whose whole job is to match.)

### Stop 2 renders the terminal

`cliSetup.jsx` already exports `useCliSetup`, `SetupButton` and `CliPane`, and `CliPane` needs
nothing but a session id. Stop 2's card uses them directly, so pressing **Set it up** opens the real
pty inside the conversation, with `ThemeHint` beside it, looking like every other pane in the app.
This is the one stop that does work in place rather than linking out, because what it opens is a
terminal and a terminal has no page of its own to visit.

### Asking something off script

Nothing in `walk.py` calls an LLM. The stops are static text plus store reads.

A typed question during the walk is an **ordinary assistant turn** — the walk does not intercept it,
does not wrap it, and does not change its own position. When there is no model,
`concierge.fallback()` answers in facts, as it already does everywhere else in this chat. The walk
card stays in the conversation above the answer, and **Next** picks the script back up where it was.

This is the whole point of the design and it costs nothing: the walk is deterministic, the AI is for
anything off script, and that is how the assistant already works.

One amendment: `fallback`'s no-model line currently points at "Connections → AI"
(`concierge.py:626`). Now that `#cli-agents` exists it points at the AI CLI agents page, which is
where somebody with no AI actually needs to go.

## Two things that describe the old step model and must move with it

### The shipped skill

`taskuary/skills/taskuary-setup/SKILL.md` is the procedure the **AI-led** concierge walk reads
(`general.setup_skill()`, appended to a setup task's worker prompt). `/api/concierge/setup` survives
this change, so the skill survives with it — but the skill hardcodes the model this spec rewrites:

- it names all eight step keys (`owner, ai, inbound, soul, sync, style, triage, agent`)
- it describes `ready` as "the three required steps are done"
- it reads `where` off each step

After this change there are five keys, `ready` is gone, and `where` is `goto`. Left alone, the AI
walk would confidently describe a checklist that no longer exists. The skill is rewritten in the same
commit: five prerequisites in the new order, `goto` instead of `where`, `complete` instead of
`ready`, and the four displaced steps described as stops on the scripted walk rather than as rows.

`tests/test_setup_skill.py` asserts on that text and moves with it.

This is the reason the skill is a shipped document rather than branching code, and it is also the
reason it can rot quietly — nothing fails when it goes stale, the AI just says something untrue. The
test is what makes it fail loudly.

### The demo

`taskuary/demo.py` allowlists the POSTs a public visitor may make (`ALLOWED_WRITES`), and
`/api/setup/dismiss` is on it. The walk's endpoints are POSTs and would be refused with the demo's
generic refusal sentence.

The walk is exactly what a demo visitor should be able to try — it is a tour of the app that touches
nothing real — so `^/api/setup/(seen|walk)(/reset)?$` joins the allowlist. Its writes are a setting
in the demo's own database, which is what everything else on that list has in common.

The panel is a different matter: `TaskHubPage.jsx:404` already hides `SetupChip` in demo mode
(`!DEMO && !demo`), and it stays hidden — a checklist of connections nobody can make is not a demo of
anything. The chip in the assistant header stays visible, and the walk behind it works.

## Deep links

Three routes do not exist and are needed before any row can point anywhere.

| Hash | Lands on | Today |
|------|----------|-------|
| `#cli-agents` | Connections → AI CLI agents | `ConnectorsView` reads `#connector=<type>` only (`ConnectorsView.jsx:1104`); the agents page opens by state, `setOpen({kind:"agents"})` |
| `#settings=config&group=Triage%20%26%20agents` | Settings → Configuration → Triage & agents | `SettingsView` has no hash routing at all; both `page` (`PAGES`) and `cfgTab` (`GROUPS`) are state-only |
| `#owner` | Docs, scrolled to the name field | `DocsView.jsx:86` owns the field; nothing links to it |

Each follows the pattern `#connector=` already sets: read on mount, `history.replaceState` to consume
it so Back does not reopen, act. `TaskHubPage.go()` keeps routing the tab; the hash carries the
within-tab position.

## Files

**Server**

- `taskuary/setup.py` — five steps, `goto` on each, `MESSAGING` subset, `setup_seen_models`, one
  counter pair, docstring amended
- `taskuary/walk.py` — new; `STOPS` and `state()`
- `taskuary/concierge.py` — `fallback`'s no-model line points at `#cli-agents`
- `taskuary/server.py` — `POST /api/setup/seen`, `GET/POST /api/setup/walk`,
  `POST /api/setup/walk/reset`
- `taskuary/skills/taskuary-setup/SKILL.md` — realigned to the five-step model
- `taskuary/demo.py` — the walk's POSTs join `ALLOWED_WRITES`

**Web**

- `website/capture-walk.mjs` — new; nine tab shots into `website/public/walk/`
- `website/public/walk/*.png` — new; shipped by vite into `taskuary/web/walk/`
- `website/src/SetupWizard.jsx` — forms deleted except `OwnerForm`; rows become links; counters
  collapsed; `NextSteps` removed
- `website/src/AiDefaults.jsx` — post `/api/setup/seen` on mount
- `website/src/AssistantView.jsx` — `setup()` drives the walk
- `website/src/assistantCards.jsx` — new `WalkCard`
- `website/src/ConnectorsView.jsx` — `#cli-agents`
- `website/src/SettingsView.jsx` — `#settings=<page>&group=<group>`
- `website/src/DocsView.jsx` — `#owner`

## Tests

`tests/test_setup.py`, extended:

- the panel has exactly five steps, in order
- a tracker alone does not tick row 4; a mailbox does
- row 3 is false until `/api/setup/seen` is posted, true after
- `complete` is all five, and nothing reports a second tier
- every step carries a `goto`

`tests/test_onboarding_walk.py`, new (`test_setup_walk.py` is taken — it covers the concierge walk):

- stop order is stable, and the first five match `setup.state()`'s steps by key
- every stop has a non-empty `can` list
- a stop's facts match what the panel would say for the same store
- position round-trips through `POST /api/setup/walk` and survives a fresh `state()` call
- an off-script turn does not move the position
- reaching the last stop clears the stored position; reset returns to the first
- no code path in `walk.py` imports or calls `llm`

`tests/test_setup_skill.py`, moved with the skill: the assertions name the five keys, `complete`
rather than `ready`, and `goto` rather than `where`. A new one: every step key the skill names exists
in `setup.state()`, so the two can never drift apart silently again.

`tests/test_demo.py` (or wherever `ALLOWED_WRITES` is covered): the walk's endpoints are allowed and
`/api/connectors` is still refused.

Web: the existing gates — `npm run lint:undef`, the esbuild syntax check, and a rebuilt committed
bundle.

## Deliberately not doing

- **The walk does not drive the tabs.** Next does not switch the app for you; it offers a link.
  Driving the app yanks the owner off whatever they were doing and is worse on a phone.
- **`can` lists are not derived.** They are what the app can do, not what this install has done.
- **The panel does not come back.** Once the five are done the counter is gone and there is no "show
  it again". The walk is the way back, and it is always there.
- **No progress is stored for the five rows.** They stay derived, so removing a connector un-ticks its
  row the way it does today. Only the walk's position and row 3's flag are stored.
