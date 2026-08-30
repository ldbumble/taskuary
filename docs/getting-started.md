# Getting started

Taskuary stores its state on your machine and opens its web interface at
`http://127.0.0.1:7787`.

## Install on Windows

Download the latest single-file
[Taskuary.exe](https://github.com/ldbumble/taskuary/releases/latest/download/Taskuary.exe)
and open it. It includes the desktop shell and does not require Python or an installer.

## Install with Python

Taskuary requires Python 3.10 or newer:

```bash
pip install taskuary
taskuary
```

The browser interface opens automatically. To run the same interface in a native desktop
window:

```bash
pip install "taskuary[desktop]"
taskuary-desktop
```

CI runs the full test matrix on Windows, Linux, and macOS. The project is developed mostly
on Windows, so the terminal, desktop shell, and agent presets get the most day-to-day use
there; macOS and Linux may still have rough edges.

## Install with Docker

Docker runs Taskuary without installing Python on the host:

```bash
git clone https://github.com/ldbumble/taskuary
cd taskuary
docker compose up
```

Open `http://127.0.0.1:7787`. Data is kept in the `taskuary-data` volume. The container
provides the Timeline, Review, Reports, and Connectors; coding CLIs and the optional
WhatsApp bridge remain host programs.

The compose file binds to localhost by default. Set `TASKUARY_TOKEN` before publishing the
port beyond the local machine.

## First-run setup

Open **Connectors** and configure these in order:

1. **A triage brain.** Add an Anthropic, OpenAI, Azure OpenAI, or OpenRouter key, or connect
   Ollama for a local model. A small inexpensive model is usually enough for triage.
2. **An inbound channel.** Connect Outlook, Gmail/IMAP, Teams, Slack, Telegram, WhatsApp,
   Discord, or one of the supported work systems. New items begin appearing on the Timeline.
3. **A coding CLI.** Choose a preset for Claude Code, Codex, Gemini, Cursor, or Copilot,
   then save and test it. A GitHub token can discover repositories automatically.
4. **Reports, if useful.** Describe a report in plain English or build one from a connected
   database, cloud account, REST endpoint, RSS feed, or MCP server. Preview it against the
   live source before scheduling it.

The **Morning digest** and **Assistant** reports are included by default. Edit their prompts
and schedules on the Reports tab, or delete either report to turn it off.

## Choosing the AI setup

Triage reads many messages and returns a short verdict; coding changes repositories much
less often and needs a stronger model. Taskuary lets those jobs use different brains.

| Setup | Triage, drafts, and summaries | Coding sessions | Best fit |
|---|---|---|---|
| **Two brains** (recommended) | Small cloud model through an AI connector | Full model through your coding CLI | You have a low-cost API key |
| **One brain, two gears** | The coding CLI's light model | The same CLI's main model | One CLI subscription, no separate key |
| **One brain, one gear** | The coding CLI's full model | The same full model | Simplest, but expensive for routine mail |
| **Local brain** | Ollama or another OpenAI-compatible local server | A coding CLI, optionally using the same local model | No key and no mail sent to a cloud model |

With no cloud key, set **Settings → Triage & routing → Triage brain** to the configured CLI.
If that CLI supports it, choose a light model on its connector card so routine triage does
not use the full coding model.

## Data and network access

The Python and desktop installs keep data in `~/.taskuary/` by default:

- `taskuary.db`—the SQLite database
- `config.toml`—local configuration
- `taskuary.log`—the application log

Set `TASKUARY_HOME` to use a different directory. Docker uses `/data` inside the container.
`TASKUARY_HOST`, `TASKUARY_PORT`, and `TASKUARY_TOKEN` can override server settings at
runtime without writing them back to the configuration file.

For LAN access, set `[server].token` in the config or provide `TASKUARY_TOKEN`, and send the
token in the `X-Taskuary-Token` header. Do not expose an unauthenticated Taskuary instance
beyond localhost.

## Next

- Read the [product guide](product-guide.md) for the complete workflow.
- Review [integrations](integrations.md) for supported systems and connector notes.
- Open the running API reference at `/api/docs`.
