# Taskuary

[English](README.md) · [简体中文](README.zh-CN.md)

[![CI](https://github.com/ldbumble/taskuary/actions/workflows/ci.yml/badge.svg)](https://github.com/ldbumble/taskuary/actions/workflows/ci.yml)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/ldbumble/taskuary/badge)](https://scorecard.dev/viewer/?uri=github.com/ldbumble/taskuary)
[![PyPI](https://img.shields.io/pypi/v/taskuary.svg?cacheSeconds=300&release=0.3.5.8&asof=2026-09-20)](https://pypi.org/project/taskuary/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776ab.svg)](https://github.com/ldbumble/taskuary)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Stars](https://img.shields.io/github/stars/ldbumble/taskuary?style=flat&color=d4a72c&label=%E2%98%85%20stars)](https://github.com/ldbumble/taskuary/stargazers)

<p align="center"><b>⭐ Please star Taskuary if you find it helpful</b> — it is how other people find it.</p>

## Your inbox, staffed by AI agents

Taskuary turns incoming messages into organized work. It sorts what matters, hands tasks to
your agents, and brings decisions back to you. Nothing sends or ships without your approval.

![The Taskuary Studio assembling as work arrives and AI agents take their seats.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/hero.gif?v=workspace)

Taskuary is early—currently **v0.3.5.8**—so breaking changes are still possible before 1.0.

<p align="center">
  <a href="https://taskuary.com/demo/"><img
    src="https://img.shields.io/badge/%E2%96%B6%20Try%20it%20now-no%20install%2C%20in%20your%20browser-2f4858?style=for-the-badge&labelColor=1f2a22"
    alt="Try Taskuary now, in your browser"></a>
</p>

<p align="center"><sub>The real app with invented data. Nothing connects, sends, or runs.</sub></p>

<p align="center"><b><a href="https://taskuary.com/docs/">Read the documentation</a></b> — installation, the first run, what to connect, and every setting.</p>

## What Taskuary can do

One request, from arrival to your approval. Follow Ruth's request for the latest vendor spend
numbers through the real app, using fictional demo data.

### 1. Connect every system. Keep control.

Mail, chats, issue trackers, alerts, and reports land on one Timeline. See what arrived,
what became a task, and what needs you without opening every system in turn.

![An annotated Timeline: each item shows its original time below its source—Email, Teams, WhatsApp, GitHub, SQL report, Assistant, Daily digest, or Calendar.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/01-timeline-sources-and-times.png)

### 2. Turn incoming work into tasks

Ruth asks for the August total, the change from July, and a breakdown by category.
Taskuary creates a task with the original request and assigns it to an agent.

![Ruth's request becomes TQ-0018, with its instructions, owner, and agent work together on the task page.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/02-task.png)

### 3. Watch the agent work

Open the task to follow the analysis. Here, the general agent prepares the numbers,
checks that the categories add up, and drafts a reply.

![The general agent's completed vendor spend analysis, with category totals, comparison, and source.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/03-agent.png)

### 4. Approve the outcome

The reply waits in **Review**, beside the request that started it. Read it, edit it,
and choose **Approve & send** when it is ready.

![Review shows Ruth's original request and the prepared reply, with Approve & send waiting for the owner.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/04-review.png)

### 5. Let the Assistant walk you through it

Choose **Walk me through my tasks**. The Assistant brings one item into the conversation,
explains what needs your attention, and puts the next action within reach.

![A close-up of the Assistant bringing Ruth's request into the conversation, with a link to its task.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/05-assistant.png)

### 6. Start your day with the daily digest

Open your morning brief to see what people need, what is in flight, and what is on your calendar.
The day's meetings sit above the digest, so Ruth's request has a clear deadline: the operations review.

![An animated close-up of the morning digest and calendar, showing the operations review and vendor planning meeting.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/06-morning.gif)

## Key features

### Use your coding CLI

Connect Claude Code, Codex, Qwen Code, OpenCode, Kimi Code, Gemini, Cursor, Copilot, Muse Code, or another CLI.
Set up the connection once, then give your agents profiles with their own instructions.
Follow their sessions, answer questions, and review the result from Taskuary.

For Qwen Code, see the [setup and compatibility guide](docs/qwen-code.md).
Use DeepSeek, GLM, or MiniMax through OpenCode, or connect Moonshot's Kimi Code:
[setup steps and supported roles](docs/chinese-coding-clis.md).

![AI CLI connections for Claude, Qwen, OpenCode with DeepSeek, and Kimi Code.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/07-coding-clis-chinese.png)

### A shared Hub for what agents learn

Keep discoveries, decisions, and useful warnings by topic. Agents can find what earlier work
uncovered, discuss it, and correct it instead of starting from scratch.

![The Hub's topics and shared discoveries, including an expanded discussion between agents.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/08-hub.png)

### Agents leave notes for each other

The Board's **Live handoffs** show what agents are working on, what is blocked, and what is ready.
An agent leaves a note; the next one reads it before picking up the work.

![Live handoff notes on the agent wall, showing progress, shared context, and who has read each note.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/09-handoffs.png)

### Memory that learns how you work

Every draft you edit and task you reclassify gives Taskuary evidence about your preferences.
Repeated patterns become lessons in **LEARNED.md**: how you write, what you own, and what
deserves a task. For example, repeatedly moving the numbers to the top of a reply can teach
it to lead with the total next time.

Open **Docs → LEARNED.md** to read, edit, or delete those lessons. Your written instructions
in `SOUL.md` take precedence.

![LEARNED.md open in the document editor, with evidence-backed preferences, hypotheses still being tested, and proposed rules awaiting the owner.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/11-learned-memory.png)

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

## Try it without installing anything

```bash
taskuary --demo                    # or: docker compose --profile demo up
```

The demo is the real interface with fictional work and scripted replies. It cannot connect to
outside systems, send messages, run tools, or start agents. Its changes reset when you reload.

## Installs

![Daily installs of taskuary from PyPI, mirror traffic excluded](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/downloads.svg)

Updated daily from PyPI with mirror traffic excluded. The raw series is
[docs/downloads.csv](docs/downloads.csv).

## Documentation

The documentation is at **[taskuary.com/docs](https://taskuary.com/docs/)**.

- [Start here](https://taskuary.com/docs/)—installation, first run, Docker, and where your data lives
- [How it works](https://taskuary.com/docs/how-it-works)—the Timeline, the five roads, what triage decides, the operator documents
- [Connections](https://taskuary.com/docs/connections)—channels, AI providers, work systems, and report sources
- [Tasks and agents](https://taskuary.com/docs/tasks-and-agents)—the task, the agent work and the reply as three separate lives
- [Reports and the Assistant](https://taskuary.com/docs/reports)—the report pipeline, AI-written source cards, and what Taskuary watches
- [Settings reference](https://taskuary.com/docs/settings)—every setting, generated from the schema the app itself reads
- [Status and roadmap](docs/roadmap.md)—what works today and what is next
- [Contributing](CONTRIBUTING.md)—development setup and contribution guide

Taskuary is free and open source under the [MIT License](LICENSE). Issues and pull requests
are welcome; security reports belong in [SECURITY.md](SECURITY.md).
