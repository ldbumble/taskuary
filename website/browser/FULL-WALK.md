# The full walk - every screen, every button, every agent road

A walk is an agent playing the owner on a scratch app, judged by what the screen shows. Run it on all three agent roads, then fix the
design flaws it finds - the patterns behind them, never one symptom at a time. Read the repo CLAUDE.md first; its rules are the bar.

## The three roads

| road | start (website/browser/real-run.mjs) |
|---|---|
| Claude Code CLI | `EVAL_BRAIN=cli` |
| Codex CLI | `EVAL_BRAIN=codex` |
| HIPAA AI through the Codex harness | `EVAL_BRAIN=gateway EVAL_AI_MODEL=gemini-4-hydrogen` (the card's agent runs `cli:card-<id>` on Codex) |

Every run: `TASKUARY_BROWSER_PLAIN_ENV=1 REAL_OUT=<folder> REAL_BROWSER=1`, then the day's mail with
`user-walk.mjs complex-day.json` (`USER_SPEED=2 USER_SITE_PORT=<free port>`). Hands: `user.mjs` (look, click, type, attach, row, go,
wait, sent; `@file` for multi-line words). One scratch app at a time on a shared laptop; never kill a process you did not start.

## 1. Every screen and every button (UI/UX)

Click everything once, screenshot it, LOOK at the shot:

- **Setup and Change my setup**: every step in every state (pending, running, done, failed), Back/Next, the one way out, Finish.
- **Connections**: every card - mail, WhatsApp, Teams, Telegram, GitHub, calendars, Monday, search, every AI card (incl. the HIPAA
  AI harness choice), Live interaction. Type in a box (autosave shows it saved), Test, Sync now (what it pulls / what it got), Enable,
  Remove (one confirm - cancel it).
- **Settings**: every section, every switch flipped and flipped back, every picker.
- **Reports, dashboards, Hub, About you, AI routing, Profiles, Playbooks**: open, edit, run, Send to agent.
- **The rail**: Next, Back, search (open a closed task, type in it), FYI Send to agent (chip on the Agent box), Mark done, Remind me
  (confirm a date), Not for me, Watch it, Change.
- **New**: an ask, an ask with a file, an ask that restates an open task.

Look for: odd whitespace, misalignment, overlap, cut-off text; two places saying the same fact differently; duplicate buttons or a
button that does nothing; more than one Back or one input on a screen; pages that stack instead of replace; builder words (protocol
names, file names like JOB.md, "default: unchanged"), raw JSON, markdown, addresses or queries; monospace or shouting capitals; a save
with no sign it saved; a dead end with no next move; a blank beat, a jump or a flicker (record it - `recorder.mjs`).

## 2. The agent's work (the task interface)

On every road, with files attached through every door (New, a task's line, Send to agent, Continue) - check the agent's OWN log read them:

- make: an image, a chart, a PDF, a spreadsheet, a deck, a web page; read and edit a local sheet; find a file; summarize a PDF
- look up a fact and a price (web search is the model's own, fast; the browser only for a sign-up or a click)
- reply drafts: one card per person, the To / greeting / "next" line all the same person; cards in a row "1 of N"
- posts: one card per network with its picture; signed-out networks through the browser with the final Post held
- browser: sign-ups, an emailed code, a human check, a paid plan (held), a broken and a hanging site
- type while it works, Stop, press twice, a press after the agent stopped; a card shows at the tool call and nothing writes under it
- memory: correct it three times (who handles what, meeting hours, sign-off), then give work that depends on it in OTHER tasks after a
  reload - did it use the right memory?
- time each turn from his Enter to the first words and to the card; flag a wrong tool, >3 calls for one step, >20 s on a quick ask

## 3. The automated inputs (email and chats)

Feed the day's mail and check each sender class end to end - a person, a stranger, an automated notice, a list, a no-reply address,
his own message: where triage put it, whether its agent started at once, what it drafted, what a press does, what the agent is told
after. Timelines on one task: a draft exists and he answers outside the app; the sender writes again; two mails in one poll; a restart
in the middle.

## 4. Then fix

For each finding: screenshot, the screen, the quote, the cause in the code (file:line). Group them into DESIGN flaws - one state said
by one function, navigation that replaces, plain words from one wording function, one road per action - and fix the pattern at its
source with a test that fails on the old code. Prove each fix with before/after screenshots on all three roads, then walk again.

## Open issues to fix first (design walk, 2026-11-20 - owner approved)

Screenshots of the walk that found them were taken on 0.4.1.2. Fix each PATTERN at its source, then walk again.

**A. Two places state one fact and disagree** - compute each state once; every surface reads it.
- WhatsApp card: "Starting the bridge..." beside "bridge not running · idle"; step 2 in bold says "The bridge is running"; Start and
  Restart both lit. One status line, one button that fits the state, steps written as things to do.
- Setup: "Nothing more is needed... press All ready" while the top bar says "connect your main source"; clicking Finish opened More
  connections. All ready greys until the main source is set; the step you click is the step you get.
- Agent permissions: "Full authority (default)" beside "Off for agents". One plain state per row.
- HIPAA AI card: "Its agent runs on" said three times (box label, inside the box, help line).

**B. Navigation stacks instead of replacing** (owner ruling 2026-11-20: going to a page REPLACES the view).
- After Back, every page visited (Settings, Reports, Hub, About you, another task) sat above the task as a collapsed bar, the task
  pushed half off the screen.
- Three or four backs on one screen (header arrow, "Back to TQ-...", bottom Back, "‹ Email"); New has both × and Cancel and two
  input boxes. One Back and one input per screen.
- Section pickers (About you, Settings, Connections) open on chips and a blank page; the first click does nothing. Open on the first
  section; the first press counts. An open connection card sits under the full 21-chip picker - collapse it.

**C. Builder words and raw values on screen** - plain words from one wording function, the app's own font.
- "Run CLI agents over ACP... Agent Client Protocol", "Default: on - unchanged" on every row, "fine-grained PAT", "Board's repo
  picker", "coding agent's issue loop", "Baileys", "JOB.md", "0 reports (built under Reports)", "triage".
- Reports rows in monospace; a run line "0.0s · nothing to say - no post · read 0 sender/subject lines"; all-caps "PLAYBOOKS - WHAT
  THIS CONNECTION DOES FOR US"; Profiles rows "OUTSIDE information", "OUR OWN figures".
- Step lines centred and quoting raw search queries; "next: the reply to gail@northwind.example" (an address, not a name).
- File chips cut to "Q... 44 KB"; "a chat message cannot carry one".

**Smaller**: an agent's decision left as prose ("For you to do: decide...") instead of a card; "Thinking..." under a finished answer;
the header chip cut off ("Claude C..."); help text boxes narrower than their fields; "+ New playbook" wrapping alone; Hub's JOB.md
tooltip covering search; New on "Working..." ~20 s before the task appeared.

**Not yet walked**: search, FYI Send to agent, Settings toggles (the tool found no names for them), a Remind me date saved, autosave.
