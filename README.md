# Taskuary

[English](README.md) · [简体中文](README.zh-CN.md)

[![CI](https://github.com/ldbumble/taskuary/actions/workflows/ci.yml/badge.svg)](https://github.com/ldbumble/taskuary/actions/workflows/ci.yml)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/ldbumble/taskuary/badge)](https://scorecard.dev/viewer/?uri=github.com/ldbumble/taskuary)
[![PyPI](https://img.shields.io/pypi/v/taskuary.svg?cacheSeconds=300&release=0.4.0.9&asof=0.4.0.9-live)](https://pypi.org/project/taskuary/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776ab.svg)](https://github.com/ldbumble/taskuary)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**AI agents that work your inbox. You approve what leaves.**

Taskuary pulls mail, chats, tickets and reports into one list. An agent works each item - researches, drafts the
reply, builds the spreadsheet, fills the form - and hands you one button: **Send**, **Pay**, **Post**. Nothing goes
out until you press it.

Runs on your computer. Free, open source, bring your own AI (Claude Code, Codex, Gemini, an API key, or a local
model). Early: **v0.4.0.9**, breaking changes possible before 1.0.

<p align="center">
  <a href="https://taskuary.com/demo/"><img
    src="https://img.shields.io/badge/%E2%96%B6%20Try%20the%20demo-in%20your%20browser-2f4858?style=for-the-badge&labelColor=1f2a22"
    alt="Try the Taskuary demo in your browser"></a>
  &nbsp;
  <a href="https://taskuary.com/docs/"><img
    src="https://img.shields.io/badge/Docs-taskuary.com-2f4858?style=for-the-badge&labelColor=1f2a22"
    alt="Read the documentation"></a>
</p>

![A task as one chat: the request on the right, the agent's turn on the left with what it did and the next step.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/02-task.png?v=chat)

## Install

**Windows:** [download the installer](https://github.com/ldbumble/taskuary/releases/latest/download/TaskuarySetup.exe). No admin rights, no Python.

**Python 3.10+** (Windows, macOS, Linux):

```bash
pip install taskuary
taskuary            # opens http://127.0.0.1:7787
```

**Docker:** `docker compose up`. **Demo, no AI or accounts:** `taskuary --demo`.

The first run asks for an AI and at least one inbox, and tests each connection before it goes live.

## How it works

1. **Everything lands in one list.** Mail (Gmail, Outlook), chats (Slack, Teams, WhatsApp, Telegram), GitHub,
   alerts and scheduled reports. Triage sorts each item: a task, something for later, a report, or FYI.
2. **An agent works each task.** It reads the thread and your notes, uses your connected systems and a browser,
   and writes up what it did. Code goes to the coding CLI you already use.
3. **You press the last button.** The email with its attachment, the post with its picture, the payment on the
   vendor's page - each waits as a card. You edit, send, or say no.
4. **It remembers.** Tell it something once ("Ray owns the ledger now") and triage, the agents and the Assistant
   use it from then on. Your edits to its drafts teach it how you write.

![The agent's turn: what it did, and a LinkedIn post with its chart waiting for one press.](https://raw.githubusercontent.com/ldbumble/taskuary/master/docs/readme/03-agent.png?v=chat)

Also: work your list from your phone over WhatsApp or Telegram, scheduled reports and dashboards, routines, and
saved sign-ins the agent can use without ever seeing the password.

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

## Documentation

[taskuary.com/docs](https://taskuary.com/docs/): [start here](https://taskuary.com/docs/),
[how it works](https://taskuary.com/docs/how-it-works), [connections](https://taskuary.com/docs/connections),
[tasks and agents](https://taskuary.com/docs/tasks-and-agents), [security](https://taskuary.com/docs/security),
[on your phone](https://taskuary.com/docs/phone), [settings](https://taskuary.com/docs/settings),
[troubleshooting](https://taskuary.com/docs/troubleshooting), [roadmap](docs/roadmap.md),
[contributing](CONTRIBUTING.md).

MIT licensed. Issues and pull requests welcome; security reports go to [SECURITY.md](SECURITY.md).
