# Taskuary

[English](README.md) · [简体中文](README.zh-CN.md)

[![CI](https://github.com/ldbumble/taskuary/actions/workflows/ci.yml/badge.svg)](https://github.com/ldbumble/taskuary/actions/workflows/ci.yml)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/ldbumble/taskuary/badge)](https://scorecard.dev/viewer/?uri=github.com/ldbumble/taskuary)
[![PyPI](https://img.shields.io/pypi/v/taskuary.svg?cacheSeconds=300&release=0.4.1.8&asof=0.4.1.8-live)](https://pypi.org/project/taskuary/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776ab.svg)](https://github.com/ldbumble/taskuary)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**AI agents that work your inbox. You approve what leaves.**

Taskuary pulls mail, chats, tickets and reports into one list. An agent works each item - researches, drafts the
reply, builds the spreadsheet, fills the form - and hands you one button: **Send**, **Pay**, **Post**. Nothing goes
out until you press it.

Runs on your computer. Free, open source, bring your own AI (Claude Code, Codex, Gemini, an API key, or a local
model). Early: **v0.4.1.8**, breaking changes possible before 1.0.

<p align="center">
  <a href="https://taskuary.com/demo/"><img
    src="https://img.shields.io/badge/%E2%96%B6%20Try%20the%20demo-in%20your%20browser-2f4858?style=for-the-badge&labelColor=1f2a22"
    alt="Try the Taskuary demo in your browser"></a>
  &nbsp;
  <a href="https://taskuary.com/docs/"><img
    src="https://img.shields.io/badge/Docs-taskuary.com-2f4858?style=for-the-badge&labelColor=1f2a22"
    alt="Read the documentation"></a>
</p>

![The Game view: an office where every task, message and agent is a figure - the Agent Floor, the Meeting Room where people wait on you, the Memory Archive and the Assistant Core.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/hero.webp?v=smooth)

## Install

**Windows:** [download the installer](https://github.com/ldbumble/taskuary/releases/latest/download/TaskuarySetup.exe). No admin rights, no Python.

**Python 3.10+** (Windows, macOS, Linux):

```bash
pip install taskuary
taskuary            # opens http://127.0.0.1:7787
```

**Docker:** `docker compose up`. **Demo, no AI or accounts:** `taskuary --demo`.

The first run asks for an AI and at least one inbox, and tests each connection before it goes live.

## What it does

### 1. Everything lands in one list

Mail (Gmail, Outlook), chats (Slack, Teams, WhatsApp, Telegram), GitHub, alerts and scheduled reports arrive on one
rail, sorted into what needs work, what can wait, and what is just for your information. No more checking six apps.

![The work rail sorting the day into Tasks, Reports and FYI, beside the morning card.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/01-timeline-sources-and-times.png?v=chat)

### 2. Every task is one chat

What came in sits on the right, the agent's turns on the left: what it did, the result, and the next step. Type in
the box to keep going.

![A task as one chat: the request on the right, the agent's turn on the left with what it did and the next step.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/02-task.png?v=chat)

### 3. The agent does the work, not just the summary

It reads the thread, looks things up, uses your systems and a real browser, and comes back with the finished thing:
the post with its chart, the reply with the spreadsheet attached, the payment filled in on the vendor's page. Coding
work goes to Claude Code, Codex or Gemini.

![The agent's turn: what it did, and a LinkedIn post with its chart waiting for one press.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/03-agent.png?v=chat)

### 4. You press the last button

Every email, post, push and payment waits as a card. Edit it, send it, or say no. Nothing leaves until you press.

![A reply with its workbook attached, waiting on Send.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/04-next-steps.png?v=chat)

### 5. It remembers

Tell it once ("Ray owns the ledger now") and every agent knows from then on. Your edits to its drafts teach it how
you write.

![LEARNED.md: what Taskuary learned about how you work, each lesson with its evidence.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/11-learned-memory.png?v=chat)

### 6. From your phone, too

Work your list over WhatsApp or Telegram, with the same buttons. Plus scheduled reports and dashboards, routines,
and saved sign-ins the agent uses without ever seeing the password.

**[See a full day with Taskuary →](https://taskuary.com/docs/tour)**

## Prompt injection

Taskuary reads text written by strangers, so it assumes some of it is written to steer the AI. No model reliably
refuses that, so Taskuary does not rely on the model. It limits what each step can do:

- **Triage has no tools.** The model that reads incoming mail can only label it.
- **Strangers don't start agents.** An agent works a task by itself only if the sender is trusted: your domain,
  someone you have written to, or someone you vouched for. Anyone else's task waits for your **Trust** press. A
  forged From address (failed DMARC/DKIM) counts as a stranger.
- **Nothing leaves without you.** Every email, post, push and payment waits as a card for your press, and is
  checked again when you approve it. An irreversible step in the browser waits too.
- **The agent never holds a secret.** Taskuary types saved passwords itself, and credentials are removed from
  prompts before they reach a hosted model.
- **Agents have less authority than you** inside Taskuary, and a report that reads the open web can read only the
  files it names.

What it does not do yet: a trusted sender's message can still steer an agent within what that agent is allowed to
do. The full model, the limits and what to set: [Security](https://taskuary.com/docs/security).

## Privacy

Your data stays in one file on your computer. Only what a task needs goes to the AI you chose; with a local model,
nothing leaves. Details: [Privacy](docs/PRIVACY.md).

## Installs

![Daily installs of taskuary from PyPI, mirror traffic excluded](https://raw.githubusercontent.com/ldbumble/taskuary/stats/downloads.svg)

## Help build it

**⭐ If Taskuary helps you, please [star the repo](https://github.com/ldbumble/taskuary/stargazers).** Stars are how
other people find it, and the clearest signal of what to keep building.

Contributors are welcome. A good first PR is a report connector: about 15 lines turns any system (Postgres, Google
Sheets, Jira...) into a report an agent reads. [CONTRIBUTING.md](CONTRIBUTING.md) has the recipe, the repo map and
the dev setup, and the [good first issues](https://github.com/ldbumble/taskuary/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22)
are waiting. Tests run offline, with no credentials. Please read the [Code of Conduct](CODE_OF_CONDUCT.md).

MIT licensed. Security reports go to [SECURITY.md](SECURITY.md).
