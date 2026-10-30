# Taskuary

[English](README.md) · [简体中文](README.zh-CN.md)

[![CI](https://github.com/ldbumble/taskuary/actions/workflows/ci.yml/badge.svg)](https://github.com/ldbumble/taskuary/actions/workflows/ci.yml)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/ldbumble/taskuary/badge)](https://scorecard.dev/viewer/?uri=github.com/ldbumble/taskuary)
[![PyPI](https://img.shields.io/pypi/v/taskuary.svg?cacheSeconds=300&release=0.3.10.2&asof=0.3.10.2-live)](https://pypi.org/project/taskuary/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776ab.svg)](https://github.com/ldbumble/taskuary)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Stars](https://img.shields.io/github/stars/ldbumble/taskuary?style=flat&color=d4a72c&label=%E2%98%85%20stars)](https://github.com/ldbumble/taskuary/stargazers)

<p align="center"><b>⭐ Please star Taskuary if you find it helpful</b> — it is how other people find it.</p>

## Your work manager. Locally. Securely. In control.

**A personal AI assistant for your job.** Mail, chats and tickets become tasks, the agents you already use (Claude Code, Codex, Gemini) do the work, and nothing goes out until you approve. Open source, runs on your machine, no subscription.

![The Assistant's Game view: an office where every task, message and agent is a figure, opening on the whole floor and zooming into each room - the Agent Floor, the Meeting Room where people wait on you, the Gym, the Coffee Room, the Memory Archive, and the Assistant Core.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/hero.webp?v=smooth)

Taskuary is early—currently **v0.3.10.2**—so breaking changes are still possible before 1.0.

<p align="center">
  <a href="https://taskuary.com/demo/"><img
    src="https://img.shields.io/badge/%E2%96%B6%20Try%20it%20now-no%20install%2C%20in%20your%20browser-2f4858?style=for-the-badge&labelColor=1f2a22"
    alt="Try Taskuary now, in your browser"></a>
</p>

<p align="center"><sub>One guided task: an email request, checked figures, and your simulated approval. Fictional data and scripted agent work; nothing connects or sends.</sub></p>

<p align="center"><b><a href="https://taskuary.com/docs/">Read the documentation</a></b> — installation, the first run, what to connect, and every setting.</p>

## What Taskuary can do

One request, from arrival to your approval. Follow Ruth's request for the latest vendor spend
numbers through the real app, using fictional demo data.

### 1. Everything lands in one place

Mail, chats, issue trackers, alerts, and reports arrive on one rail, sorted by what they need:
**Tasks** (every open task - a spinning ring on the one an agent is working, a quiet shade on an urgent one), **For later**, **Reports**, the Advisor's ideas, and **FYI**. Beside it, the day opens on
one card: what changed since last night, what was learned, the morning digest, your meetings, and
what waits in each section - so you never open each system in turn. A goal is a task whose steps
are tasks: triage opens one for an open-ended ask, and files later mail under the step it serves.

![The work rail sorting today's items into Tasks, Reports, and FYI, beside the opening card: agents that finished and a report that ran since last night, the memory and morning digest lines, today's meetings, and what waits in each section.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/01-timeline-sources-and-times.png?v=spine)

### 2. Let the Assistant walk you through it

Choose **Walk me through my tasks**. The Assistant puts one item on the table at a time, as the
same task you would open yourself. Under it is one small bar, **Nav**: **Back** and **Next**, each greyed
where there is nowhere to go. Everything you can do to the task sits on the task itself (below). For
anything else, type in the chat pill in the corner - a window opens out of it, and the Assistant already
has the message, the thread, and your past decisions to answer from. Asked about the page on screen - a
task, a connection, a report being set up, a setting - it works that page as you would, a step at a time in
the chat: it fills boxes and presses Save, Test or Mark done, but a Send is only ever lit for you, and a
secret never reaches it. Every **Set up with AI** opens this chat.

![Ruth's request on the table with the chat window open out of the corner pill: asked what is on the list, the Assistant answers beside the task without moving it.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/05-assistant.png?v=spine)

Assistant look-ups clamp result limits to a safe range and use their default when a limit is invalid.

### 3. Every request becomes a task with its whole story

Every task reads left to right in three sections: **Came from** (the message, what triage made of it
and why, the ask), **Agent**, and **Close out**. The section the task is up to opens; the other two fold
to slim columns beside it that still say where they stand. Each section carries its own moves - on its
spine when folded, on a strip across its top when open:

- **Came from**: **Remind me**, **Not a task**, and **Change ▾** (split or merge, who does it, priority, assignee, where the code is).
- **Agent**: **Send to agent**, then **Continue** or **Run another agent** once it has run.
- **Close out**: **Draft reply** or **Reply**, **Hand it to a person**, **Mark done**, **Close with a note**, **Attach a file**, and **Share**.

![Ruth's request as a task in three sections: Came from open with Remind me and Change on its strip; Agent (not started) with Send to agent on its spine; Close out (not drafted yet) with Draft reply, Hand it to a person, Mark done, Close with a note and Share on its spine; Nav and the chat pill under it.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/02-task.png?v=spine)

### 4. The agent shows what it did

Choose **Send to agent**; the agent works in the Agent section. When it finishes, that section rests on its
Result: a summary, its answer, what it found, and **What it made** - each file with Open and Download.
The whole conversation is one link under it. **Continue** picks the same agent up with a note from you;
**Run another agent** starts a second agent on the same task. Here the agent prepares the numbers, checks that the
categories add up, saves a workbook, and drafts the reply. Nothing is sent.

![The agent's Result on Ruth's task: a one-line summary, the July and August totals by category, what it found, and the workbook it made with Open and Download; Came from and Close out folded beside it with their moves on their spines.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/03-agent.png?v=spine)

### 5. The last word is yours

The prepared reply waits in **Close out**, addressed to Ruth, with Came from and the agent's Result
folded beside it. Read it, edit it, and choose **Send** when it is ready - or **Redraft**. Sending and
closing are two steps: the task stays open until you choose **Mark done**.

![Close out open on the reply drafted to Ruth: Hand it to a person, Mark done, Attach a file, Close with a note and Share across its top; To, Cc, the editable draft, Send and Redraft under them; Came from and Agent folded beside it.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/04-review.png?v=spine)

### 6. Start your day before it gets busy

Each morning the Assistant opens on what changed since last night, what it learned, today's meetings,
and what waits in each section - and the morning digest unfolds in place, so it is never stale by the
time you reach it. Ruth's request has a clear deadline: the 11:30 operations review.

![An animated close-up of the morning: the opening card, then its morning digest unfolding - who wants what, what is in flight, and today's meetings.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/06-morning.gif?v=spine)

## Key features

### Reports, dashboards, and FYI open like work

A report opens in the same three sections as a task, the report itself in the middle - its chart,
its table, the files it attached - with **Put it on my list** beside Nav when it should become work. Dashboards land beside the reports.
What needs nothing from you is batched: one FYI card holds every message of the batch, each folded to
who, where, and its line, and **All read, next** moves on.

![A report in a task's three sections: Headcount by site, nightly, with its bar chart, table, and attached files, with Nav and Put it on my list under it.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/13-report.png?v=spine)

![The Taskuary at a glance dashboard: what came in, new tasks, open now, reply time, how far items got, and agent sessions.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/14-dashboard.png?v=spine)

![An FYI batch: six messages that need nothing, each folded to its sender, channel, subject, and first line, with All read, next in Nav under them.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/12-fyi.png?v=spine)

### General agents, coding agents, and how work fans out

A **coding agent** works in a terminal in your repository. A **general agent** works in a conversation -
research, a recommendation, a drafted reply - and touches no system. Both run on a **brain**: a CLI such as
Claude Code or Codex, or an AI connection, with the model you chose on it. What they are told is a
**profile**: instructions such as `ASSISTANT.md` for general work and `CODING.md` for code, laid on
whichever brain runs it.

Most general asks are short. When triage reads one as quick, it is answered in a single call that leaves
the same Result, draft, or question on the task an agent would. Hard work, work that needs a browser, and
a quick call that finds it needs more go to a full agent session.

Work fans out at three levels:

- **Agent sessions** run side by side up to **Settings → Agents at once** (4 by default, up to 16). The rest
  wait their turn and start as sessions end. Sessions you start yourself are never held back.
- **Quick work** has its own pool of eight calls at once, apart from that number, so a burst of mail is
  answered without opening sessions.
- **Inside a session**, a CLI may start its own subagents, background shells, and monitors. Taskuary reads
  them from the session and keeps the agent shown as working while they run; they are part of that one
  session, not extra ones.

### Use your coding CLI

Connect Claude Code, Codex, Qwen Code, OpenCode, Kimi Code, Gemini, Cursor, Copilot, Muse Code, or another CLI.
Set up the connection once, then give your agents profiles with their own instructions.
Follow their sessions, answer questions, and review the result from Taskuary.

For Qwen Code, see the [setup and compatibility guide](docs/qwen-code.md).
Use DeepSeek, GLM, or MiniMax through OpenCode, or connect Moonshot's Kimi Code:
[setup steps and supported roles](docs/chinese-coding-clis.md).

![AI CLI connections for Claude, Qwen, OpenCode with DeepSeek, and Kimi Code.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/07-coding-clis-chinese.png?v=spine)

### A shared Hub for what agents learn

Keep discoveries, decisions, and useful warnings by topic. Agents can find what earlier work
uncovered, discuss it, and correct it instead of starting from scratch.

![A discovery in the Hub, with the discussion two agents had under it.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/08-hub.png?v=spine)

### Agents leave notes for each other

The Board's **Live handoffs** show what agents are working on, what is blocked, and what is ready.
An agent leaves a note; the next one reads it before picking up the work.

![Live handoff notes on the agent wall, showing progress, shared context, and who has read each note.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/09-handoffs.png?v=spine)

### Routines, connections, sign-ins, and your phone

- **Routines.** **New → Routine** runs a job on a schedule - checks, opening tasks, preparing drafts. A coding
  routine runs a Claude Code skill in the repository you choose, as its own slash command. Each run files a
  task, and routines sit beside reports under **Reports → Routines**.
- **Combine.** Each mail and messaging connection has a **Combine** slider, 1 (Separate) to 5 (Combine): how
  readily a message from there joins a task on the same subject rather than becoming its own.
- **Data connections feed reports.** Finance and commerce sources such as Intacct, QuickBooks, and Amazon
  feed reports, dashboards, and agents; they do not put items on your rail.
- **Sign-ins stay yours.** When an agent's browser reaches a sign-in page, take over the pane or use a
  one-time sign-in page; Taskuary types the password itself, and the agent never sees it. Saved sign-ins and
  authenticator keys are under **Settings → Agent permissions**.
- **Your phone.** Over WhatsApp or Telegram, the same Assistant walks your tasks with the same buttons. It
  speaks only while you are talking to it. See [On your phone](https://taskuary.com/docs/phone).

### Memory that learns how you work

Every draft you edit and task you reclassify gives Taskuary evidence about your preferences.
Repeated patterns become lessons in **LEARNED.md**: how you write, what you own, and what
deserves a task. For example, repeatedly moving the numbers to the top of a reply can teach
it to lead with the total next time.

Open **Docs → LEARNED.md** to read, edit, or delete those lessons. Your written instructions
in `SOUL.md` take precedence.

It also learns from what came *after*. The **outcome ledger** records one row per action Taskuary
took or proposed - a reply sent, a task closed, an agent stopping and your next move in your own
words, a pull request merged, a promise made, a sender ignored - and a daily sweep fills in what
followed from facts already in the store: more rounds on the thread, a task reopened, a promise
delivered late. Reflection reads those rows as evidence, so a lesson can say "green PR from the
coding agent: you merge it, 8 of 8". A learned line never acts on its own; it changes which button comes
first. It also keeps a page per person it deals with, compiled from the same ledger: how fast they
answer, whether a chase is needed, who on copy moves them - and a thread gone quiet past that
person's own day is *slipped*, on your rail under Tasks, with Chase, Let it go, They answered elsewhere
and Remind me under it. See [The Advisor](https://taskuary.com/docs/advisor).

![LEARNED.md open in the document editor, with evidence-backed preferences, hypotheses still being tested, and proposed rules awaiting the owner.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/11-learned-memory.png?v=spine)

<details>
<summary>Technical details: how LEARNED.md becomes memory</summary>

- **Learn from a correction.** A model call turns an explicit correction into a hypothesis.
  Batched reflection compares multiple decisions; untouched approvals contribute here.
- **Keep the evidence.** Each machine-written lesson carries `s` (strength), `ev` (evidence
  IDs), and `seen` (last supporting date). A stable `k` identifies it across rewrites.
- **Promote supported patterns.** A new hypothesis starts at strength 2. Reflection is
  instructed to promote it at 4 or more, with at least three episodes across two people or
  threads. Contradictions weaken it; stale hypotheses also decay across reflection cycles.
- **Use active lessons.** The prompt builder excludes the Hypotheses, Proposed rules, and
  raw Verdicts sections. Active lessons inform triage, drafts, and agent context.
- **Keep the owner in charge.** Inferred rules that hide or file work wait in Proposed
  rules. Two matching explicit owner verdicts can already supply that authorization.
  Untagged lines you write are preserved, and learning can be disabled in Settings.

See [Learning from your decisions](https://taskuary.com/docs/how-it-works#correcting-it-teaches-it),
or the implementation in [learn.py](taskuary/learn.py) and [learnedgraph.py](taskuary/learnedgraph.py).

</details>

### What leaves your machine

![Task context passes through a credential check before reaching the chosen AI provider or CLI. Original mail stays unchanged.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/10-prompt-privacy.svg)

Taskuary runs locally. With a hosted AI provider or coding CLI, the prompt contains the context
needed to do the work you asked for. **Use a model running on your machine, and those AI prompts
stay local too.**

Credentials are taken out of that prompt first. If a colleague mails an API key, a connection
string, or a private key, it is replaced with a labelled placeholder (`[redacted:aws-key]`) at
each of the three doors a prompt can leave by: the hosted models, a headless CLI run, and the
first prompt of an agent pane. Your mail itself is never altered—the scrub is on the way out,
not on the way in—so a vendor's one-time code stays readable where it arrived. Nothing Taskuary
sends carries a placeholder either: a reply still holding one is refused, not delivered.

The rules are deterministic rather than a model's judgement, because by the time a model could
judge, the credential would already be in a prompt. So they catch credentials with a
recognizable shape—provider keys, tokens, credentialed URLs, connection strings, private
keys—and they will not catch a sentence like "the wifi password is bluefish17". Report anything
you find through [SECURITY.md](SECURITY.md).

## Install

### Windows app

Download the latest single-file
[Taskuary.exe](https://github.com/ldbumble/taskuary/releases/latest/download/Taskuary.exe)
and open it. No Python or installer is required.

### Python

Python 3.10 or newer works on Windows, macOS, and Linux:

```bash
pip install taskuary
taskuary
```

Taskuary opens at [http://127.0.0.1:7787](http://127.0.0.1:7787). For a native desktop
window instead, install `pip install "taskuary[desktop]"` and run `taskuary-desktop`.

### Docker

```bash
git clone https://github.com/ldbumble/taskuary
cd taskuary
docker compose up
```

Then open [http://127.0.0.1:7787](http://127.0.0.1:7787). Docker runs the web app;
coding CLIs and the optional WhatsApp bridge remain on the host.

On first run, connect an AI provider or local Ollama model, add at least one inbound
channel, then choose the coding CLI that should receive tasks. The setup wizards test each
connection before it goes live.

GitHub repository pickers apply to their own connection. Until an issues picker is set,
an inbound trigger creates tasks, a feed connection shows issues to read without triage, and a tool-only
connection leaves issues off. PRs default off. An explicit repository picker overrides
that connection's role without enabling other repositories or connections.

## Try it without installing anything

```bash
taskuary --demo                    # or: docker compose --profile demo up
```

The demo is the real interface with fictional work and scripted replies. It cannot connect to
outside systems, send messages, run tools, or start agents. Its changes reset when you reload.

## Installs

![Daily installs of taskuary from PyPI, mirror traffic excluded](https://raw.githubusercontent.com/ldbumble/taskuary/stats/downloads.svg)

Updated daily from PyPI with mirror traffic excluded. The raw series is
[downloads.csv on the `stats` branch](https://github.com/ldbumble/taskuary/blob/stats/downloads.csv).

## Documentation

The documentation is at **[taskuary.com/docs](https://taskuary.com/docs/)**.

- [Start here](https://taskuary.com/docs/)—installation, first run, Docker, and where your data lives
- [How it works](https://taskuary.com/docs/how-it-works)—the work rail, the five roads, what triage decides, the operator documents
- [Connections](https://taskuary.com/docs/connections)—channels, AI providers, work systems, and report sources
- [Tasks and agents](https://taskuary.com/docs/tasks-and-agents)—the task, the agent work and the reply as three separate lives
- [Security](https://taskuary.com/docs/security)—prompt injection: what Taskuary does about it, what it does not do yet, and what to set
- [Assistant buttons](https://taskuary.com/docs/assistant)—every button under an Assistant card, the one question two of them ask, and the words that work typed
- [What the Assistant sees](https://taskuary.com/docs/assistant-tools)—every tool the Assistant has, and the summary it gets on every turn
- [Reports and the Advisor](https://taskuary.com/docs/reports)—the report pipeline, AI-written source cards, and what Taskuary watches
- [The Advisor](https://taskuary.com/docs/advisor)—what goes into it, its two clocks, and the outcome ledger that teaches it what worked
- [On your phone](https://taskuary.com/docs/phone)—the same assistant over WhatsApp or Telegram, and what it may do there
- [Settings reference](https://taskuary.com/docs/settings)—every setting, generated from the schema the app itself reads
- [When something is wrong](https://taskuary.com/docs/troubleshooting)—what to check, in the order worth checking it
- [Status and roadmap](docs/roadmap.md)—what works today and what is next
- [Contributing](CONTRIBUTING.md)—development setup and contribution guide

Taskuary is free and open source under the [MIT License](LICENSE). Issues and pull requests
are welcome; security reports belong in [SECURITY.md](SECURITY.md).
