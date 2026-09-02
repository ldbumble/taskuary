# Taskuary

[![CI](https://github.com/ldbumble/taskuary/actions/workflows/ci.yml/badge.svg)](https://github.com/ldbumble/taskuary/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/taskuary.svg?cacheSeconds=600)](https://pypi.org/project/taskuary/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776ab.svg)](https://github.com/ldbumble/taskuary)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## Your inbox, staffed by AI agents.

Taskuary brings your mail, chats, issues, and scheduled reports onto one local timeline.
AI triage decides what is real work, your coding CLI works the tasks in your own repos,
and replies wait for your approval. Nothing sends or ships without you.

![The Taskuary Studio: work arrives, triage decides what needs action, and agents take seats to work it.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/hero.gif)

Taskuary is early—currently **v0.3.2.9**—and moving fast. The funnel, review queue,
agent sessions, and reports pipeline are in daily use; breaking changes are still possible
before 1.0.

<p align="center">
  <a href="https://taskuary.com/demo/"><img
    src="https://img.shields.io/badge/%E2%96%B6%20Try%20it%20now-no%20install%2C%20in%20your%20browser-2f4858?style=for-the-badge&labelColor=1f2a22"
    alt="Try Taskuary now, in your browser"></a>
</p>

<p align="center"><sub>The real app over invented work — timeline, triage, a coding session mid-run,
reports with charts. Nothing to install and nothing connects to anything.</sub></p>

## One timeline for incoming work

Outlook, Gmail, Teams, Slack, Telegram, WhatsApp, GitHub, Jira, alerts, and reports all
arrive on the same day-grouped rail. Each row says what it is and whether it needs you.
Open one to see the full message, its attachments, why triage ruled that way, the drafted
reply, and every available next step.

![The Timeline with mail, chats, reports, active tasks, and an Assistant post on one rail.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/screenshot-timeline-crop.png)

Coding work can go straight to Claude Code, Codex, Gemini, Cursor, Copilot, or any CLI that
accepts a prompt on stdin. You watch the live terminal, answer questions, review the diff,
and approve what happens next. Research, marketing, and other general work belong in a
conversational workspace built with assistant-ui and your existing Taskuary AI connections.
Assistant and terminal are two views of the same session: model, history, queued instructions,
image attachments, and the side-by-side browser stay put when you switch. The same workspace
also appears on the Wall.

## An assistant that notices what falls between tasks

The Assistant periodically reads what the hub can see and posts only when it has something
useful to say: a reply that went unanswered, a meeting that needs context, a task that went
quiet, or a pattern across the week's work. Every suggestion includes its evidence and can
be made into a task, dismissed, snoozed, or taught away with **Not this**.

![An Assistant post showing two evidence-backed suggestions and what it reviewed.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/screenshot-assistant.png)

It watches the systems you run on, not only the hub. Point it at a Sage Intacct query, a
database, a file, a REST or MCP tool, a cloud log group, or an agent skill—no saved report has
to stand behind any of them—and it reads each one silently on every check. That step would
otherwise ask you to know an object name and a list of field ids, so you can describe what it
should keep an eye on instead and the AI writes the source cards: it may only choose systems you
have actually connected, it reads the real schema before writing a query, and it asks rather
than guessing a filter. The same help sits on every source card in the report builder.

Its voice, schedule, model, and thresholds are yours to change. It leaves a note for its next
check, does not repeat itself, and stays silent when there is nothing worth interrupting you
for.

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

A full Taskuary over invented work — a morning's mail and chats already triaged with the
reasons attached, drafts waiting in Review, agents on the board with their transcripts
playing, live task handoffs on the Board, and the durable agent-written handbook in Social.
Every Social entry names the agent and originating task; Board handoffs are short-lived
checkout coordination that rolls up nightly. The AI answers from a script and every door
to the outside world is shut at the API layer (`taskuary/demo.py`): nothing sends, no
connection can be made or edited, no tool runs, and no CLI starts. Nobody's real data is in
it — Dana Whitfield and Northwind Facilities are invented.

## Installs

![Daily installs of taskuary from PyPI, mirror traffic excluded](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/downloads.svg)

Redrawn every morning by [`downloads.yml`](.github/workflows/downloads.yml) from PyPI's own
numbers, with mirror traffic excluded — a full PyPI mirror pulls every release, so counting it
would let a handful of real users read as hundreds. What it does **not** claim is that CI
installs have been removed: the field that would separate `pip install` in a build runner from
one on somebody's laptop is in PyPI's BigQuery dataset, not in the public API. The daily series
is [docs/downloads.csv](docs/downloads.csv).

## Documentation

- [Getting started](docs/getting-started.md)—installation, first-run setup, Docker, and data
- [Product guide](docs/product-guide.md)—the workflow, learning loop, agents, and operator documents
- [Integrations](docs/integrations.md)—channels, AI providers, work systems, and report sources
- [Reports and the Assistant](docs/reports-and-assistant.md)—the report pipeline, letting the AI write the source cards, and what the Assistant watches
- [Status and roadmap](docs/roadmap.md)—what works today and what is next
- [Contributing](CONTRIBUTING.md)—development setup and contribution guide

Taskuary is free and open source under the [MIT License](LICENSE). Issues and pull requests
are welcome; security reports belong in [SECURITY.md](SECURITY.md).
