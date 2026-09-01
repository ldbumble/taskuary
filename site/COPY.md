# The words on taskuary.com

Every piece of text on the landing page, pulled out of the code and laid out as plain
writing. **Edit this file (or a copy of it) freely — you cannot break the site from here.**
Nobody has to touch HTML: whoever owns the repo pastes the approved wording back into
`site/index.html`, slot by slot, using the numbers below.

## Read this first (about "the login")

There isn't one, and that is not a permissions problem — there is no account to hand over.
taskuary.com is a single hand-written file (`site/index.html`) that Cloudflare re-publishes
every time it changes in GitHub. No CMS, no admin panel, no "edit page" button. The only
accounts involved are GitHub (where the file lives) and Cloudflare (which serves it), and
neither is a place you'd want to write copy.

Three ways to work, easiest first:

1. **This document.** Rewrite the slots below, send it back, it gets pasted in. No tools,
   no account, no markup. This is the recommended path and the reason this file exists.
2. **GitHub account.** An invite to the repo lets you edit this one file in the browser and
   get a private preview link of the real page before anything goes live. Still shaped like
   a developer tool, but it's one file and a pencil icon.
3. **Move the site onto Webflow/Framer** so there's a genuine visual editor. Honest cost:
   the animated hero is a custom renderer borrowed from the app itself and no page builder
   will host it as-is, so this means rebuilding the page. Not worth it at v0.3.

**To see the product before writing about it, you do not need a login either:**
<https://taskuary.com/demo/> is the real app running on invented work, in the browser,
no install and no sign-up.

## How to use the slots

Each slot has the text that's on the page now, and a suggested rewrite. The suggestions are
a first pass in one direction — *the product is that your work keeps moving and nothing gets
dropped; the agents are how, not what* — written to be argued with, not accepted. Strike
them out and write your own.

Keep roughly within the lengths noted; they're what the layout holds without reflowing badly.

---

## 1 · Hero (the first screen, over the animation)

**1a — Small label above the headline** *(one or two words)*
- Now: `Taskuary`
- Keep.

**1b — Headline** *(≤ 40 characters; the last few words print in the accent colour)*
- Now: `Your inbox, staffed by AI agents.`
- Suggested: `Nothing falls through the cracks.`

**1c — Scroll cue** *(≤ 20 characters)*
- Now: `find the door`
- Keep.

---

## 2 · Opening pitch (first block after the hero)

**2a — Small label** *(≤ 45 characters)*
- Now: `everything in → one funnel → agents + you`
- Suggested: `it arrives → it gets sorted → it gets done`

**2b — Headline** *(≤ 30 characters)*
- Now: `Your work AI assistant.`
- Suggested: `Your work keeps moving.`

**2c — Paragraph** *(≤ 300 characters; the first sentence prints bold)*
- Now: `Your inbox and your coding agents in one place. Mail, chats, issues and reports land
  on one timeline; triage says what is real work; the coding CLI you already use does it;
  you approve. Runs entirely on your machine.`
- Suggested: `Everything anyone asks of you, in one list, already started. Mail, chats,
  tickets and reports arrive in one place. It works out which ones are actually yours, gets
  the work underway, and waits for you to say yes. Nothing sends without you, and nothing
  leaves your computer.`

**2d — Buttons and the line under them**
- Now: `Try it now` / `no install, no sign-up — the real app over invented work, running in
  your browser` / `Download for Windows` / `View source` /
  `Free and open source (MIT) · your data never leaves the machine`
- Suggested: change only the first button's caption to `See it working` if "Try it now"
  reads as a trial sign-up. The rest is doing its job.

---

## 3 · The three steps

**3a — Step one** *(heading ≤ 40 chars, body ≤ 180)*
- Now: `01 · IN` / `Everything lands on one timeline` /
  `Outlook and IMAP mail, Teams, Slack, Telegram, WhatsApp, GitHub issues, Jira, and the
  reports you schedule — one rail, in the order it arrived.`
- Suggested: `01 · IT ARRIVES` / `Everything lands in one place` /
  `Email, Teams, Slack, WhatsApp, Telegram, tickets from Jira or GitHub, and the reports you
  asked for — one list, in the order it came in.`

**3b — Step two**
- Now: `02 · FUNNEL` / `Triage says what is real work` /
  `It reads the thread, not just the message: who was addressed, whether a colleague already
  answered, what you ruled before. A question becomes a drafted reply; work becomes a task.`
- Suggested: `02 · IT GETS SORTED` / `It works out what's actually yours` /
  `It reads the whole thread, not just the last message — who was asked, whether someone
  already answered, what you decided last time. A question gets a draft reply written. Real
  work becomes a task.`

**3c — Step three**
- Now: `03 · AGENTS + YOU` / `Your agents do it, you approve` /
  `Claude Code, Codex or Gemini open a live session on the task in your own checkout. Replies
  wait in a review queue. Nothing sends without you.`
- Suggested: `03 · IT GETS DONE` / `The work gets done. You say yes.` /
  `The task is picked up and worked on while you're elsewhere. Everything it produces —
  every reply, every change — waits in one queue for your approval. Nothing goes out on its
  own.`

---

## 4 · "What it does"

**4a — Small label**
- Now: `what it does` — keep.

**4b — Section headline** *(≤ 110 characters; one phrase can be italic)*
- Now: `Work arrives as messages. Work is tasks. You were the translation layer.`
- Suggested: `You spend your day turning other people's messages into your own to-do list.
  That's the part this does.`

