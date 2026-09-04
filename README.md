# Taskuary

[![CI](https://github.com/ldbumble/taskuary/actions/workflows/ci.yml/badge.svg)](https://github.com/ldbumble/taskuary/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/taskuary.svg?cacheSeconds=300&release=0.3.3.2)](https://pypi.org/project/taskuary/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776ab.svg)](https://github.com/ldbumble/taskuary)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## Your inbox, staffed by AI agents

Taskuary turns incoming messages into organized work. It sorts what matters, hands tasks to
your agents, and brings decisions back to you. Nothing sends or ships without your approval.

![The Taskuary Studio: work arrives, triage decides what needs action, and agents take seats to work it.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/hero.gif?v=studio)

Taskuary is early—currently **v0.3.3.2**—so breaking changes are still possible before 1.0.

<p align="center">
  <a href="https://taskuary.com/demo/"><img
    src="https://img.shields.io/badge/%E2%96%B6%20Try%20it%20now-no%20install%2C%20in%20your%20browser-2f4858?style=for-the-badge&labelColor=1f2a22"
    alt="Try Taskuary now, in your browser"></a>
</p>

<p align="center"><sub>The real app with invented data. Nothing connects, sends, or runs.</sub></p>

## What Taskuary can do

**Connect every system. Keep control.**

Bring your mail, chats, issue trackers, alerts, reports, and AI agents into one control center
that runs on your machine. Every input lands on a single Timeline with its context, status, and
available actions intact. Taskuary gives your tools one place to work together while you decide
what can run, what can send, and what needs your attention.

![Taskuary's unified work pipe and chat, populated only with fictional demo data.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/screenshot-chat.png?v=0.3.3.2)

**Turn incoming work into tasks automatically**

AI triage reads every incoming item, understands what it means, and turns actionable requests
into ready-to-run tasks. Routine updates are filed, questions get draft replies, and urgent
decisions move to the front. Every choice comes with a reason, and you can change it at any time.

**Watch the work. Approve the outcome.**

Taskuary keeps the system moving and brings you in when your judgment matters. The Assistant
speaks up when a reply is waiting, a task has gone quiet, a report has failed, or a meeting is
about to start. Each update arrives once, with the evidence and next actions attached, so you can
review the work, make the call, and approve what happens next.

**Agents in your own repos**

Send coding work to Claude Code, Codex, Gemini, Cursor, Copilot, or another CLI.

**Live workspaces**

Watch the terminal, answer questions, review changes, and use the built-in browser without
losing the session.

**Reports and workflows**

Describe a check in plain words and Taskuary builds it: read a folder of CSVs each morning, total
the AP bills due in the next 30 days, count helpdesk tickets by day. Reports read and summarize -
on a schedule, or on demand with Run now - and can come back with an AI summary. Workflows write
data or keep state. Quiet checks stay silent, so you only hear about the one that failed.

**You stay in control**

Replies and proposed actions wait in Review. You decide what sends, runs, closes, or gets dismissed.

## How work flows

### 1. Work arrives and gets sorted

Taskuary reads connected inboxes, separates tasks from noise, and shows the result on one Timeline.

![The Timeline in task view: every message with its verdict, and the drafted reply waiting on you](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/screenshot-timeline-crop.png?v=0.3.3.2)

### 2. An agent works on it

Tasks move from **Queued** to **Agent working**. The Board shows live progress and anything waiting on you.

![Taskuary Board with queued, active, and waiting work](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/screenshot-board.png)

### 3. The result comes back to you

Finished work, draft replies, questions, and loose ends return for review. You decide what to send, change, snooze, or dismiss.

![The assistant walking the pipe: the item on the table, its drafted reply, and Approve & send waiting on you](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/screenshot-assistant.png?v=0.3.3.2)

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

- [Getting started](docs/getting-started.md)—installation, first-run setup, Docker, and data
- [Product guide](docs/product-guide.md)—the workflow, learning loop, agents, and operator documents
- [Integrations](docs/integrations.md)—channels, AI providers, work systems, and report sources
- [Reports and proactive checks](docs/reports-and-assistant.md)—the report pipeline, AI-written source cards, and what Taskuary watches
- [Status and roadmap](docs/roadmap.md)—what works today and what is next
- [Contributing](CONTRIBUTING.md)—development setup and contribution guide

Taskuary is free and open source under the [MIT License](LICENSE). Issues and pull requests
are welcome; security reports belong in [SECURITY.md](SECURITY.md).
