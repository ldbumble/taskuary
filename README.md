# Taskuary

[English](README.md) · [简体中文](README.zh-CN.md)

[![CI](https://github.com/ldbumble/taskuary/actions/workflows/ci.yml/badge.svg)](https://github.com/ldbumble/taskuary/actions/workflows/ci.yml)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/ldbumble/taskuary/badge)](https://scorecard.dev/viewer/?uri=github.com/ldbumble/taskuary)
[![PyPI](https://img.shields.io/pypi/v/taskuary.svg?cacheSeconds=300&release=0.3.7.9&asof=2026-10-06T1830)](https://pypi.org/project/taskuary/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776ab.svg)](https://github.com/ldbumble/taskuary)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Stars](https://img.shields.io/github/stars/ldbumble/taskuary?style=flat&color=d4a72c&label=%E2%98%85%20stars)](https://github.com/ldbumble/taskuary/stargazers)

<p align="center"><b>⭐ Please star Taskuary if you find it helpful</b> — it is how other people find it.</p>

## Your work, already underway

**A personal AI assistant for your job.** Mail, chats and tickets become tasks, the agents you already use (Claude Code, Codex, Gemini) do the work, and nothing goes out until you approve. Open source, runs on your machine, no subscription.

Compared with hosted assistants like Fyxer, Taskuary is free and open source, runs on your machine, and hands the work to agents you already use.

![The Taskuary Studio assembling as work arrives and AI agents take their seats.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/hero.gif?v=workspace)

Taskuary is early—currently **v0.3.7.9**—so breaking changes are still possible before 1.0.

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
**Urgent**, **On you**, **For later**, the Advisor's ideas, and **FYI**. Beside it, the Assistant
says what came in and who is waiting, so you never open each system in turn.

![The work rail sorting today's items into Urgent, On you, Advisor ideas, and FYI, beside the Assistant's morning summary of who is waiting.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/01-timeline-sources-and-times.png?v=95295dd)

### 2. Let the Assistant walk you through it

Choose **Walk me through my tasks**. The Assistant puts one item on the table at a time, as the
same task card you would open yourself, with the next actions under it: **Next**, **Write reply**,
**Start an agent**. The buttons always do the same thing; the chat line is for everything else,
and the Assistant already has the message, the thread, and your past decisions to answer from.

![The Assistant bringing Ruth's request into the chat as task TQ-0018, with Next, Write reply, and Start an agent under it.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/05-assistant.png?v=95295dd)

### 3. Every request becomes a task with its whole story

Open any item to see how it got here: the message, what triage decided and why, which agent
has it, and where the reply stands.

![Ruth's request on its task: the message, the triage decision, the agent, and the reply still to write.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/02-task.png?v=95295dd)

### 4. The agent works inside the chat

**Start an agent** and it works in the same card. Here the analyst prepares the numbers, checks
that the categories add up, names its source, and drafts the reply. Nothing is sent.

![The analyst's finished vendor spend analysis inside the chat, with category totals, the change from July, and its source.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/03-agent.png?v=95295dd)

### 5. The last word is yours

The prepared reply waits on the task, beside the request that started it. Read it, edit it,
and choose **Approve & send** when it is ready.

![The drafted reply to Ruth waiting on its task, with Approve & send, Reject, and Regenerate with AI.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/04-review.png?v=95295dd)

### 6. Start your day before it gets busy

Each morning the Assistant opens with today's meetings on a timeline and who needs a word from you.
Ruth's request has a clear deadline: the 11:30 operations review.

![An animated close-up of the morning: today's meetings on a timeline, then the people and agents waiting.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/06-morning.gif?v=95295dd)

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

![Daily installs of taskuary from PyPI, mirror traffic excluded](https://raw.githubusercontent.com/ldbumble/taskuary/stats/downloads.svg)

Updated daily from PyPI with mirror traffic excluded. The raw series is
[downloads.csv on the `stats` branch](https://github.com/ldbumble/taskuary/blob/stats/downloads.csv).

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