**4c — Paragraph under it** *(≤ 160 characters)*
- Now: `Taskuary is that layer — local-first, with your judgement written down where the
  machine can read it.`
- Suggested: `Taskuary does that translating, on your own machine, using the judgement calls
  you've already made.`

**4d–4i — The six cards** *(heading ≤ 40 chars, body ≤ 200)*

| # | Heading now | Suggested heading |
|---|---|---|
| 4d | A review queue, not an autopilot | Nothing goes out without you |
| 4e | The Studio | See what's being worked on, right now |
| 4f | Reports you ask for in English | Ask for a report like you'd ask a person |
| 4g | It learns from your verdicts | Tell it once, it remembers |
| 4h | Your coding CLI, not ours | It uses the tools you already pay for |
| 4i | Local-first, by construction | Your data never leaves your computer |

Card bodies as they stand — rewrite any that lean on jargon:

- **4d** `Every reply and every outbound report is drafted for you first. One loud colour on
  the whole screen, spent only on what is waiting on you.`
  → *Suggested:* `Every reply and every report is written up for you to look at first. One
  colour is used on the entire site, and only ever for the things waiting on you.`
- **4e** `An isometric floor where each desk is an agent. Watch the live terminal on its
  screen, see the files it has touched, fly to a desk when it raises a hand.`
  → *Suggested:* `A floor plan where every desk is a piece of work in progress. Look over
  its shoulder while it runs, see what it changed, go straight there when it needs you.`
- **4f** `"Every Monday, vendors with unpaid invoices over 30 days, to me and Dana." SQL
  Server, Postgres, Sage Intacct, AWS, Azure, a REST endpoint — charted, attached, on the
  timeline.` → keep; the quoted example is the strongest sentence on the page.
- **4g** `"Not our task." "Priya handles AR." "Resident refunds are somebody else's." Each
  one becomes a rule that decides next time — on the thread, the topic, or the sender.`
  → keep.
- **4h** `Agents run as real sessions of the tools you already pay for — Claude Code, Codex,
  Gemini — in your repos, with a blackboard so two agents in one checkout do not collide.`
  → *Suggested:* `It drives Claude Code, Codex or Gemini — the tools you already have — on
  your own files, and keeps two of them from tripping over each other.`
- **4i** `A SQLite file in your home directory. Write-only credentials. No account, no cloud,
  no telemetry. Bind to localhost or run it in Docker on your own box.`
  → *Suggested:* `Everything sits in one file on your own machine. No account to make, no
  cloud, nothing reported back to anyone.`

---

## 5 · Download

**5a — Small label / headline**
- Now: `download` / `Runs where you work.` — keep.

**5b — Line under the headline** *(≤ 140 characters)*
- Now: `One app, three ways in. It stores everything in ~/.taskuary and opens at
  localhost:7787.`
- Suggested: `One app, three ways to install it. Everything stays in a single folder on your
  machine.`

**5c — The three option cards** — `Taskuary.exe`, `pip`, `Docker`. These are install
instructions for people who already know which one they want; leave them technical.

---

## 6 · Open source

**6a — Small label / headline**
- Now: `open source` / `MIT licensed. Built in the open, in daily use.` — keep.

**6b — Line under it** *(≤ 160 characters)*
- Now: `Taskuary runs the author's own inbox. Issues get answered; pull requests get
  reviewed by the same agents it ships.`
- Suggested: `It runs the author's own inbox every day. The bug reports and code changes on
  this project get handled by the thing itself.`

**6c — "Where it is"** *(≤ 260 characters)*
- Now: `Early — v0.3 and moving fast. The funnel, the review queue, the agent sessions and
  the reports pipeline are real; the edges are still being knocked off, and breaking changes
  are possible before 1.0.`
- Suggested: `Early — v0.3, and moving fast. The sorting, the approval queue, the work
  sessions and the reports all genuinely work; the rough edges are still being smoothed, and
  things may change before version 1.0.`

**6d — The three bullets under it**
- Now: `Python 3.10+ · FastAPI · SQLite — one process, one file` / `730+ tests, run on
  Windows, macOS and Linux on every push` / `A triage dataset built from your own verdicts,
  so accuracy is a number, not a feeling`
- These speak to developers deciding whether to trust the code. Worth keeping as-is, but the
  third one could be `Its sorting is scored against your own past decisions, so "is it any
  good" has an actual number.`

**6e — "Get involved"** *(≤ 160 characters)*
- Now: `Star it so others find it. Open an issue for what is wrong. The contributing guide
  is short.` — keep.

---

## 7 · The strip at the very bottom

- Now: `everything in → one funnel → agents + you`
- Should match slot 2a exactly, whatever that becomes.

---

## Also worth deciding

Three things live outside this page and should say the same thing as slot 1b once it's
settled, or the pitch splits in two:

- **The browser tab title**, and the title on the link preview that shows when the site is
  pasted into WhatsApp or Slack — both currently `Taskuary — your work AI assistant`.
- **The link-preview blurb** — currently
  `Everything in → one funnel → agents + you. Local-first, open source.`
- **The Google search description** — currently `Your inbox and your coding agents in one
  place. Email, Teams, Slack, GitHub and scheduled reports land on one timeline; AI triage
  says what is real work; the coding CLI you already use does it; you approve. Free, open
  source, runs on your machine.` (aim for under 160 characters — Google cuts it off.)
- **The headline on the GitHub page** (`README.md`) — currently
  `Your inbox, staffed by AI agents.`, i.e. the same as slot 1b.
