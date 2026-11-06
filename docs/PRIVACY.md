# Privacy

Taskuary runs on your computer and keeps your data in one folder there. Only what a task needs goes to the AI model you
choose, with secrets removed first. This page says what that means in practice: what stays, what leaves, and to whom.

There is no Taskuary account and no Taskuary server holding your data. The app does not report usage back to us.

## What runs on your computer

- **The app itself.** A local web app on `127.0.0.1:7787` (or a desktop window around it). It listens only on this
  computer unless you change `[server].host` or turn on link sharing (below).
- **Your data**, in one folder, `~/.taskuary/` (`TASKUARY_HOME` moves it; Docker uses `/data`):
  `taskuary.db` (messages, tasks, settings, the audit log), `config.toml`, `taskuary.log`, attachments, the operator
  documents (`SOUL.md`, `LEARNED.md` and the rest), playbooks, and the context files handed to coding sessions.
  The data itself is the one database file, `taskuary.db`; the rest sits beside it in the same folder.
- **Local models, if you pick them.** With Ollama or another model server on this machine, AI prompts stay on it too.
  The same holds for local voice transcription (Local Whisper) and the optional knowledge-base embeddings, which
  default to Ollama at `127.0.0.1`.

## What leaves it

Taskuary calls the services you connect, and nothing else:

| Where | What is sent | When |
|---|---|---|
| **The AI model you choose** (a hosted provider or a coding CLI) | The text a step needs: each incoming message for triage, and the task's context - the thread, what you typed, relevant notes and documents - for drafts, the Assistant and agents | Every time a model is asked something. Triage reads each new message from the channels you connect |
| **Your connected systems** (mail, chats, trackers, business systems, data sources) | The calls that read from them, and - after your press - what you approved to send, post or change | While a connection is on |
| **Your phone channel** (WhatsApp, Telegram), if you set one up | The messages of a session you start from your phone, through that service | Only while you are talking to it |
| **Web search and page readers**, if you connect one | The searches and page addresses an agent asks for | When an agent uses them |
| **A CLI's or skill's own source**, when you install one from Taskuary | The download request for that CLI, model or skill | When you press Install or import a skill |
| **GitHub** | A request for the latest release version, from the update card | When the update card checks; the GitHub connection, when you add one, talks to GitHub like any connected system |

A hosted model receives what it reads. Its provider's own terms decide how long it keeps it and what it does with it.

### Secrets removed first

Before a prompt reaches a hosted model, a headless CLI run or the first prompt of an agent pane, Taskuary replaces
credentials it can recognise - provider keys, tokens, passwords in URLs and connection strings, private keys - with a
labelled placeholder such as `[redacted:aws-key]`. The rules are deterministic, so they only catch credentials with a
recognisable shape; a sentence like "the wifi password is bluefish17" is not caught. It does **not** remove personal
or health information. Your stored mail is never altered, and a reply that still holds a placeholder is refused, not
sent. The code is [taskuary/redact.py](../taskuary/redact.py).
Where it runs: what Taskuary sends to a hosted model, a background agent run, and an agent pane's first message. A coding CLI that opens files on its own, and lines you type later into a live agent pane, reach its model as they are.

## Supported models and connections

- **AI providers:** Anthropic, OpenAI, Azure OpenAI, OpenRouter, Google Gemini, xAI, Mistral, Cohere, Groq and other
  OpenAI-compatible services; Sign in with ChatGPT; Ollama or any local OpenAI-compatible server (LM Studio,
  llama.cpp, vLLM).
- **Coding CLIs:** Claude Code, Codex, Gemini, Qwen Code, OpenCode, Kimi Code, Cursor, Copilot and others.
- **Connections:** mail (Outlook, Gmail, IMAP), chats (Teams, Slack, WhatsApp, Telegram, Discord), trackers (GitHub,
  GitLab, Jira, Linear and more), business systems and data sources. The full, current list is in
  [Connections](https://taskuary.com/docs/connections).

## Credentials

- Connection secrets are sealed by the operating system, not kept as text in the database: Windows DPAPI under your
  Windows user, or the system keychain on macOS and Linux when the `keyring` package has a backend. Where neither is
  available they stay in the database as text. This protects a copy of the database file; it is not a wall against a
  program running as your own user. Code: [taskuary/vault.py](../taskuary/vault.py).
- The app never returns a stored secret to the page: secrets are write-only once saved.
- Saved website sign-ins (**Settings → Agent permissions**) are filled in by Taskuary itself; the agent driving the
  browser never sees the password.
- Mail and other systems are read with your own sign-in, so the agreements you already hold with them still apply.

## Permissions and approvals

- **Nothing goes out until you approve it.** A reply, an email, a post, a payment, an order or a tracker change an
  agent prepares waits on the task with a button; your press runs it.
- **Each connection has a ceiling** - read, write or admin - under **Settings → Agent permissions**. Set a connection
  an agent should only read to *read*.
- **A stranger does not start an agent.** Work from someone outside the circle you set waits for your Start.
- **Your own agents run as you.** A coding agent on your task runs with its CLI's permissions bypassed, as your user,
  with a shell: it can read what your account can read, including this data folder. What it does inside your
  repository is that CLI's own work. See [Security](https://taskuary.com/docs/security) for the full list of limits.
- **A push waits for your press.** A coding agent's `git push` (and anything that deploys) is held until you approve it - unless you set that repository's GitHub connection to act on its own, in which case it goes straight through.
- **Link sharing** is off by default. Turned on, a second listener on your network serves only the shared links; the
  app and its API stay on `127.0.0.1`.

## Regulated data (HIPAA and similar)

**Taskuary is not HIPAA-certified, and has had no compliance audit.** Running on your computer does not by itself make
a setup compliant. If your work includes patient or other regulated data, you need your own setup: a model provider
and account under a Business Associate Agreement (BAA) with your organisation, or a local model, and your compliance
team's sign-off on the whole arrangement. There is no Taskuary service for us to sign a BAA for.

## The website

taskuary.com is a static site. Its demo counts visits and clicks first-party: no cookies, no third party, a session id
that lives in the browser tab, and the country Cloudflare reports. The demo connects to nothing and sends nothing.
Each event stores only: the time, that tab's session id, what was clicked or viewed, the page, the referring page, the country, and whether it was a phone ([functions/api/ev.js](../functions/api/ev.js)).

Questions or a privacy problem: open an issue, or for anything sensitive follow [SECURITY.md](../SECURITY.md).
